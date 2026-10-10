# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/whisper.py — One-Time Receiver Whisper System
#  Supports: @username AND user ID
# --------------------------------------------------------------------------------

import re
import secrets
from typing import Dict

from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from core.bot import app


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════
BOT_USERNAME = "ItzElaraBot"


# ══════════════════════════════════════════════════════════════════════════════
#  WHISPER STORAGE
# ══════════════════════════════════════════════════════════════════════════════
# token -> whisper data
#
# Whisper remains here until:
#   • receiver reads it once
#   • bot restarts
#
# Sender can read unlimited times while active.
# Receiver can consume it only once.
_WHISPERS: Dict[str, dict] = {}


# Telegram username pattern: @username
_USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{5,32})(?!\w)")

# Telegram user ID pattern: 5-15 digits as standalone number
_USER_ID_RE = re.compile(r"(?<!\d)(\d{5,15})(?!\d)")


# ══════════════════════════════════════════════════════════════════════════════
#  PARSER — find recipient in query
# ══════════════════════════════════════════════════════════════════════════════
def _find_recipient(query: str):
    """Return (secret_text, recipient_token, recipient_type).

    recipient_type:
        "username" — @username found
        "user_id"  — numeric ID found
        ""         — no recipient
    Priority: @username first, then numeric user ID.
    """
    # ── Priority 1: @username ──
    matches = list(_USERNAME_RE.finditer(query))
    if matches:
        last = matches[-1]
        recipient = last.group(1)
        secret = (query[:last.start()] + query[last.end():]).strip()
        return secret, recipient, "username"

    # ── Priority 2: numeric user ID ──
    id_matches = list(_USER_ID_RE.finditer(query))
    if id_matches:
        last = id_matches[-1]
        recipient = last.group(1)
        secret = (query[:last.start()] + query[last.end():]).strip()
        return secret, recipient, "user_id"

    return query.strip(), "", ""


# ══════════════════════════════════════════════════════════════════════════════
#  INLINE QUERY
# ══════════════════════════════════════════════════════════════════════════════

