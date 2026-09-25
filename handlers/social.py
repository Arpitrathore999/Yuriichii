from pathlib import Path

from pyrogram import filters
from pyrogram.enums import ParseMode
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action, get_gif_file_id

COMMANDS = [
    "hug", "kiss", "bite", "slap", "kick", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]


def _plain(text):
    import re
    return re.sub(r"<[^>]+>", "", str(text or "")).strip()


async def _send_media(message, media_path, caption):
    """Send local media using the correct Telegram method for its extension."""
    ext = Path(str(media_path)).suffix.lower()

    if ext == ".gif":
        await message.reply_animation(animation=str(media_path), caption=caption, parse_mode=ParseMode.HTML)
    elif ext == ".mp4":
        await message.reply_video(video=str(media_path), caption=caption, parse_mode=ParseMode.HTML, supports_streaming=True)
    elif ext in {".jpg", ".jpeg", ".png", ".webp"}:
        await message.reply_photo(photo=str(media_path), caption=caption, parse_mode=ParseMode.HTML)
    elif ext == ".webm":
        # Telegram/Pyrogram may not accept WebM as a normal video in every setup.
        await message.reply_document(document=str(media_path), caption=caption, parse_mode=ParseMode.HTML)
    else:
        raise ValueError(f"Unsupported social media extension: {ext}")


@app.on_message(filters.command(COMMANDS, prefixes=["/", ".", "!", "#"]))
async def social(_, message):
    command = (message.command[0] if message.command else "").lower().lstrip("/")

    try:
        target = get_reply_target(message)
    except Exception as e:
        print(f"[SOCIAL TARGET ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        target = None

    if target is None and len(message.command or []) >= 2:
        username = str(message.command[1]).lstrip("@").strip()
        if username:
            try:
                target = await app.get_users(username)
            except Exception as e:
                print(f"[SOCIAL USER ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    if target is None:
        return await message.reply(f"❌ Reply to a user's message or use /{command} @username.")

    if not getattr(target, "id", None):
        return await message.reply("❌ I couldn't identify that user. Please try again.")
    if getattr(target, "is_bot", False):
        return await message.reply("🤖 You can't target a bot with this command.")
    if message.from_user and target.id == message.from_user.id:
        return await message.reply("❌ You can't use this command on yourself.")

    try:
        text = await action(message, command, target)
    except Exception as e:
        print(f"[SOCIAL ACTION ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        text = f"❤️ {getattr(message.from_user, 'first_name', 'Someone')} interacted with {getattr(target, 'first_name', 'someone')}!"

    # Local assets/social/<command> is checked first. DB file IDs remain a fallback.
    try:
        media = await get_gif_file_id(command)
    except Exception as e:
        print(f"[SOCIAL MEDIA LOOKUP ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        media = None

    if media:
        try:
            await _send_media(message, media, text)
            return
        except Exception as e:
            print(f"[SOCIAL MEDIA SEND ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
            # Retry without HTML if a caption formatting issue caused the failure.
            try:
                await _send_media(message, media, _plain(text))
                return
            except Exception as e2:
                print(f"[SOCIAL MEDIA PLAIN ERROR] /{command}: {type(e2).__name__}: {e2}", flush=True)

    try:
        await message.reply(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"[SOCIAL TEXT HTML ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        await message.reply(_plain(text))
