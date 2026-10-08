# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/whisper.py — One-Time Receiver Whisper System
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


# Telegram username pattern
_USERNAME_RE = re.compile(
    r"(?<!\w)@([A-Za-z0-9_]{5,32})(?!\w)"
)


# ══════════════════════════════════════════════════════════════════════════════
#  INLINE QUERY
# ══════════════════════════════════════════════════════════════════════════════

@app.on_inline_query()
async def whisper_inline(_, inline_query):

    query = (inline_query.query or "").strip()

    results = []

    # ──────────────────────────────────────────────────────────────────────────
    # 📖 INSTRUCTIONS
    #
    # This is ALWAYS shown when user opens:
    #
    # @ElaraBot
    #
    # It is NOT dependent on a username being present.
    # ──────────────────────────────────────────────────────────────────────────

    instructions = InlineQueryResultArticle(
        id=f"whisper-help-{inline_query.from_user.id}",

        title="📖 Instructions",

        description="How to send and read a Whisper",

        input_message_content=InputTextMessageContent(
            "<b>🤫 Whisper Instructions</b>\n\n"

            "<b>📤 How to send:</b>\n"
            "<code>@ElaraBot your secret message @username</code>\n\n"

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

    # Instructions is always the first inline result.
    results.append(instructions)


    # ══════════════════════════════════════════════════════════════════════════
    #  NO QUERY
    # ══════════════════════════════════════════════════════════════════════════

    # If user only types @ElaraBot, show Instructions.
    if not query:
        await inline_query.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
        return


    # ══════════════════════════════════════════════════════════════════════════
    #  FIND RECIPIENT
    # ══════════════════════════════════════════════════════════════════════════

    matches = list(_USERNAME_RE.finditer(query))

    # No @username yet.
    # Still show Instructions.
    if not matches:
        await inline_query.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
        return


    # Last @username = recipient
    recipient_username = matches[-1].group(1)

    # Everything except recipient username = secret message
    secret_text = (
        query[:matches[-1].start()]
        + query[matches[-1].end():]
    ).strip()

    if not secret_text:
        await inline_query.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
        return


    # ══════════════════════════════════════════════════════════════════════════
    #  RESOLVE USER
    # ══════════════════════════════════════════════════════════════════════════

    try:
        recipient = await app.get_users(recipient_username)
    except Exception:
        await inline_query.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
        return

    if not recipient:
        await inline_query.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
        return

    # Don't allow whispering to bots.
    if recipient.is_bot:
        await inline_query.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
        return


    # ══════════════════════════════════════════════════════════════════════════
    #  CREATE WHISPER TOKEN
    # ══════════════════════════════════════════════════════════════════════════

    token = secrets.token_urlsafe(18)

    _WHISPERS[token] = {
        "sender_id": inline_query.from_user.id,
        "recipient_id": recipient.id,
        "recipient_name": (
            recipient.first_name
            or recipient.username
            or "User"
        ),
        "text": secret_text,
    }


    recipient_name = (
        recipient.first_name
        or recipient.username
        or "User"
    )


    # ══════════════════════════════════════════════════════════════════════════
    #  WHISPER RESULT
    # ══════════════════════════════════════════════════════════════════════════

    whisper_result = InlineQueryResultArticle(
        id=token,

        title=(
            f"Whisper for {recipient_name} "
            f"(@{recipient_username})"
        ),

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


    # Put Whisper below Instructions.
    results.append(whisper_result)


    # ══════════════════════════════════════════════════════════════════════════
    #  ANSWER INLINE QUERY
    # ══════════════════════════════════════════════════════════════════════════

    await inline_query.answer(
        results,
        cache_time=0,
        is_personal=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@app.on_callback_query(filters.regex(r"^wpr:"))
async def whisper_callback(_, callback_query):

    data = callback_query.data or ""


    # ══════════════════════════════════════════════════════════════════════════
    #  HELP / INSTRUCTIONS
    # ══════════════════════════════════════════════════════════════════════════

    if data == "wpr:help":

        await callback_query.answer(
            "🤫 Whisper\n\n"
            "To send:\n"
            "@ElaraBot your secret message @username\n\n"
            "👤 Sender:\n"
            "You can read your Whisper unlimited times.\n\n"
            "🔐 Receiver:\n"
            "Can read it only once.\n\n"
            "🗑️ After the receiver reads it, "
            "the Whisper message is automatically deleted.",
            show_alert=True,
        )

        return


    # ══════════════════════════════════════════════════════════════════════════
    #  GET TOKEN
    # ══════════════════════════════════════════════════════════════════════════

    token = data[4:]

    whisper = _WHISPERS.get(token)


    # Already consumed / expired
    if not whisper:

        await callback_query.answer(
            "⌛ This whisper has already expired.",
            show_alert=True,
        )

        return


    user_id = callback_query.from_user.id


    # ══════════════════════════════════════════════════════════════════════════
    #  SENDER
    #
    # Sender can read unlimited times.
    # Token is NOT removed.
    # Group message is NOT deleted.
    # ══════════════════════════════════════════════════════════════════════════

    if user_id == whisper["sender_id"]:

        await callback_query.answer(
            whisper["text"],
            show_alert=True,
        )

        return


    # ══════════════════════════════════════════════════════════════════════════
    #  WRONG USER
    # ══════════════════════════════════════════════════════════════════════════

    if user_id != whisper["recipient_id"]:

        await callback_query.answer(
            "🔒 This whisper is private.\n"
            "Only the sender and intended recipient can read it.",
            show_alert=True,
        )

        return


    # ══════════════════════════════════════════════════════════════════════════
    #  RECEIVER — ONE TIME ONLY
    # ══════════════════════════════════════════════════════════════════════════

    # Remove BEFORE displaying content.
    #
    # This makes it impossible for the same receiver to successfully
    # consume the whisper twice, even if two callbacks arrive quickly.
    _WHISPERS.pop(token, None)


    # Show secret once.
    await callback_query.answer(
        whisper["text"],
        show_alert=True,
    )


    # ══════════════════════════════════════════════════════════════════════════
    #  DELETE GROUP WHISPER
    # ══════════════════════════════════════════════════════════════════════════

    try:
        if callback_query.message:
            await callback_query.message.delete()

    except Exception as e:
        print(
            f"[Whisper delete] {type(e).__name__}: {e}",
            flush=True,
        )
