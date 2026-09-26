from pathlib import Path

from pyrogram import filters
from pyrogram.enums import ParseMode
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action, get_gif_file_id
from modules.social.settings import DEFAULT_CAPTIONS

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


async def _get_random_members(client, chat_id, exclude_ids=()):
    excluded = {int(x) for x in exclude_ids if x}
    members = []
    try:
        async for member in client.get_chat_members(chat_id):
            user = member.user
            if not user or user.is_bot or user.id in excluded:
                continue
            members.append(user)
    except Exception as e:
        print(f"[SOCIAL MEMBERS ERROR]: {type(e).__name__}: {e}", flush=True)
    return members


def _mention(user):
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone"
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={int(user.id)}">{name}</a>'


def _special_caption(command, a, b):
    pool = DEFAULT_CAPTIONS.get(command) or ["{a} ❤️ {b}"]
    template = __import__("random").choice(pool)
    return template.format(a=a, b=b, pct=__import__("random").randint(1, 100))


async def _send_social_random_media(message, command, caption):
    try:
        media = await get_gif_file_id(command)
    except Exception as e:
        print(f"[SOCIAL MEDIA LOOKUP ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        media = None
    if media:
        try:
            await _send_media(message, media, caption)
            return
        except Exception as e:
            print(f"[SOCIAL MEDIA SEND ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
            try:
                await _send_media(message, media, _plain(caption))
                return
            except Exception as e2:
                print(f"[SOCIAL MEDIA PLAIN ERROR] /{command}: {type(e2).__name__}: {e2}", flush=True)
    try:
        await message.reply(caption, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply(_plain(caption))


@app.on_message(filters.command(COMMANDS, prefixes=["/", ".", "!", "#"]))
async def social(_, message):
    command = (message.command[0] if message.command else "").lower().lstrip("/!.#")

    # /crush: reply to B's message. B is the person whose crush is being found.
    # The command sender is excluded from the candidate list.
    if command == "crush":
        target = None
        try:
            target = get_reply_target(message)
        except Exception as e:
            print(f"[SOCIAL CRUSH TARGET ERROR]: {type(e).__name__}: {e}", flush=True)
        if not target:
            return await message.reply("❌ Reply to the user's message whose crush you want to find.")
        if getattr(target, "is_bot", False):
            return await message.reply("🤖 Bots don't have crushes. 😭")
        if not getattr(target, "id", None):
            return await message.reply("❌ I couldn't identify that user.")

        excluded = {target.id}
        if message.from_user:
            excluded.add(message.from_user.id)
        candidates = await _get_random_members(message._client, message.chat.id, excluded)
        if not candidates:
            return await message.reply("❌ Not enough members to find a random crush. 😭")

        crush = __import__("random").choice(candidates)
        caption = _special_caption("crush", _mention(target), _mention(crush))
        return await _send_social_random_media(message, "crush", caption)

    # /couple: no reply/tag required. Pick two random non-bot members from the GC.
    if command == "couple":
        candidates = await _get_random_members(message._client, message.chat.id)
        if len(candidates) < 2:
            return await message.reply("❌ Need at least 2 non-bot members for a random couple. 💞")

        x, y = __import__("random").sample(candidates, 2)
        caption = _special_caption("couple", _mention(x), _mention(y))
        return await _send_social_random_media(message, "couple", caption)

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

    await _send_social_random_media(message, command, text)
