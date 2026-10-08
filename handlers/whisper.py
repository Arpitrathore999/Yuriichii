# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/whisper.py — 🔒 Whisper System (with debug)
# --------------------------------------------------------------------------------

import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from pyrogram import StopPropagation, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from core.bot import app
from database.mongo import db

BOT_USERNAME = "ItzElaraBot"

# Anti-spam
_READ_ATTEMPTS: dict = defaultdict(list)
_BLOCKED_READERS: dict = {}
_READ_WINDOW = 60
_READ_LIMIT = 3
_BLOCK_SECONDS = 600

WHISPER_TTL_SECONDS = 86400


def _whispers_col():
    return db["whispers"] if db is not None else None


def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_whisper(text: str) -> tuple[str, str]:
    """Return (message, recipient_username)."""
    body = re.sub(
        rf"^@{re.escape(BOT_USERNAME)}\s+", "", text, count=1, flags=re.I
    ).strip()
    if not body:
        return "", ""
    # Find all @mentions except bot
    matches = list(re.finditer(r"@([A-Za-z0-9_]{5,32})", body))
    filtered = [m for m in matches if m.group(1).lower() != BOT_USERNAME.lower()]
    if not filtered:
        return body, ""
    last = filtered[-1]
    recipient = last.group(1)
    msg = (body[:last.start()] + body[last.end():]).strip()
    return msg, recipient


def _is_blocked(user_id: int) -> int:
    now = time.time()
    blocked_until = _BLOCKED_READERS.get(int(user_id), 0)
    if blocked_until > now:
        return int(blocked_until - now)
    if blocked_until:
        _BLOCKED_READERS.pop(int(user_id), None)
        _READ_ATTEMPTS.pop(int(user_id), None)
    return 0


