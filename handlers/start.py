from pyrogram import filters
from core.bot import app
from database.users import ensure_user

@app.on_message(filters.command("start"))
async def start(_, message):
    await ensure_user(message.from_user)
    await message.reply(
        "🌙 **Hey, I'm Elara!**\n\n"
        "💬 Talk to me normally in DM.\n"
        "🤖 `/ai hello` for a direct AI chat.\n\n"
        "💕 Social commands ke liye kisi user ke message par reply karke command use karo."
    )
