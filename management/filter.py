"""Elara GC Management - Filters module.

Commands (prefixes /, !, .):
  /filter <trigger> <reply>
  /filters
  /stop <trigger>
  /stopall

Filters are case-insensitive and are stored per chat in MongoDB.
"""

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
COLLECTION = "chat_filters"


def _collection():
    return db[COLLECTION] if db is not None else None


async def _is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


def _valid_chat(message) -> bool:
    return bool(
        message.chat
        and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    )


def _parse_filter_args(message):
    """Return (trigger, reply) from the raw command text.

    Supports quoted multi-word triggers, e.g.:
      /filter "hello bro" Hey there!
    """
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None, None

    rest = parts[1].strip()
    if not rest:
        return None, None

    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end == -1:
            return None, None
        trigger = rest[1:end].strip()
        reply = rest[end + 1:].strip()
    elif rest.startswith("'"):
        end = rest.find("'", 1)
        if end == -1:
            return None, None
        trigger = rest[1:end].strip()
        reply = rest[end + 1:].strip()
    else:
        bits = rest.split(maxsplit=1)
        if len(bits) < 2:
            return None, None
        trigger, reply = bits[0], bits[1].strip()

    if not trigger or not reply:
        return None, None
    return trigger, reply


@app.on_message(filters.command("filter", prefixes=PREFIXES) & filters.group)
async def add_filter(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return await message.reply("❌ <b>Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ.</b>")

    trigger, reply = _parse_filter_args(message)
    if not trigger or not reply:
        return await message.reply(
            "❌ <b>Uꜱᴀɢᴇ:</b> <code>/filter &lt;trigger&gt; &lt;reply&gt;</code>\n"
            "Fᴏʀ ᴍᴜʟᴛɪᴘʟᴇ ᴡᴏʀᴅꜱ: <code>/filter \"hello bro\" Hi!</code>"
        )

    col = _collection()
    if col is None:
        return await message.reply("❌ <b>Fɪʟᴛᴇʀ ᴅᴀᴛᴀʙᴀꜱᴇ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    normalized = trigger.casefold().strip()
    await col.update_one(
        {"chat_id": message.chat.id, "trigger": normalized},
        {
            "$set": {
                "chat_id": message.chat.id,
                "trigger": normalized,
                "display_trigger": trigger,
                "reply": reply,
                "added_by": message.from_user.id,
            }
        },
        upsert=True,
    )
    await message.reply(f"✅ <b>Fɪʟᴛᴇʀ Aᴅᴅᴇᴅ:</b> <code>{trigger}</code>")


@app.on_message(filters.command("filters", prefixes=PREFIXES) & filters.group)
async def list_filters(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return
    col = _collection()
    if col is None:
        return await message.reply("❌ <b>Fɪʟᴛᴇʀ ᴅᴀᴛᴀʙᴀꜱᴇ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    docs = await col.find({"chat_id": message.chat.id}).sort("trigger", 1).to_list(length=500)
    if not docs:
        return await message.reply("📭 <b>Nᴏ Fɪʟᴛᴇʀꜱ ᴀʀᴇ ꜱᴇᴛ ɪɴ ᴛʜɪꜱ ᴄʜᴀᴛ.</b>")

    lines = ["🔎 <b>Cᴜʀʀᴇɴᴛ Fɪʟᴛᴇʀꜱ</b>", ""]
    for doc in docs:
        trigger = doc.get("display_trigger") or doc.get("trigger", "")
        lines.append(f"• <code>{trigger}</code>")
    await message.reply("\n".join(lines))


@app.on_message(filters.command("stop", prefixes=PREFIXES) & filters.group)
async def stop_filter(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await message.reply("❌ <b>Uꜱᴀɢᴇ:</b> <code>/stop &lt;trigger&gt;</code>")

    trigger = parts[1].strip()
    if len(trigger) >= 2 and trigger[0] == trigger[-1] and trigger[0] in ('"', "'"):
        trigger = trigger[1:-1].strip()
    normalized = trigger.casefold()

    col = _collection()
    if col is None:
        return await message.reply("❌ <b>Fɪʟᴛᴇʀ ᴅᴀᴛᴀʙᴀꜱᴇ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    result = await col.delete_one({"chat_id": message.chat.id, "trigger": normalized})
    if not result.deleted_count:
        return await message.reply(f"⚠️ <b>Fɪʟᴛᴇʀ Nᴏᴛ Fᴏᴜɴᴅ:</b> <code>{trigger}</code>")
    await message.reply(f"🗑 <b>Fɪʟᴛᴇʀ Rᴇᴍᴏᴠᴇᴅ:</b> <code>{trigger}</code>")


@app.on_message(filters.command("stopall", prefixes=PREFIXES) & filters.group)
async def stop_all_filters(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return
    col = _collection()
    if col is None:
        return await message.reply("❌ <b>Fɪʟᴛᴇʀ ᴅᴀᴛᴀʙᴀꜱᴇ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    result = await col.delete_many({"chat_id": message.chat.id})
    await message.reply(f"🗑 <b>Aʟʟ Fɪʟᴛᴇʀꜱ Rᴇᴍᴏᴠᴇᴅ.</b>\nRemoved: <code>{result.deleted_count}</code>")


@app.on_message(filters.group & filters.text, group=30)
async def filter_listener(_, message):
    if not message.from_user or message.from_user.is_bot:
        return
    if not message.text:
        return

    # Don't make management commands trigger filters.
    if message.text[:1] in PREFIXES:
        return

    col = _collection()
    if col is None:
        return

    docs = await col.find({"chat_id": message.chat.id}).to_list(length=500)
    if not docs:
        return

    content = message.text.casefold()
    for doc in docs:
        trigger = str(doc.get("trigger", "")).casefold().strip()
        reply = doc.get("reply")
        if trigger and reply and trigger in content:
            try:
                await message.reply(str(reply))
            except Exception:
                pass
            break
