from pyrogram import filters
from core.bot import app
import config

def owner_only(message):
    return bool(message.from_user and message.from_user.id == config.OWNER_ID)

@app.on_message(filters.command("stats"))
async def stats(_, message):
    if not owner_only(message):
        return
    await message.reply("📊 **Elara Stats**\n\nBot is online and modular.")
