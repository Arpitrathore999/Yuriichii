# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/filter.py — Text + Media Filters
# --------------------------------------------------------------------------------

"""Elara GC Management - Filters module.

Commands (prefixes /, !, .):
  /filter <trigger> <reply>              → text filter
  /filter <trigger>  (reply to media)    → media filter
  /filters                                → list filters
  /stop <trigger>                         → remove one
  /stopall                                → remove all

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


# ── Media helpers ─────────────────────────────────────────────────────────────

def _detect_media(replied):
    """Return (media_type, file_id, caption) if replied message has media, else None."""
    if not replied:
        return None
    if replied.sticker:
        return ("sticker", replied.sticker.file_id, None)
    if replied.animation:
        return ("gif", replied.animation.file_id, replied.caption)
    if replied.photo:
        return ("photo", replied.photo.file_id, replied.caption)
    if replied.video:
        return ("video", replied.video.file_id, replied.caption)
    if replied.audio:
        return ("audio", replied.audio.file_id, replied.caption)
    if replied.voice:
        return ("voice", replied.voice.file_id, replied.caption)
    if replied.video_note:
        return ("video_note", replied.video_note.file_id, None)
    if replied.document:
        return ("document", replied.document.file_id, replied.caption)
    return None


async def _send_media(message, media_type, file_id, caption=None):
    """Reply with the appropriate media type."""
    try:
        if media_type == "sticker":
            return await message.reply_sticker(file_id)
        if media_type == "gif":
            return await message.reply_animation(file_id, caption=caption)
        if media_type == "photo":
            return await message.reply_photo(file_id, caption=caption)
        if media_type == "video":
            return await message.reply_video(file_id, caption=caption)
        if media_type == "audio":
            return await message.reply_audio(file_id, caption=caption)
        if media_type == "voice":
            return await message.reply_voice(file_id, caption=caption)
        if media_type == "video_note":
            return await message.reply_video_note(file_id)
        if media_type == "document":
            return await message.reply_document(file_id, caption=caption)
    except Exception as e:
        print(f"[filter-media-send] {type(e).__name__}: {e}", flush=True)
    return None


# ── Argument parser (text + media) ────────────────────────────────────────────

def _parse_filter_args(message):
    """Return (trigger, reply, media_info).

    Supports:
      /filter hi Hello              → text filter
      /filter hi                    → media filter (reply to media)
      /filter hi Nice!              → media filter + custom caption (reply to media)
      /filter "hello bro" Hey!      → multi-word text trigger
    """
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None, None, None

    rest = parts[1].strip()
    if not rest:
        return None, None, None

    # ── 1. Extract trigger and inline reply (if any) ──
    reply_text = None
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end == -1:
            trigger = rest[1:].strip()
        else:
            trigger = rest[1:end].strip()
            reply_text = rest[end + 1:].strip() or None
    elif rest.startswith("'"):
        end = rest.find("'", 1)
        if end == -1:
            trigger = rest[1:].strip()
        else:
            trigger = rest[1:end].strip()
            reply_text = rest[end + 1:].strip() or None
    else:
        bits = rest.split(maxsplit=1)
        trigger = bits[0].strip()
        reply_text = bits[1].strip() if len(bits) > 1 else None

    if not trigger:
        return None, None, None

    # ── 2. Check if replied message has media ──
    media_info = _detect_media(message.reply_to_message)

    # Media filter: reply_text optional (used as caption if given)
    if media_info:
        return trigger, reply_text, media_info

    # Text filter: reply_text mandatory
    if not reply_text:
        return None, None, None

    return trigger, reply_text, None


# ── Add filter ────────────────────────────────────────────────────────────────

@app.on_message(filters.command("filter", prefixes=PREFIXES) & filters.group)
async def add_filter(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return await message.reply("❌ <b>Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ.</b>")

    trigger, reply, media_info = _parse_filter_args(message)
    if not trigger:
        return await message.reply(
            "❌ <b>Uꜱᴀɢᴇ:</b>\n"
            "• <code>.filter &lt;trigger&gt; &lt;reply&gt;</code>\n"
            "• <code>.filter &lt;trigger&gt;</code> <i>(reply to media)</i>\n"
            "• <code>.filter \"multi word\" reply</code>"
        )

    col = _collection()
    if col is None:
        return await message.reply("❌ <b>Fɪʟᴛᴇʀ ᴅᴀᴛᴀʙᴀꜱᴇ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    normalized = trigger.casefold().strip()

    # ── Media filter ──
    if media_info:
        media_type, file_id, orig_caption = media_info
        caption = reply if reply else orig_caption
        await col.update_one(
            {"chat_id": message.chat.id, "trigger": normalized},
            {
                "$set": {
                    "chat_id": message.chat.id,
                    "trigger": normalized,
                    "display_trigger": trigger,
                    "type": "media",
                    "media_type": media_type,
                    "file_id": file_id,
                    "caption": caption,
                    "added_by": message.from_user.id,
                },
                "$unset": {"reply": ""},
            },
            upsert=True,
        )
        return await message.reply(
            f"✅ <b>Mᴇᴅɪᴀ Fɪʟᴛᴇʀ Aᴅᴅᴇᴅ:</b> <code>{trigger}</code>\n"
            f"📎 Tʏᴘᴇ: <code>{media_type}</code>"
        )

    # ── Text filter ──
    await col.update_one(
        {"chat_id": message.chat.id, "trigger": normalized},
        {
            "$set": {
                "chat_id": message.chat.id,
                "trigger": normalized,
                "display_trigger": trigger,
                "type": "text",
                "reply": reply,
                "added_by": message.from_user.id,
            },
            "$unset": {"file_id": "", "media_type": "", "caption": ""},
        },
        upsert=True,
    )
    await message.reply(f"✅ <b>Tᴇxᴛ Fɪʟᴛᴇʀ Aᴅᴅᴇᴅ:</b> <code>{trigger}</code>")


# ── List filters ──────────────────────────────────────────────────────────────

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
        ftype = doc.get("type", "text")
        icon = "📎" if ftype == "media" else "📝"
        lines.append(f"{icon} <code>{trigger}</code>")
    await message.reply("\n".join(lines))


# ── Stop one ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("stop", prefixes=PREFIXES) & filters.group)
async def stop_filter(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await message.reply("❌ <b>Uꜱᴀɢᴇ:</b> <code>.stop &lt;trigger&gt;</code>")

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


# ── Stop all ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("stopall", prefixes=PREFIXES) & filters.group)
async def stop_all_filters(_, message):
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return
    col = _collection()
    if col is None:
        return await message.reply("❌ <b>Fɪʟᴛᴇʀ ᴅᴀᴛᴀʙᴀꜱᴇ ɪꜱ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    result = await col.delete_many({"chat_id": message.chat.id})
    await message.reply(f"🗑 <b>Aʟʟ Fɪʟᴛᴇʀꜱ Rᴇᴍᴏᴠᴇᴅ.</b>\nRemoved: <code>{result.deleted_count}</code>")


# ── Listener (text + media) ──────────────────────────────────────────────────

@app.on_message(
    filters.group
    & (
        filters.text
        | filters.caption
        | filters.photo
        | filters.video
        | filters.sticker
        | filters.animation
        | filters.audio
        | filters.voice
        | filters.document
        | filters.video_note
    ),
    group=30,
)
async def filter_listener(_, message):
    if not message.from_user or message.from_user.is_bot:
        return

    # Commands ko trigger mat karo
    if message.text and message.text[:1] in PREFIXES:
        return
    if message.caption and message.caption[:1] in PREFIXES:
        return

    # Match content
    content = ""
    if message.text:
        content = message.text.casefold()
    elif message.caption:
        content = message.caption.casefold()
    else:
        # Media without caption — koi trigger match nahi ho sakta
        return

    col = _collection()
    if col is None:
        return

    docs = await col.find({"chat_id": message.chat.id}).to_list(length=500)
    if not docs:
        return

    for doc in docs:
        trigger = str(doc.get("trigger", "")).casefold().strip()
        if not trigger or trigger not in content:
            continue

        # ── Media filter ──
        if doc.get("type") == "media" and doc.get("file_id"):
            await _send_media(
                message,
                doc.get("media_type"),
                doc.get("file_id"),
                doc.get("caption") or None,
            )
            break

        # ── Text filter ──
        reply = doc.get("reply")
        if reply:
            try:
                await message.reply(str(reply))
            except Exception:
                pass
            break
