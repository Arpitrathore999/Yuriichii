# --------------------------------------------------------------------------------
# Elara © 2026
# handlers/lock.py — GC lock management
# --------------------------------------------------------------------------------

import re
import asyncio
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import RPCError

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]


async def is_approved(chat_id: int, user_id: int) -> bool:
    """Return whether a user is exempt from this group's content locks."""
    col = _col("lock_approvals")
    if col is None:
        return False
    return await col.find_one({"chat_id": int(chat_id), "user_id": int(user_id)}) is not None


async def _approval_target(message):
    """Resolve a user from reply, ID, @username, plain username or Telegram mention."""
    # 1) Reply to the user's message.
    replied = message.reply_to_message
    if replied:
        if replied.from_user:
            return replied.from_user
        # Anonymous-admin/channel messages cannot identify a user.

    # 2) Read the first argument after /approve or /unapprove.
    args = (message.command or [])[1:]
    raw = args[0].strip() if args else ""

    # 3) Text mentions (clickable names) in the command itself.
    # Pyrogram exposes a real User on TEXT_MENTION entities.
    entities = list(message.entities or []) + list(message.caption_entities or [])
    for entity in entities:
        entity_type = getattr(entity, "type", None)
        if str(entity_type).lower().endswith("text_mention") and getattr(entity, "user", None):
            return entity.user
        # Support a clickable tg://user?id=... link used as the argument.
        url = getattr(entity, "url", None)
        if url and "tg://user?id=" in url:
            match = re.search(r"tg://user\\?id=(\\d+)", url)
            if match:
                try:
                    return await app.get_users(int(match.group(1)))
                except Exception:
                    pass

    if not raw:
        return None

    # 4) Numeric Telegram user ID.
    try:
        return await app.get_users(int(raw))
    except (ValueError, TypeError):
        pass
    except Exception:
        return None

    # 5) @username or plain username (with or without @).
    username = raw.lstrip("@").strip()
    if username:
        try:
            return await app.get_users(username)
        except Exception:
            return None
    return None


async def _approval_guard(message):
    if not await _is_group(message):
        await message.reply("❌ <b>This command can only be used in groups.</b>")
        return False
    if not await _can_manage(message):
        await message.reply("❌ <b>Only group admins can manage approvals.</b>")
        return False
    if _col("lock_approvals") is None:
        await message.reply("❌ <b>Database is unavailable. Approval could not be saved.</b>")
        return False
    return True

LOCK_TYPES = {
    "sticker": "Stickers",
    "stickers": "Stickers",
    "gif": "GIFs",
    "gifs": "GIFs",
    "text": "Text",
    "photo": "Photos",
    "video": "Videos",
    "music": "Music",
    "file": "Files",
    "files": "Files",
    "voice": "Voice Messages",
    "voicemsg": "Voice Messages",
    "voice_msg": "Voice Messages",
    "video_msg": "Video Messages",
    "videomsg": "Video Messages",
    "link": "Links",
    "links": "Links",
    "all": "ALL",
}

CANONICAL = {
    "stickers", "gif", "text", "photo", "video", "music", "files",
    "voice msg", "video msg", "link", "all"
}

ALIASES = {
    "sticker": "stickers", "stickers": "stickers",
    "gif": "gif", "gifs": "gif",
    "text": "text", "photo": "photo", "video": "video", "music": "music",
    "file": "files", "files": "files",
    "voice": "voice msg", "voicemsg": "voice msg", "voice_msg": "voice msg", "voice msg": "voice msg",
    "video_msg": "video msg", "videomsg": "video msg", "video msg": "video msg",
    "link": "link", "links": "link", "all": "all",
}


def _col(name):
    return db[name] if db is not None else None


async def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _member(message, user_id):
    try:
        return await app.get_chat_member(message.chat.id, user_id)
    except Exception:
        return None


async def _is_admin(message, user_id=None):
    uid = user_id or (message.from_user.id if message.from_user else None)
    if not uid or not await _is_group(message):
        return False
    member = await _member(message, uid)
    return bool(member and member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR))


async def _can_manage(message):
    if not await _is_group(message) or not message.from_user:
        return False
    member = await _member(message, message.from_user.id)
    if not member or member.status not in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
        return False
    if member.status == ChatMemberStatus.OWNER:
        return True
    if db is not None:
        doc = await db["admin_rights"].find_one({"chat_id": int(message.chat.id), "user_id": int(message.from_user.id)})
        if doc is not None and "delete" in set(doc.get("rights", [])):
            return True
    privileges = getattr(member, "privileges", None)
    return bool(privileges and getattr(privileges, "can_delete_messages", False))


async def _bot_can_delete(message):
    member = await _member(message, "me")
    if not member:
        return False
    if member.status == ChatMemberStatus.OWNER:
        return True
    privileges = getattr(member, "privileges", None)
    return bool(member.status == ChatMemberStatus.ADMINISTRATOR and privileges and getattr(privileges, "can_delete_messages", False))