def _track_violation(user_id: int) -> bool:
    now = time.time()
    uid = int(user_id)
    recent = [t for t in _READ_ATTEMPTS.get(uid, []) if now - t < _READ_WINDOW]
    recent.append(now)
    _READ_ATTEMPTS[uid] = recent
    if len(recent) >= _READ_LIMIT:
        _BLOCKED_READERS[uid] = now + _BLOCK_SECONDS
        _READ_ATTEMPTS[uid] = []
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLER: @ItzElaraBot <message> @username
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(
    filters.group & filters.text,
    group=-50,              # Run BEFORE other handlers
)
async def whisper_handler(_, message: Message):
    if not message.from_user or not message.text:
        return

    text = message.text.strip()

    # Quick check: starts with @ItzElaraBot ?
    if not text.lower().startswith(f"@{BOT_USERNAME.lower()}"):
        return

    print(f"[WHISPER] triggered: {text[:80]}", flush=True)

    whisper_text, recipient_username = _parse_whisper(text)

    # No recipient username → let AI handle
    if not recipient_username:
        print(f"[WHISPER] no recipient, skipping → AI will handle", flush=True)
        return

    print(f"[WHISPER] text='{whisper_text}' recipient='{recipient_username}'", flush=True)

    if not whisper_text:
        await message.reply(
            "❌ <b>ᴜꜱᴀɢᴇ:</b>\n"
            f"<code>@{BOT_USERNAME} &lt;message&gt; @username</code>\n\n"
            f"<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
            f"<code>@{BOT_USERNAME} ʜᴇʟʟᴏ ʙʀᴏ @username</code>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    # Lookup recipient
    try:
        recipient = await app.get_users(recipient_username)
        print(f"[WHISPER] recipient found: {recipient.id}", flush=True)
    except Exception as e:
        print(f"[WHISPER] recipient lookup failed: {type(e).__name__}: {e}", flush=True)
        await message.reply(
            f"❌ <b>ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ:</b> @{_esc(recipient_username)}\n"
            "<i>ᴍᴀᴋᴇ sᴜʀᴇ ᴛʜᴇʏ ʜᴀᴠᴇ ᴀ ᴜꜱᴇʀɴᴀᴍᴇ ᴀɴᴅ ʜᴀᴠᴇ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ.</i>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    # Self-check
    if recipient.id == message.from_user.id:
        await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴡʜɪsᴘᴇʀ ᴛᴏ ʏᴏᴜʀsᴇʟꜰ.")
        raise StopPropagation

    # Check recipient in group
    try:
        await app.get_chat_member(message.chat.id, recipient.id)
        print(f"[WHISPER] recipient is in group", flush=True)
    except Exception as e:
        print(f"[WHISPER] recipient not in group: {type(e).__name__}: {e}", flush=True)
        await message.reply(
            f"❌ @{_esc(recipient_username)} ɪs ɴᴏᴛ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    # Store
    col = _whispers_col()
    if col is None:
        await message.reply("❌ ᴅᴀᴛᴀʙᴀsᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")
        raise StopPropagation

    whisper_id = uuid.uuid4().hex[:16]
    await col.insert_one({
        "_id": whisper_id,
        "chat_id": int(message.chat.id),
        "sender_id": int(message.from_user.id),
        "sender_name": message.from_user.first_name or "User",
        "recipient_id": int(recipient.id),
        "recipient_username": recipient_username,
        "text": whisper_text,
        "created_at": datetime.now(timezone.utc),
    })
    print(f"[WHISPER] stored: {whisper_id}", flush=True)

    # Delete original message
    try:
        await message.delete()
    except Exception as e:
        print(f"[WHISPER] delete failed: {type(e).__name__}: {e}", flush=True)

    recipient_name = recipient.first_name or recipient_username

    body = (
        f"🔒 <b>ᴡʜɪsᴘᴇʀ ꜰᴏʀ {_esc(recipient_name)}.</b>\n"
        f"<i>ᴏɴʟʏ ᴛʜᴇʏ ᴄᴀɴ ʀᴇᴀᴅ ᴛʜᴇ ᴄᴏɴᴛᴇɴᴛ.</i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "👁 ʀᴇᴀᴅ ᴄᴏɴᴛᴇɴᴛ",
            callback_data=f"whisper_read:{whisper_id}",
        )],
        [InlineKeyboardButton(
            "ℹ️ ʜᴏᴡ ᴛᴏ sᴇɴᴅ ᴀ ᴡʜɪsᴘᴇʀ?",
            callback_data="whisper_help",
        )],
    ])

    try:
        sent = await app.send_message(
            message.chat.id,
            body,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        print(f"[WHISPER] placeholder sent: {sent.id}", flush=True)
    except Exception as e:
        print(f"[WHISPER] send failed: {type(e).__name__}: {e}", flush=True)

    raise StopPropagation


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK: 👁 Read content
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^whisper_read:"), group=-50)
async def whisper_read(_, query: CallbackQuery):
    whisper_id = query.data.split(":", 1)[1]
    user = query.from_user
    if not user:
        return

    print(f"[WHISPER read] user={user.id} whisper={whisper_id}", flush=True)

    # Blocked?
    if _is_blocked(user.id):
        try:
            await query.answer()
        except Exception:
            pass
        raise StopPropagation

    col = _whispers_col()
    if col is None:
        await query.answer("❌ ᴅᴀᴛᴀʙᴀsᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
        raise StopPropagation

    doc = await col.find_one({"_id": whisper_id})
    if not doc:
        await query.answer(
            "❌ ᴛʜɪs ᴡʜɪsᴘᴇʀ ɪs ɴᴏ ʟᴏɴɢᴇʀ ᴀᴠᴀɪʟᴀʙʟᴇ.",
            show_alert=True,
        )
        raise StopPropagation

    # TTL
    created = doc.get("created_at")
    if created:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > WHISPER_TTL_SECONDS:
            await query.answer("❌ ᴛʜɪs ᴡʜɪsᴘᴇʀ ʜᴀs ᴇxᴘɪʀᴇᴅ.", show_alert=True)
            raise StopPropagation

    # Recipient only
    if int(user.id) != int(doc["recipient_id"]):
        print(f"[WHISPER read] NOT for {user.id} (belongs to {doc['recipient_id']})", flush=True)
        blocked = _track_violation(user.id)
        if blocked:
            try:
                await query.answer(
                    "⚠️ ᴅᴏɴ'ᴛ sᴘᴀᴍ! ʏᴏᴜʀ ᴍᴇssᴀɢᴇs ᴡɪʟʟ ʙᴇ ɪɢɴᴏʀᴇᴅ ꜰᴏʀ 10 ᴍɪɴᴜᴛᴇs.",
                    show_alert=True,
                )
            except Exception:
                pass
            raise StopPropagation
        try:
            await query.answer("🔒 ᴛʜɪs ᴡʜɪsᴘᴇʀ ɪs ɴᴏᴛ ꜰᴏʀ ʏᴏᴜ!", show_alert=True)
        except Exception:
            pass
        raise StopPropagation

    content = doc.get("text", "")
    sender = doc.get("sender_name", "Someone")
    alert_text = f"🔒 Whisper from {sender}:\n\n{content}"

    if len(alert_text) <= 200:
        try:
            await query.answer(alert_text, show_alert=True)
            print(f"[WHISPER read] shown via alert", flush=True)
        except Exception as e:
            print(f"[WHISPER read] alert failed: {e}", flush=True)
    else:
        try:
            await app.send_message(
                user.id,
                f"🔒 <b>ᴡʜɪsᴘᴇʀ ꜰʀᴏᴍ {_esc(sender)}:</b>\n\n{_esc(content)}",
                parse_mode=ParseMode.HTML,
            )
            await query.answer("✅ sᴇɴᴛ ᴛᴏ ʏᴏᴜʀ ᴅᴍ!", show_alert=False)
        except Exception:
            try:
                await query.answer(
                    "❌ ᴘʟᴇᴀsᴇ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ɪɴ ᴅᴍ ꜰɪʀsᴛ.",
                    show_alert=True,
                )
            except Exception:
                pass

    raise StopPropagation


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK: ℹ️ How to send
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^whisper_help$"), group=-50)
async def whisper_help(_, query: CallbackQuery):
    text = (
        f"ℹ️ How to send a whisper\n\n"
        f"Format:\n@{BOT_USERNAME} <message> @username\n\n"
        f"Example:\n@{BOT_USERNAME} hello bro @username\n\n"
        f"Notes:\n"
        f"• Bot username at start\n"
        f"• Recipient username at end\n"
        f"• Recipient must be in the group\n"
        f"• Only they can read"
    )
    try:
        await query.answer(text[:200], show_alert=True)
    except Exception:
        pass
    raise StopPropagation
