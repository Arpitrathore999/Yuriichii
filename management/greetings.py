# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/greetings.py — Welcome / Goodbye (Media Support)
# --------------------------------------------------------------------------------

import asyncio
import re
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.errors import RPCError

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
COLLECTION = "greetings"

DEFAULT_WELCOME = "👋 <b>Welcome {mention} to {chat}!</b>"
DEFAULT_GOODBYE = "👋 <b>{mention} has left {chat}.</b>"


def _col():
    return db[COLLECTION] if db is not None else None


def _name(user):
    return (getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)).strip()


def _mention(user):
    return f'<a href="tg://user?id={int(user.id)}">{_name(user)}</a>'


def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _is_admin(message):
    if not _is_group(message) or not message.from_user:
        return False
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _permission(message):
    if not await _is_admin(message):
        await message.reply("❌ <b>You don't have permission to use this command.</b>")
        return False
    return True


async def _get(chat_id):
    c = _col()
    if c is None:
        return {
            "chat_id": int(chat_id), "welcome": True, "goodbye": True,
            "cleanwelcome": False, "welcome_text": DEFAULT_WELCOME,
            "goodbye_text": DEFAULT_GOODBYE, "old_welcome_ids": [],
            "welcome_media": None, "goodbye_media": None,
        }
    doc = await c.find_one({"chat_id": int(chat_id)})
    if not doc:
        doc = {
            "chat_id": int(chat_id), "welcome": True, "goodbye": True,
            "cleanwelcome": False, "welcome_text": DEFAULT_WELCOME,
            "goodbye_text": DEFAULT_GOODBYE, "old_welcome_ids": [],
            "welcome_media": None, "goodbye_media": None,
        }
        await c.update_one({"chat_id": int(chat_id)}, {"$setOnInsert": doc}, upsert=True)
    return doc


async def _update(chat_id, **values):
    c = _col()
    if c is None:
        return
    await c.update_one({"chat_id": int(chat_id)}, {"$set": values}, upsert=True)


