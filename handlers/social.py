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
    command = (message.command or [""])[0].lower()

    # /couple is a special command; it can be extended later with a random-group picker.
    if command == "couple":
        return await message.reply("💞 Use /couple by replying to a member's message to create today's couple.")

    target = get_reply_target(message)

    # Also support: /hug @username
    if target is None and len(message.command or []) >= 2:
        username = message.command[1].lstrip("@")
        try:
            target = await app.get_users(username)
        except Exception:
            target = None

    if not target:
        return await message.reply("❌ Reply to a user's message or use /hug @username.")

    if target.is_bot:
        return await message.reply("🤖 You can't target a bot with this command.")
    if message.from_user and target.id == message.from_user.id:
        return await message.reply("❌ You can't use this command on yourself.")

    try:
        text = await action(message, command, target)
        # Captions are HTML, so keep the parse mode consistent.
        await message.reply(text, parse_mode="html")
    except Exception as e:
        print(f"[SOCIAL ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        await message.reply("❌ I couldn't process that social command right now. Please try again.")
