import random
from pathlib import Path

from pyrogram import filters

from core.bot import app
from modules.social.actions import action, get_local_media

COMMANDS = [
    "hug", "kiss", "bite", "slap", "punch", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce",
]

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "social"


def _mention(user):
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone"
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={int(user.id)}">{name}</a>'


async def _get_target(client, message):
    # Preferred: reply to a user's message.
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user

    # Also support: /hug @username or /hug user_id
    args = message.command[1:] if message.command else []
    if args:
        try:
            return await client.get_users(args[0])
        except Exception:
            return None

    return None


async def _send_result(message, command, text):
    folder = ASSET_ROOT / command
    files = []
    if folder.is_dir():
        files = [p for p in folder.iterdir() if p.is_file()]

    if not files:
        return await message.reply_text(text, parse_mode="html")

    media = random.choice(files)
    try:
        ext = media.suffix.lower()
        if ext == ".gif":
            return await message.reply_animation(str(media), caption=text, parse_mode="html")
        if ext in {".mp4", ".webm", ".mkv"}:
            return await message.reply_video(str(media), caption=text, parse_mode="html")
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            return await message.reply_photo(str(media), caption=text, parse_mode="html")
    except Exception as e:
        print(f"[SOCIAL MEDIA SEND ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    return await message.reply_text(text, parse_mode="html")


async def _social_handler(client, message):
    command = (message.command[0].lower() if message.command else "")
    if command not in COMMANDS:
        return

    target = await _get_target(client, message)
    if not target:
        return await message.reply_text(
            "❌ <b>Reply to a user's message</b> or use <code>/" + command + " @username</code>.",
            parse_mode="html",
        )

    if getattr(target, "is_bot", False):
        return await message.reply_text("🤖 <b>Bots are not valid targets.</b>", parse_mode="html")

    if target.id == message.from_user.id:
        return await message.reply_text("❌ <b>You can't use this on yourself. 😭</b>", parse_mode="html")

    try:
        # Existing module contains the caption/relationship logic.
        text = await action(message, command, target)
    except Exception as e:
        print(f"[SOCIAL HANDLER ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return await message.reply_text(
            "❌ <b>Social command failed.</b>\n<code>Check the bot logs.</code>",
            parse_mode="html",
        )

    return await _send_result(message, command, text)


# Register one command at a time. This works with both Pyrogram/Kurigram command-filter APIs.
for _command in COMMANDS:
    app.on_message(filters.command(_command))(_social_handler)
