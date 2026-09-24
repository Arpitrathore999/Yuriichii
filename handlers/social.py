from pyrogram import filters
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action, get_gif_file_id

COMMANDS = [
    "hug", "kiss", "bite", "slap", "kick", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]


@app.on_message(filters.command(COMMANDS))
async def social(_, message):
    command = (message.command[0] if message.command else "").lower().lstrip("/")

    try:
        target = get_reply_target(message)

        if target is None and len(message.command or []) >= 2:
            username = message.command[1].lstrip("@").strip()
            if username:
                try:
                    target = await app.get_users(username)
                except Exception as e:
                    print(f"[SOCIAL TARGET ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
                    target = None

        if target is None:
            return await message.reply(
                "❌ Reply to a user's message or use /%s @username." % command
            )

        if not getattr(target, "id", None):
            return await message.reply("❌ I couldn't identify that user. Please try again.")
        if getattr(target, "is_bot", False):
            return await message.reply("🤖 You can't target a bot with this command.")
        if message.from_user and target.id == message.from_user.id:
            return await message.reply("❌ You can't use this command on yourself.")

        text = await action(message, command, target)
        gif_file_id = await get_gif_file_id(command)

        if gif_file_id:
            try:
                await message.reply_animation(
                    animation=gif_file_id,
                    caption=text,
                    parse_mode="html",
                )
                return
            except Exception as gif_error:
                print(
                    f"[SOCIAL GIF ERROR] /{command}: {type(gif_error).__name__}: {gif_error}",
                    flush=True,
                )

        await message.reply(text, parse_mode="html")

    except Exception as e:
        print(f"[SOCIAL ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return await message.reply(
            "❌ I couldn't process that social command right now. Please try again."
        )
