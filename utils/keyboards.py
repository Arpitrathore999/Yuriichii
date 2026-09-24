from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import config

def start_keyboard():
    rows = [
        [InlineKeyboardButton("💬 CHAT WITH ELARA ›", callback_data="elara:chat")],
        [
            InlineKeyboardButton("📖 ABOUT ›", callback_data="elara:about"),
            InlineKeyboardButton("💕 SOCIAL ›", callback_data="elara:social"),
        ],
        [InlineKeyboardButton("❓ HELP & COMMANDS ›", callback_data="elara:help")],
        [
            InlineKeyboardButton("📢 UPDATES ›", url=config.UPDATES_URL or "https://t.me/"),
            InlineKeyboardButton("👑 OWNER ›", url=config.OWNER_URL or "https://t.me/"),
        ],
    ]
    return InlineKeyboardMarkup(rows)

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ BACK", callback_data="elara:home")]
    ])