async def _settings(chat_id):
    col = _col("lock_settings")
    if col is None:
        return {"chat_id": int(chat_id), "locks": [], "warns": True}
    doc = await col.find_one({"chat_id": int(chat_id)})
    return doc or {"chat_id": int(chat_id), "locks": [], "warns": True}


async def _save(chat_id, locks=None, warns=None):
    col = _col("lock_settings")
    if col is None:
        return False
    update = {"chat_id": int(chat_id)}
    if locks is not None:
        update["locks"] = sorted(set(locks))
    if warns is not None:
        update["warns"] = bool(warns)
    await col.update_one({"chat_id": int(chat_id)}, {"$set": update}, upsert=True)
    return True


def _parse_items(args):
    raw = " ".join(args).lower().strip()
    if not raw:
        return []
    # Support: /lock voice msg /lock video msg
    tokens = raw.split()
    items, i = [], 0
    while i < len(tokens):
        if i + 1 < len(tokens) and f"{tokens[i]} {tokens[i+1]}" in ALIASES:
            items.append(ALIASES[f"{tokens[i]} {tokens[i+1]}"])
            i += 2
            continue
        if tokens[i] in ALIASES:
            items.append(ALIASES[tokens[i]])
        else:
            items.append(tokens[i])
        i += 1
    return items


def _display(items):
    return ", ".join(items) if items else "None"


async def _guard(message):
    if not await _is_group(message):
        await message.reply("❌ <b>This command can only be used in groups.</b>")
        return False
    if not await _can_manage(message):
        await message.reply("❌ <b>You don't have permission to manage locks.</b>")
        return False
    if not await _bot_can_delete(message):
        await message.reply("❌ <b>I need delete-message admin permission to enforce locks.</b>")
        return False
    return True


@app.on_message(filters.command("lock", prefixes=PREFIXES))
async def lock_command(_, message):
    if not await _guard(message):
        return
    items = _parse_items((message.command or [])[1:])
    if not items:
        return await message.reply("❌ <b>Usage:</b> <code>/lock stickers link</code>")
    invalid = [x for x in items if x not in CANONICAL]
    if invalid:
        return await message.reply("❌ <b>Unknown lock type:</b> <code>" + ", ".join(invalid) + "</code>\nUse <code>/locktypes</code>.")
    settings = await _settings(message.chat.id)
    locks = set(settings.get("locks", []))
    if "all" in items:
        locks = {"all"}
    else:
        locks.update(items)
        locks.discard("all")
    await _save(message.chat.id, locks=locks)
    await message.reply(f"🔒 <b>Lᴏᴄᴋᴇᴅ:</b> <code>{_display(sorted(locks))}</code>")


@app.on_message(filters.command("unlock", prefixes=PREFIXES))
async def unlock_command(_, message):
    if not await _guard(message):
        return
    items = _parse_items((message.command or [])[1:])
    if not items:
        return await message.reply("❌ <b>Usage:</b> <code>/unlock stickers link</code>")
    invalid = [x for x in items if x not in CANONICAL]
    if invalid:
        return await message.reply("❌ <b>Unknown lock type:</b> <code>" + ", ".join(invalid) + "</code>")
    settings = await _settings(message.chat.id)
    locks = set(settings.get("locks", []))
    if "all" in items:
        locks.clear()
    else:
        for item in items:
            locks.discard(item)
    await _save(message.chat.id, locks=locks)
    await message.reply(f"🔓 <b>Uɴʟᴏᴄᴋᴇᴅ:</b> <code>{_display(items)}</code>")


@app.on_message(filters.command("locks", prefixes=PREFIXES))
async def locks_command(_, message):
    if not await _is_group(message):
        return await message.reply("❌ <b>This command can only be used in groups.</b>")
    settings = await _settings(message.chat.id)
    locks = settings.get("locks", [])
    if not locks:
        return await message.reply("🔓 <b>Nᴏ ʟᴏᴄᴋs ᴀʀᴇ ᴀᴄᴛɪᴠᴇ.</b>")
    await message.reply("🔒 <b>Lᴏᴄᴋᴇᴅ Iᴛᴇᴍs</b>\n\n" + "\n".join(f"• <code>{x}</code>" for x in locks))


@app.on_message(filters.command("lockwarns", prefixes=PREFIXES))
async def lockwarns_command(_, message):
    if not await _guard(message):
        return
    args = message.command or []
    if len(args) < 2:
        settings = await _settings(message.chat.id)
        state = "ᴏɴ" if settings.get("warns", True) else "ᴏғғ"
        return await message.reply(f"⚠️ <b>Lᴏᴄᴋ Wᴀʀɴs:</b> {state}")
    value = args[1].lower()
    if value in ("yes", "on"):
        await _save(message.chat.id, warns=True)
        return await message.reply("⚠️ <b>Lᴏᴄᴋ ᴡᴀʀɴs ᴇɴᴀʙʟᴇᴅ.</b>")
    if value in ("no", "off"):
        await _save(message.chat.id, warns=False)
        return await message.reply("🔕 <b>Lᴏᴄᴋ ᴡᴀʀɴs ᴅɪsᴀʙʟᴇᴅ.</b>")
    await message.reply("❌ <b>Use:</b> <code>/lockwarns yes</code> or <code>/lockwarns no</code>")