@app.on_inline_query()
async def whisper_inline(_, inline_query):

    query = (inline_query.query or "").strip()
    results = []

    # ──────────────────────────────────────────────────────────────────────────
    # 📖 INSTRUCTIONS (always first)
    # ──────────────────────────────────────────────────────────────────────────
    instructions = InlineQueryResultArticle(
        id=f"whisper-help-{inline_query.from_user.id}",
        title="📖 Instructions",
        description="How to send and read a Whisper",
        input_message_content=InputTextMessageContent(
            "<b>🤫 Whisper Instructions</b>\n\n"

            "<b>📤 How to send:</b>\n\n"

            "<b>1️⃣ By username:</b>\n"
            f"<code>@{BOT_USERNAME} your message @username</code>\n\n"

            "<b>2️⃣ By user ID (no username):</b>\n"
            f"<code>@{BOT_USERNAME} your message 123456789</code>\n\n"

            "<b>👤 Sender:</b>\n"
            "You can read your Whisper as many times as you want "
            "until the receiver opens it.\n\n"

            "<b>🔐 Receiver:</b>\n"
            "The receiver can read the Whisper only <b>once</b>.\n\n"

            "<b>🗑️ After reading:</b>\n"
            "As soon as the receiver successfully reads it, "
            "the Whisper message is automatically deleted.\n\n"

            "<b>⚠️ Important:</b>\n"
            "Only the sender and intended receiver can read the "
            "Whisper content."
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "↗️ How to send a whisper?",
                        callback_data="wpr:help",
                    )
                ]
            ]
        ),
    )
    results.append(instructions)

    # ──────────────────────────────────────────────────────────────────────────
    # NO QUERY → show instructions only
    # ──────────────────────────────────────────────────────────────────────────
    if not query:
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return

    # ──────────────────────────────────────────────────────────────────────────
    # FIND RECIPIENT
    # ──────────────────────────────────────────────────────────────────────────
    secret_text, recipient_token, recipient_type = _find_recipient(query)

    if not recipient_token or not secret_text:
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return

    # ──────────────────────────────────────────────────────────────────────────
    # RESOLVE USER
    # ──────────────────────────────────────────────────────────────────────────
    recipient = None
    try:
        if recipient_type == "username":
            recipient = await app.get_users(recipient_token)
        elif recipient_type == "user_id":
            recipient = await app.get_users(int(recipient_token))
    except Exception as e:
        print(f"[Whisper lookup] {type(e).__name__}: {e}", flush=True)

    if not recipient:
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return

    # Don't allow whispering to bots
    if recipient.is_bot:
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return

    # ──────────────────────────────────────────────────────────────────────────
    # CREATE WHISPER TOKEN
    # ──────────────────────────────────────────────────────────────────────────
    token = secrets.token_urlsafe(18)

    recipient_name = (
        recipient.first_name
        or recipient.username
        or str(recipient.id)
    )

    _WHISPERS[token] = {
        "sender_id": inline_query.from_user.id,
        "recipient_id": recipient.id,
        "recipient_name": recipient_name,
        "text": secret_text,
    }

    # ──────────────────────────────────────────────────────────────────────────
    # WHISPER RESULT
    # ──────────────────────────────────────────────────────────────────────────
    recipient_label = (
        f"@{recipient.username}"
        if recipient.username
        else f"ID {recipient.id}"
    )

    whisper_result = InlineQueryResultArticle(
        id=token,
        title=f"Whisper for {recipient_name} ({recipient_label})",
        description=(
            "🔐 Receiver: one-time read • "
            "Sender: unlimited reads"
        ),
        input_message_content=InputTextMessageContent(
            f"🔒 <b>Whisper for {recipient_name}.</b>\n"
            "Only they can read the content.\n\n"
            "<i>👁️ Receiver can read this only once.</i>"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "👁️ Read content",
                        callback_data=f"wpr:{token}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "↗️ How to send a whisper?",
                        callback_data="wpr:help",
                    )
                ],
            ]
        ),
    )
    results.append(whisper_result)

    # ──────────────────────────────────────────────────────────────────────────
    # ANSWER
    # ──────────────────────────────────────────────────────────────────────────
    await inline_query.answer(results, cache_time=0, is_personal=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@app.on_callback_query(filters.regex(r"^wpr:"))
async def whisper_callback(_, callback_query):

    data = callback_query.data or ""

    # ──────────────────────────────────────────────────────────────────────────
    # HELP / INSTRUCTIONS
    # ──────────────────────────────────────────────────────────────────────────
    if data == "wpr:help":
        await callback_query.answer(
            "🤫 Whisper\n\n"
            "To send (by username):\n"
            f"@{BOT_USERNAME} your message @username\n\n"
            "To send (by user ID):\n"
            f"@{BOT_USERNAME} your message 123456789\n\n"
            "👤 Sender:\n"
            "You can read your Whisper unlimited times.\n\n"
            "🔐 Receiver:\n"
            "Can read it only once.\n\n"
            "🗑️ After the receiver reads it, "
            "the Whisper message is automatically deleted.",
            show_alert=True,
        )
        return

    # ──────────────────────────────────────────────────────────────────────────
    # GET TOKEN
    # ──────────────────────────────────────────────────────────────────────────
    token = data[4:]
    whisper = _WHISPERS.get(token)

    if not whisper:
        await callback_query.answer(
            "⌛ This whisper has already expired.",
            show_alert=True,
        )
        return

    user_id = callback_query.from_user.id

    # ──────────────────────────────────────────────────────────────────────────
    # SENDER — unlimited reads
    # ──────────────────────────────────────────────────────────────────────────
    if user_id == whisper["sender_id"]:
        await callback_query.answer(
            whisper["text"],
            show_alert=True,
        )
        return

    # ──────────────────────────────────────────────────────────────────────────
    # WRONG USER
    # ──────────────────────────────────────────────────────────────────────────
    if user_id != whisper["recipient_id"]:
        await callback_query.answer(
            "🔒 This whisper is private.\n"
            "Only the sender and intended recipient can read it.",
            show_alert=True,
        )
        return

    # ──────────────────────────────────────────────────────────────────────────
    # RECEIVER — ONE TIME ONLY
    # ──────────────────────────────────────────────────────────────────────────
    # Pop BEFORE displaying → prevents double-read
    _WHISPERS.pop(token, None)

    # Show secret once
    await callback_query.answer(
        whisper["text"],
        show_alert=True,
    )

    # Delete the group whisper message
    try:
        if callback_query.message:
            await callback_query.message.delete()
    except Exception as e:
        print(f"[Whisper delete] {type(e).__name__}: {e}", flush=True)
