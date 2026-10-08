"""One-time group whisper system.

Usage in a group (after enabling Inline Mode for the bot):
    @ElaraBot hello, this is secret @username

The inline result posts a locked message to the group. Only the target user can
press "Read content". The secret is shown in a Telegram alert and the whisper
message is deleted immediately after the first successful read.
"""

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

# token -> whisper data. A token is deleted as soon as the intended recipient
# successfully reads it, making the whisper strictly one-time per process.
_WHISPERS: Dict[str, dict] = {}

_USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{5,32})(?!\w)")


@app.on_inline_query()
async def whisper_inline(_, inline_query):
    query = (inline_query.query or "").strip()
    if not query:
        return

    # Recipient is the last @username in the inline query. This lets the
    # sender write naturally: "hello bhai @lovers_rock".
    matches = list(_USERNAME_RE.finditer(query))
    if not matches:
        return

    recipient_username = matches[-1].group(1)
    secret_text = (query[: matches[-1].start()] + query[matches[-1].end() :]).strip()
    if not secret_text:
        return

    try:
        recipient = await app.get_users(recipient_username)
    except Exception:
        return

    if not recipient or recipient.is_bot:
        return

    token = secrets.token_urlsafe(18)
    _WHISPERS[token] = {
        "sender_id": inline_query.from_user.id,
        "recipient_id": recipient.id,
        "recipient_name": recipient.first_name or recipient.username or "User",
        "text": secret_text,
    }

    # Telegram's inline-result cache is disabled so each generated token is
    # unique and cannot accidentally be reused by another user.
    result = InlineQueryResultArticle(
        id=token,
        title=f"Whisper for {recipient.first_name or recipient_username} (@{recipient_username})",
        description="Only the selected user can read this message • One-time read",
        input_message_content=InputTextMessageContent(
            f"🔒 <b>Whisper for {recipient.first_name or recipient_username}.</b>\n"
            "Only they can read the content.\n\n"
            "<i>⚠️ This whisper expires after it is read once.</i>"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("👁️ Read content", callback_data=f"wpr:{token}")],
                [InlineKeyboardButton("↗️ How to send a whisper?", callback_data="wpr:help")],
            ]
        ),
    )

    await inline_query.answer([result], cache_time=0, is_personal=True)


@app.on_callback_query(filters.regex(r"^wpr:"))
async def whisper_callback(_, callback_query):
    data = callback_query.data or ""

    if data == "wpr:help":
        await callback_query.answer(
            "Use inline mode in a group:\n\n"
            "@ElaraBot your secret message @username\n\n"
            "Select the Whisper result and send it. Only @username can read it, and it expires after the first successful read.",
            show_alert=True,
        )
        return

    token = data[4:]
    whisper = _WHISPERS.get(token)
    if not whisper:
        await callback_query.answer(
            "⌛ This whisper has already expired or is no longer available.",
            show_alert=True,
        )
        return

    if callback_query.from_user.id != whisper["recipient_id"]:
        await callback_query.answer(
            "🔒 This whisper is private. Only the intended recipient can read it.",
            show_alert=True,
        )
        return

    # Consume before showing the content. This prevents a second successful
    # callback from racing the first one and reading the same whisper twice.
    _WHISPERS.pop(token, None)

    await callback_query.answer(whisper["text"], show_alert=True)

    # Remove the group message immediately after the first successful read.
    try:
        await callback_query.message.delete()
    except Exception:
        pass
