from pyrogram import filters
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action, get_gif_file_id

COMMANDS = [
    "hug", "kiss", "bite", "slap", "kick", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]


def _plain(text):
    # Last-resort fallback if a custom caption contains broken HTML.
    import re
    return re.sub(r"<[^>]+>", "", str(text or "")).strip()


@app.on_message(filters.command(COMMANDS))
async def social(_, message):
    command = (message.command[0] if message.command else "").lower().lstrip("/")

    # Target resolution is kept separate so one bad username/reply cannot kill the handler.
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
        return await message.reply(
            f"❌ Reply to a user's message or use /{command} @username."
        )

    if not getattr(target, "id", None):
        return await message.reply("❌ I couldn't identify that user. Please try again.")
    if getattr(target, "is_bot", False):
        return await message.reply("🤖 You can't target a bot with this command.")
    if message.from_user and target.id == message.from_user.id:
        return await message.reply("❌ You can't use this command on yourself.")

    # Caption generation has its own fallbacks, so a custom DB entry cannot stop the command.
    try:
        text = await action(message, command, target)
    except Exception as e:
        print(f"[SOCIAL ACTION ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        text = f"❤️ {getattr(message.from_user, 'first_name', 'Someone')} interacted with {getattr(target, 'first_name', 'someone')}!"

    # Pick one of the admin-added GIFs at random. No GIF = normal text response.
    try:
        gif_file_id = await get_gif_file_id(command)
    except Exception as e:
        print(f"[SOCIAL GIF LOOKUP ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        gif_file_id = None

    if gif_file_id:
        try:
            await message.reply_animation(animation=gif_file_id, caption=text, parse_mode="html")
            return
        except Exception as e:
            print(f"[SOCIAL GIF SEND ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
            # Broken HTML in a custom caption should not make the whole command fail.
            try:
                await message.reply_animation(animation=gif_file_id, caption=_plain(text))
                return
            except Exception as e2:
                print(f"[SOCIAL GIF PLAIN ERROR] /{command}: {type(e2).__name__}: {e2}", flush=True)

    # Final text fallback.
    try:
        await message.reply(text, parse_mode="html")
    except Exception as e:
        print(f"[SOCIAL TEXT HTML ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        try:
            await message.reply(_plain(text))
        except Exception as e2:
            print(f"[SOCIAL TEXT ERROR] /{command}: {type(e2).__name__}: {e2}", flush=True)
