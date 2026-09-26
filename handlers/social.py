import random
from pathlib import Path

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.bot import app
from modules.social.actions import action, get_local_media
from modules.social.settings import COMMANDS
from modules.social.relationship import get_status, set_status, clear_status

COMMANDS = tuple(c.lower() for c in COMMANDS)


def target_from_reply(message):
    reply = message.reply_to_message
    return reply.from_user if reply else None


def mention(user):
    name = (getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone")
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def send_social(message, command, target):
    # modules/social/actions.py handles captions + relationship state.
    result = await action(message, command, target)
    if not result:
        return

    media = get_local_media(command)
    if not media:
        return await message.reply_text(result, parse_mode="html")

    try:
        ext = Path(media).suffix.lower()
        if ext in {".mp4", ".webm", ".mkv"}:
            return await message.reply_video(media, caption=result, parse_mode="html")
        if ext == ".gif":
            return await message.reply_animation(media, caption=result, parse_mode="html")
        return await message.reply_photo(media, caption=result, parse_mode="html")
    except Exception as e:
        print(f"[SOCIAL SEND ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return await message.reply_text(result, parse_mode="html")


async def social_dispatch(client, message):
    command = (message.command or [""])[0].lower()
    if command not in COMMANDS:
        return

    target = target_from_reply(message)
    if not target:
        return await message.reply_text(
            "❌ <b>Reply to a user's message first.</b>\n<i>Social commands use reply-only targeting. 💕</i>",
            parse_mode="html",
        )

    if getattr(target, "is_bot", False):
        return await message.reply_text("🤖 <b>Bots don't have feelings... pick a real human. 😭</b>", parse_mode="html")

    if not message.from_user or target.id == message.from_user.id:
        return await message.reply_text("❌ <b>You can't use this on yourself. 😏</b>", parse_mode="html")

    return await send_social(message, command, target)


@app.on_message(filters.command(COMMANDS))
async def social_commands(client, message):
    try:
        await social_dispatch(client, message)
    except Exception as e:
        print(f"[SOCIAL DISPATCH ERROR] {type(e).__name__}: {e}", flush=True)
        try:
            await message.reply_text("❌ <b>Social command failed.</b> Please check the bot logs.", parse_mode="html")
        except Exception:
            pass
