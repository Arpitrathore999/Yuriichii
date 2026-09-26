import random
import re
from pathlib import Path

from pyrogram import filters

from core.bot import app
from modules.social.actions import action

COMMANDS = [
    "hug", "kiss", "bite", "slap", "punch", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce",
]

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "social"
COMMAND_RE = re.compile(r"^/(%s)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?$" % "|".join(map(re.escape, COMMANDS)), re.I)


def _mention(user):
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone"
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={int(user.id)}">{name}</a>'


async def _get_target(client, message, arg):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    if arg:
        try:
            return await client.get_users(arg.strip().split()[0])
        except Exception as e:
            print(f"[SOCIAL TARGET ERROR] {type(e).__name__}: {e}", flush=True)
    return None


async def _send_result(message, command, text):
    folder = ASSET_ROOT / command
    files = [p for p in folder.iterdir() if p.is_file()] if folder.is_dir() else []
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
    raw = (message.text or message.caption or "").strip()
    match = COMMAND_RE.match(raw)
    if not match:
        return

    command = match.group(1).lower()
    arg = match.group(2)

    if not message.from_user:
        return

    target = await _get_target(client, message, arg)
    if not target:
        return await message.reply_text(
            f"❌ <b>Reply to a user's message</b> or use <code>/{command} @username</code>.",
            parse_mode="html",
        )

    if getattr(target, "is_bot", False):
        return await message.reply_text("🤖 <b>Bots are not valid targets.</b>", parse_mode="html")
    if target.id == message.from_user.id:
        return await message.reply_text("❌ <b>You can't use this on yourself. 😭</b>", parse_mode="html")

    try:
        text = await action(message, command, target)
    except Exception as e:
        print(f"[SOCIAL HANDLER ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return await message.reply_text(
            "❌ <b>Social command failed.</b>\n<code>Check the bot logs.</code>",
            parse_mode="html",
        )
    return await _send_result(message, command, text)


# Regex is used instead of filters.command so both /hug and /hug@BotUsername
# are handled consistently on the installed Kurigram/Pyrogram-compatible API.
app.on_message(filters.regex(COMMAND_RE))(_social_handler)
