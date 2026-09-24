from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import config

def start_keyboard():
    bot_username = getattr(config, "BOT_USERNAME", "")
    add_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛩️ ADD ME TO A GROUP ⛩️", url=add_url)],
        [
            InlineKeyboardButton("🍬 SUPPORT 🍬", url=getattr(config, "SUPPORT_URL", "") or "https://t.me/"),
            InlineKeyboardButton("🍹 UPDATES 🍹", url=getattr(config, "UPDATES_URL", "") or "https://t.me/"),
        ],
        [InlineKeyboardButton("🏩 HELP & COMMANDS 🏩", callback_data="elara_help")],
        [
            InlineKeyboardButton("👑 OWNER", url=getattr(config, "OWNER_URL", "") or "https://t.me/"),
            InlineKeyboardButton("🍡 SOURCE", url=getattr(config, "SOURCE_URL", "") or "https://t.me/"),
        ],
    ])

def help_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 AI", callback_data="elara_help_ai"),
            InlineKeyboardButton("💕 SOCIAL", callback_data="elara_help_social"),
        ],
        [InlineKeyboardButton("✦ CLOSE ✦", callback_data="elara_help_close")],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ BACK TO HELP", callback_data="elara_help")]
    ])