def _fill(text, user, chat):
    values = {
        "{name}": _name(user),
        "{mention}": _mention(user),
        "{id}": str(user.id),
        "{username}": f"@{user.username}" if user.username else "",
        "{chat}": getattr(chat, "title", "Group") or "Group",
        "{chat_id}": str(chat.id),
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def _extract_media(replied):
    """Return (media_type, file_id) or (None, None)."""
    if not replied:
        return None, None
    if replied.photo:
        return "photo", replied.photo.file_id
    if replied.video:
        return "video", replied.video.file_id
    if replied.animation:
        return "gif", replied.animation.file_id
    if replied.document:
        return "document", replied.document.file_id
    if replied.sticker:
        return "sticker", replied.sticker.file_id
    return None, None


async def _send_welcome(chat_id, reply_to_id, text, media):
    """Send welcome with optional media."""
    try:
        if media and media.get("type") == "photo":
            return await app.send_photo(chat_id, photo=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "video":
            return await app.send_video(chat_id, video=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "gif":
            return await app.send_animation(chat_id, animation=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "document":
            return await app.send_document(chat_id, document=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "sticker":
            # Send sticker then text
            await app.send_sticker(chat_id, sticker=media["file_id"], reply_to_message_id=reply_to_id)
            return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
        # No media — plain text
        return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
    except Exception as e:
        print(f"[welcome-send] {type(e).__name__}: {e}", flush=True)
        return None


async def _send_goodbye(chat_id, reply_to_id, text, media):
    """Send goodbye with optional media."""
    try:
        if media and media.get("type") == "photo":
            return await app.send_photo(chat_id, photo=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "video":
            return await app.send_video(chat_id, video=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "gif":
            return await app.send_animation(chat_id, animation=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "document":
            return await app.send_document(chat_id, document=media["file_id"], caption=text, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        if media and media.get("type") == "sticker":
            await app.send_sticker(chat_id, sticker=media["file_id"], reply_to_message_id=reply_to_id)
            return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
        return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
    except Exception as e:
        print(f"[goodbye-send] {type(e).__name__}: {e}", flush=True)
        return None


# ── Settings commands ─────────────────────────────────────────────────────────

@app.on_message(
    filters.group
    & filters.incoming
    & filters.command(
        ["welcome", "goodbye", "setwelcome", "resetwelcome",
         "setgoodbye", "resetgoodbye", "cleanwelcome"],
        PREFIXES,
    )
)
async def greetings_settings(_, message):
    if not await _permission(message):
        return
    command = (message.command[0] or "").lower()
    args = " ".join(message.command[1:]).strip()

    # ── Toggle commands ──
    if command in ("welcome", "goodbye", "cleanwelcome"):
        if not args:
            doc = await _get(message.chat.id)
            key = command
            await message.reply(f"✦ <b>{command.title()}:</b> {'ON' if doc.get(key) else 'OFF'}")
            return
        value = args.lower()
        if value not in ("yes", "no", "on", "off"):
            await message.reply("❌ Use <code>yes</code>, <code>no</code>, <code>on</code> or <code>off</code>.")
            return
        enabled = value in ("yes", "on")
        await _update(message.chat.id, **{command: enabled})
        await message.reply(f"✓ <b>{command.title()} messages {'enabled' if enabled else 'disabled'}.</b>")
        return

    # ── Set welcome (text or media) ──
    if command == "setwelcome":
        media_type, media_id = _extract_media(message.reply_to_message)
        if media_type:
            # Media + optional caption
            caption = args if args else (message.reply_to_message.caption or DEFAULT_WELCOME)
            await _update(message.chat.id,
                          welcome_text=caption,
                          welcome_media={"type": media_type, "file_id": media_id})
            return await message.reply(f"✓ <b>Welcome media set</b> ({media_type}).")
        if not args:
            return await message.reply(
                "❌ <b>Uꜱᴀɢᴇ:</b>\n"
                "• <code>.setwelcome &lt;text&gt;</code>\n"
                "• ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ/ᴠɪᴅᴇᴏ/ɢɪꜰ ᴡɪᴛʜ <code>.setwelcome</code>"
            )
        await _update(message.chat.id, welcome_text=args, welcome_media=None)
        return await message.reply("✓ <b>Welcome message updated.</b>")

    # ── Reset welcome ──
    if command == "resetwelcome":
        await _update(message.chat.id, welcome_text=DEFAULT_WELCOME, welcome_media=None)
        return await message.reply("✓ <b>Welcome message reset.</b>")

    # ── Set goodbye (text or media) ──
    if command == "setgoodbye":
        media_type, media_id = _extract_media(message.reply_to_message)
        if media_type:
            caption = args if args else (message.reply_to_message.caption or DEFAULT_GOODBYE)
            await _update(message.chat.id,
                          goodbye_text=caption,
                          goodbye_media={"type": media_type, "file_id": media_id})
            return await message.reply(f"✓ <b>Goodbye media set</b> ({media_type}).")
        if not args:
            return await message.reply(
                "❌ <b>Uꜱᴀɢᴇ:</b>\n"
                "• <code>.setgoodbye &lt;text&gt;</code>\n"
                "• ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ/ᴠɪᴅᴇᴏ/ɢɪꜰ ᴡɪᴛʜ <code>.setgoodbye</code>"
            )
        await _update(message.chat.id, goodbye_text=args, goodbye_media=None)
        return await message.reply("✓ <b>Goodbye message updated.</b>")

    # ── Reset goodbye ──
    if command == "resetgoodbye":
        await _update(message.chat.id, goodbye_text=DEFAULT_GOODBYE, goodbye_media=None)
        return await message.reply("✓ <b>Goodbye message reset.</b>")


# ── Welcome handler ───────────────────────────────────────────────────────────

@app.on_message(filters.group & filters.new_chat_members, group=-5)
async def welcome_members(_, message):
    doc = await _get(message.chat.id)
    if not doc.get("welcome", True):
        return

    if doc.get("cleanwelcome"):
        await _clean_old(message.chat.id)

    for user in message.new_chat_members:
        if getattr(user, "is_bot", False):
            continue
        text = _fill(doc.get("welcome_text") or DEFAULT_WELCOME, user, message.chat)
        media = doc.get("welcome_media")
        sent = await _send_welcome(message.chat.id, message.id, text, media)
        if sent:
            await _remember_welcome(message.chat.id, sent.id)
            if doc.get("cleanwelcome"):
                asyncio.create_task(_expire_welcome(message.chat.id, sent.id))


# ── Goodbye handler ───────────────────────────────────────────────────────────

@app.on_message(filters.group & filters.left_chat_member, group=-5)
async def goodbye_member(_, message):
    doc = await _get(message.chat.id)
    if not doc.get("goodbye", True):
        return
    user = message.left_chat_member
    if not user or getattr(user, "is_bot", False):
        return
    text = _fill(doc.get("goodbye_text") or DEFAULT_GOODBYE, user, message.chat)
    media = doc.get("goodbye_media")
    await _send_goodbye(message.chat.id, message.id, text, media)


# ── Cleanup helpers ───────────────────────────────────────────────────────────

async def _clean_old(chat_id, exclude=None):
    c = _col()
    if c is None:
        return
    doc = await c.find_one({"chat_id": int(chat_id)})
    ids = list(doc.get("old_welcome_ids", [])) if doc else []
    kept = []
    for mid in ids:
        if exclude is not None and int(mid) == int(exclude):
            kept.append(mid)
            continue
        try:
            await app.delete_messages(chat_id, int(mid))
        except Exception:
            pass
    await c.update_one({"chat_id": int(chat_id)}, {"$set": {"old_welcome_ids": kept}})


async def _remember_welcome(chat_id, message_id):
    c = _col()
    if c is None:
        return
    await c.update_one(
        {"chat_id": int(chat_id)},
        {"$push": {"old_welcome_ids": {"$each": [int(message_id)], "$slice": -20}}},
        upsert=True,
    )


async def _expire_welcome(chat_id, message_id):
    await asyncio.sleep(300)
    try:
        doc = await _get(chat_id)
        if not doc.get("cleanwelcome"):
            return
        await app.delete_messages(chat_id, int(message_id))
        c = _col()
        if c is not None:
            await c.update_one({"chat_id": int(chat_id)}, {"$pull": {"old_welcome_ids": int(message_id)}})
    except Exception:
        pass
