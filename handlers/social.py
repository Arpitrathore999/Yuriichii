import random
import re
from pathlib import Path

from pyrogram import filters

from core.bot import app
from modules.social.actions import action

COMMANDS = (
    "hug", "kiss", "bite", "slap", "punch", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce",
)

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "social"
COMMAND_RE = re.compile(r"^/(hug|kiss|bite|slap|punch|cuddle|pat|highfive|flirt|love|crush|couple|propose|marriage|divorce)(?:@[A-Za-z0-9_]+)?(?:\\s+(.*))?$", re.I | re.S)


def _mention(user):
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone"
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    user_id = getattr(user, "id", None)
    return f'<a href="tg://user?id={int(user_id)}">{name}</a>' if user_id else name


async def _get_target(client, message, args):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user

    if args:
        try:
            return await client.get_users(args.strip().split()[0])
        except Exception as e:
            print(f"[SOCIAL TARGET ERROR] {args}: {type(e).__name__}: {e}", flush=True)
    return None


async def _send_result(message, command, text):
    folder = ASSET_ROOT / command
    if not folder.is_dir():
        return await message.reply_text(text, parse_mode="html")

    files = [p for p in folder.iterdir() if p.is_file()]
    if not files:
        return await message.reply_text(text, parse_mode="html")

    media = random.choice(files)
    ext = media.suffix.lower()
    try:
        if ext == ".gif":
            return await message.reply_animation(str(media), caption=text, parse_mode="html")
        if ext in {".mp4", ".webm", ".mkv"}:
            return await message.reply_video(str(media), caption=text, parse_mode="html")
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            return await message.reply_photo(str(media), caption=text, parse_mode="html")
    except Exception as e:
        print(f"[SOCIAL MEDIA ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    return await message.reply_text(text, parse_mode="html")


async def _social_handler(client, message):
    text = (message.text or message.caption or "").strip()
    match = COMMAND_RE.match(text)
    if not match:
        return

    command = match.group(1).lower()
    args = match.group(2) or ""

    if not message.from_user:
        return

    target = await _get_target(client, message, args)
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
        result = await action(message, command, target)
    except Exception as e:
        print(f"[SOCIAL ACTION ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return await message.reply_text(
            "❌ <b>Social command failed.</b>", parse_mode="html"
        )

    return await _send_result(message, command, result)


# Use regex instead of filters.command so both /hug and /hug@BotUsername
# are handled consistently across Pyrogram/Kurigram versions.
app.on_message(filters.regex(COMMAND_RE))(_social_handler)
