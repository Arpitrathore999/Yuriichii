from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import config

def start_keyboard():
    bot_username = getattr(config, "BOT_USERNAME", "")
    add_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛩️ ADD ME TO A GROUP ⛩️", url=add_url, style=enums.ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton("🍬 SUPPORT 🍬", url=getattr(config, "SUPPORT_URL", "") or "https://t.me/", style=enums.ButtonStyle.SUCCESS),
            InlineKeyboardButton("🍹 UPDATES 🍹", url=getattr(config, "UPDATES_URL", "") or "https://t.me/", style=enums.ButtonStyle.SUCCESS),
        ],
        [InlineKeyboardButton("🏩 HELP & COMMANDS 🏩", callback_data="elara_help", style=enums.ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton("👑 OWNER", url=getattr(config, "OWNER_URL", "") or "https://t.me/", style=enums.ButtonStyle.DANGER),
            InlineKeyboardButton("🍡 SOURCE", url=getattr(config, "SOURCE_URL", "") or "https://t.me/", style=enums.ButtonStyle.DANGER),
        ],
    ])

def help_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 AI", callback_data="elara_help_ai", style=enums.ButtonStyle.PRIMARY),
            InlineKeyboardButton("💕 SOCIAL", callback_data="elara_help_social", style=enums.ButtonStyle.SUCCESS),
        ],
        [InlineKeyboardButton("✦ CLOSE ✦", callback_data="elara_help_close", style=enums.ButtonStyle.DANGER)],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ BACK TO HELP", callback_data="elara_help", style=enums.ButtonStyle.PRIMARY)]
    ])
