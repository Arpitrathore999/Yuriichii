from pyrogram import filters
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action

COMMANDS = [
    "hug", "kiss", "bite", "slap", "kick", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]

@app.on_message(filters.command(COMMANDS))
async def social(_, message):
    command = (message.command[0] if message.command else "").lower().lstrip("/")

    # /couple is handled like every other social command when replying to a user.
    target = get_reply_target(message)

    # Also support: /hug @username
    if target is None and len(message.command or []) >= 2:
        username = message.command[1].lstrip("@").strip()
        if username:
            try:
                target = await app.get_users(username)
            except Exception:
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

    try:
        text = await action(message, command, target)
        # Social captions previously used Markdown while the handler forced HTML.
        # Send the final caption as plain text so Telegram cannot reject malformed
        # formatting because of a user's name or caption text.
        await message.reply(text, parse_mode=None)
    except Exception as e:
        print(f"[SOCIAL ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return await message.reply(
            "❌ I couldn't process that social command right now. Please try again."
        )
