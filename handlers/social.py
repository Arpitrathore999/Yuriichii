from pyrogram import filters
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action

COMMANDS = [
    "hug", "kiss", "bite", "slap", "kick", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]

# Explicitly register social commands. These are processed before any generic
# AI/text handler can consume them.
@app.on_message(filters.command(COMMANDS))
async def social(_, message):
    command = (message.command or [""])[0].split("@")[0].lower()

    target = get_reply_target(message)
    if not target:
        return await message.reply(
            "❌ Kisi user ke message par **reply** karke command use karo."
        )

    if target.is_bot:
        return await message.reply("🤖 Bot ko target mat karo 😭")
    if not message.from_user:
        return await message.reply("❌ User information nahi mili.")
    if target.id == message.from_user.id:
        return await message.reply("❌ Khud par ye command nahi chalegi 😭")

    try:
        text = await action(message, command, target)
        await message.reply(text, parse_mode="html")
    except Exception as e:
        # Keep the bot alive and return a useful error instead of silently
        # making the command appear broken.
        print(f"[SOCIAL ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        await message.reply("❌ Social command abhi process nahi ho paya. Dobara try karo.")
