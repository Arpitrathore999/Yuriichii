# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/greetings.py — Welcome / Goodbye (Media + Line Break Fixed)
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

# Caption limit (Telegram) — 1024. We use 900 to be safe.
CAPTION_LIMIT = 900


# ─── DB helpers ───────────────────────────────────────────────────────────────
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
    default = {
        "chat_id": int(chat_id), "welcome": True, "goodbye": True,
        "cleanwelcome": False, "welcome_text": DEFAULT_WELCOME,
        "goodbye_text": DEFAULT_GOODBYE, "old_welcome_ids": [],
        "welcome_media": None, "goodbye_media": None,
    }
    if c is None:
        return default
    doc = await c.find_one({"chat_id": int(chat_id)})
    if not doc:
        await c.update_one({"chat_id": int(chat_id)}, {"$setOnInsert": default}, upsert=True)
        return default
    return doc


async def _update(chat_id, **values):
    c = _col()
    if c is None:
        return
    await c.update_one({"chat_id": int(chat_id)}, {"$set": values}, upsert=True)


# ─── Text / media helpers ─────────────────────────────────────────────────────
def _fill(text, user, chat):
    """Replace placeholders. Preserve real line breaks for HTML captions."""
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

    # Normalize CRLF
    text = text.replace("\r\n", "\n")
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


async def _send_with_media(chat_id, reply_to_id, text, media):
    """Send media+text. Long text → media alag, text alag."""
    try:
        if not media:
            return await app.send_message(
                chat_id, text,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=reply_to_id,
            )

        mtype = media.get("type")
        fid = media.get("file_id")
        long_text = len(text) > CAPTION_LIMIT

        if mtype == "photo":
            if long_text:
                await app.send_photo(chat_id, photo=fid, reply_to_message_id=reply_to_id)
                return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
            return await app.send_photo(chat_id, photo=fid, caption=text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)

        if mtype == "video":
            if long_text:
                await app.send_video(chat_id, video=fid, reply_to_message_id=reply_to_id)
                return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
            return await app.send_video(chat_id, video=fid, caption=text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)

        if mtype == "gif":
            if long_text:
                await app.send_animation(chat_id, animation=fid, reply_to_message_id=reply_to_id)
                return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
            return await app.send_animation(chat_id, animation=fid, caption=text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)

        if mtype == "document":
            if long_text:
                await app.send_document(chat_id, document=fid, reply_to_message_id=reply_to_id)
                return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)
            return await app.send_document(chat_id, document=fid, caption=text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)

        if mtype == "sticker":
            await app.send_sticker(chat_id, sticker=fid, reply_to_message_id=reply_to_id)
            return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)

        # Unknown media type — text only
        return await app.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_to_message_id=reply_to_id)

    except Exception as e:
        print(f"[send-with-media] {type(e).__name__}: {e}", flush=True)
        return None


# ─── Settings commands ────────────────────────────────────────────────────────
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

    # Full raw text with newlines preserved (message.text keeps them)
    full = message.text or message.caption or ""
    parts = full.split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""

    # ── Toggle commands ──
    if command in ("welcome", "goodbye", "cleanwelcome"):
        if not args:
            doc = await _get(message.chat.id)
            state = "ON" if doc.get(command) else "OFF"
            return await message.reply(f"✦ <b>{command.title()}:</b> {state}")

        value = args.lower().strip()
        if value not in ("yes", "no", "on", "off"):
            return await message.reply("❌ Use <code>yes</code>, <code>no</code>, <code>on</code> or <code>off</code>.")

        enabled = value in ("yes", "on")
        await _update(message.chat.id, **{command: enabled})
        return await message.reply(
            f"✓ <b>{command.title()} messages {'enabled' if enabled else 'disabled'}.</b>"
        )

    # ── Setwelcome ──
    if command == "setwelcome":
        mtype, fid = _extract_media(message.reply_to_message)
        if mtype:
            caption = args if args else (message.reply_to_message.caption or DEFAULT_WELCOME)
            await _update(
                message.chat.id,
                welcome_text=caption,
                welcome_media={"type": mtype, "file_id": fid},
            )
            return await message.reply(f"✓ <b>Welcome media set</b> ({mtype}).")
        if not args:
            return await message.reply(
                "❌ <b>Uꜱᴀɢᴇ:</b>\n"
                "• <code>.setwelcome &lt;text&gt;</code>\n"
                "• ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ/ᴠɪᴅᴇᴏ/ɢɪꜰ ᴡɪᴛʜ <code>.setwelcome</code>"
            )
        await _update(message.chat.id, welcome_text=args, welcome_media=None)
        return await message.reply("✓ <b>Welcome message updated.</b>")

    # ── Resetwelcome ──
    if command == "resetwelcome":
        await _update(message.chat.id, welcome_text=DEFAULT_WELCOME, welcome_media=None)
        return await message.reply("✓ <b>Welcome message reset.</b>")

    # ── Setgoodbye ──
    if command == "setgoodbye":
        mtype, fid = _extract_media(message.reply_to_message)
        if mtype:
            caption = args if args else (message.reply_to_message.caption or DEFAULT_GOODBYE)
            await _update(
                message.chat.id,
                goodbye_text=caption,
                goodbye_media={"type": mtype, "file_id": fid},
            )
            return await message.reply(f"✓ <b>Goodbye media set</b> ({mtype}).")
        if not args:
            return await message.reply(
                "❌ <b>Uꜱᴀɢᴇ:</b>\n"
                "• <code>.setgoodbye &lt;text&gt;</code>\n"
                "• ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ/ᴠɪᴅᴇᴏ/ɢɪꜰ ᴡɪᴛʜ <code>.setgoodbye</code>"
            )
        await _update(message.chat.id, goodbye_text=args, goodbye_media=None)
        return await message.reply("✓ <b>Goodbye message updated.</b>")

    # ── Resetgoodbye ──
    if command == "resetgoodbye":
        await _update(message.chat.id, goodbye_text=DEFAULT_GOODBYE, goodbye_media=None)
        return await message.reply("✓ <b>Goodbye message reset.</b>")


# ─── Welcome handler ──────────────────────────────────────────────────────────
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

        sent = await _send_with_media(message.chat.id, message.id, text, media)
        if sent:
            await _remember_welcome(message.chat.id, sent.id)
            if doc.get("cleanwelcome"):
                asyncio.create_task(_expire_welcome(message.chat.id, sent.id))


# ─── Goodbye handler ──────────────────────────────────────────────────────────
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
    await _send_with_media(message.chat.id, message.id, text, media)


# ─── Cleanup ──────────────────────────────────────────────────────────────────
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
