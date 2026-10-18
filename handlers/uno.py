"""UNO Telegram Mini App launcher for Elara.

Set UNO_WEBAPP_URL to the HTTPS URL where uno_web/index.html is hosted.
"""
import os
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from core.bot import app

UNO_WEBAPP_URL = os.getenv("UNO_WEBAPP_URL", "").strip()

@app.on_message(filters.command(["uno", "playuno"]))
async def uno_command(_, message):
    if not UNO_WEBAPP_URL.startswith("https://"):
        await message.reply_text(
            "🃏 **UNO**\n\nUNO Mini App ka interface ready hai, lekin abhi host nahi hua.\n\n"
            "`UNO_WEBAPP_URL` environment variable mein deployed HTTPS URL set karke bot restart karo."
        )
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play UNO", web_app=WebAppInfo(url=UNO_WEBAPP_URL))],
        [InlineKeyboardButton("ℹ️ How to Play", callback_data="uno_help")],
    ])
    await message.reply_photo(
        photo="https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/UNO_Logo.svg/512px-UNO_Logo.svg.png",
        caption=(
            "🃏 **UNO**\n\n"
            "Play UNO with friends! Create a lobby, invite players, or practice against AI.\n\n"
            "🎴 Match the colour or number\n"
            "🔄 Skip · Reverse · Draw Two\n"
            "🌈 Wild · Wild Draw Four"
        ),
        reply_markup=keyboard,
    )

@app.on_callback_query(filters.regex(r"^uno_help$"))
async def uno_help(_, query):
    await query.answer(
        "Match the colour or number. Use action cards wisely and remember to call UNO when one card remains!",
        show_alert=True,
    )