@app.on_message(filters.command("locktypes", prefixes=PREFIXES))
async def locktypes_command(_, message):
    await message.reply(
        "🔐 <b>Lᴏᴄᴋᴀʙʟᴇ Tʏᴘᴇs</b>\n\n"
        "• <code>stickers</code>\n• <code>gif</code>\n• <code>text</code>\n• <code>photo</code>\n"
        "• <code>video</code>\n• <code>music</code>\n• <code>files</code>\n• <code>voice msg</code>\n"
        "• <code>video msg</code>\n• <code>link</code>\n• <code>all</code>"
    )


@app.on_message(filters.command("approve", prefixes=PREFIXES))
async def approve_command(_, message):
    if not await _approval_guard(message):
        return
    user = await _approval_target(message)
    if not user:
        return await message.reply(
            "❌ <b>Target not found.</b> Reply to a user's message, or use "
            "<code>/approve @username</code>, <code>/approve username</code>, "
            "<code>/approve USER_ID</code>, or mention a user by clickable name."
        )
    col = _col("lock_approvals")
    await col.update_one(
        {"chat_id": int(message.chat.id), "user_id": int(user.id)},
        {"$set": {"chat_id": int(message.chat.id), "user_id": int(user.id),
                  "username": user.username or "", "first_name": user.first_name or ""}},
        upsert=True,
    )
    await message.reply(f"✅ <b>{user.mention} approved.</b> They can now bypass this group's content locks.")


@app.on_message(filters.command(["unapprove", "unapproveuser"], prefixes=PREFIXES))
async def unapprove_command(_, message):
    if not await _approval_guard(message):
        return
    user = await _approval_target(message)
    if not user:
        return await message.reply(
            "❌ <b>Target not found.</b> Reply to a user's message, or use "
            "<code>/unapprove @username</code>, <code>/unapprove username</code>, "
            "<code>/unapprove USER_ID</code>, or mention a user by clickable name."
        )
    result = await _col("lock_approvals").delete_one(
        {"chat_id": int(message.chat.id), "user_id": int(user.id)}
    )
    if result.deleted_count:
        await message.reply(f"🚫 <b>{user.mention} approval removed.</b>")
    else:
        await message.reply(f"ℹ️ <b>{user.mention} was not approved.</b>")


@app.on_message(filters.command(["approved", "approvedlist"], prefixes=PREFIXES))
async def approved_command(_, message):
    if not await _is_group(message):
        return await message.reply("❌ <b>This command can only be used in groups.</b>")
    col = _col("lock_approvals")
    if col is None:
        return await message.reply("❌ <b>Database is unavailable.</b>")
    cursor = col.find({"chat_id": int(message.chat.id)}).sort("user_id", 1)
    docs = await cursor.to_list(length=100)
    if not docs:
        return await message.reply("📋 <b>No approved users in this group.</b>")
    lines = []
    for i, doc in enumerate(docs, 1):
        name = (doc.get("first_name") or "User").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        username = doc.get("username")
        suffix = f" (@{username})" if username else ""
        uid = int(doc["user_id"])
        lines.append(f'{i}. <a href="tg://user?id={uid}">{name}</a>{suffix} — <code>{uid}</code>')
    await message.reply("✅ <b>Approved users</b>\n\n" + "\n".join(lines))


async def _locked_kind(message):
    if message.sticker:
        return "stickers"
    if message.animation:
        return "gif"
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.audio:
        return "music"
    if message.document:
        return "files"
    if message.voice:
        return "voice msg"
    if message.video_note:
        return "video msg"
    if message.text:
        if message.entities:
            for entity in message.entities:
                if str(entity.type).lower().endswith("url") or str(entity.type).lower().endswith("text_link"):
                    return "link"
        if re.search(r"(?:https?://|www\.|t\.me/|telegram\.me/)", message.text, re.I):
            return "link"
        return "text"
    return None


@app.on_message(filters.group & ~filters.service, group=90)
async def enforce_locks(_, message):
    if not message.chat:
        return
    settings = await _settings(message.chat.id)
    locks = set(settings.get("locks", []))
    if not locks:
        return
    if await _is_admin(message):
        return
    if message.from_user and await is_approved(message.chat.id, message.from_user.id):
        return
    kind = await _locked_kind(message)
    if not kind:
        return
    if "all" not in locks and kind not in locks:
        return
    try:
        await message.delete()
    except Exception:
        return
    if settings.get("warns", True):
        try:
            sent = await message.reply(f"⚠️ {message.from_user.mention if message.from_user else 'User'} <b>{kind}</b> is currently locked in this group.")
            await asyncio.sleep(3)
            await sent.delete()
        except Exception:
            pass
