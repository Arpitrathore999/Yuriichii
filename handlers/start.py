import asyncio

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from core.bot import app
from database.users import ensure_user
import config


def esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def start_keyboard():
    bot_username = getattr(config, "BOT_USERNAME", "")
    add_url = (
        f"https://t.me/{bot_username}?startgroup=true"
        if bot_username
        else "https://t.me/"
    )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⛩️ ᴀᴅᴅ мᴇ ʙᴀʙʏ ⛩️",
                url=add_url,
            )
        ],
        [
            InlineKeyboardButton(
                "🍬 sᴜᴘᴘᴏʀᴛ 🍬",
                url=getattr(config, "SUPPORT_URL", "") or "https://t.me/",
            ),
            InlineKeyboardButton(
                "🍹 ᴜᴘᴅᴀᴛᴇs 🍹",
                url=getattr(config, "UPDATES_URL", "") or "https://t.me/",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
                callback_data="elara_help",
            )
        ],
        [
            InlineKeyboardButton(
                "🫧 ᴏᴡɴᴇʀ 🫧",
                url=getattr(config, "OWNER_URL", "") or "https://t.me/",
            ),
            InlineKeyboardButton(
                "🍡 sᴏᴜʀᴄᴇ 🍡",
                url=getattr(config, "SOURCE_URL", "") or "https://t.me/",
            ),
        ],
    ])


def help_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 ᴀɪ", callback_data="elara_help_ai"),
            InlineKeyboardButton("💕 sᴏᴄɪᴀʟ", callback_data="elara_help_social"),
        ],
        [
            InlineKeyboardButton("⌯ ᴄʟᴏsᴇ ⌯", callback_data="elara_help_close"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⌯ ʙᴀᴄᴋ ⌯", callback_data="elara_help")]
    ])


def home_text(name):
    return f"""
❍ <b>ʜᴇʏ <a href="tg://user?id={{uid}}">{esc(name)}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🌙</b>

ɪ ᴀᴍ <b>ᴇʟᴀʀᴀ</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ
ᴛᴇʟᴇɢʀᴀᴍ ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ғᴏʀ
ᴄʜᴀᴛs, ᴄʜᴀᴏs &amp; ʟᴀᴛᴇ-ɴɪɢʜᴛ ᴛᴀʟᴋs. ✨

✦ <b>ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs</b> ✦

<code>┌──────────────────────────────┐
│  ғᴇᴀᴛᴜʀᴇ          ᴅᴇᴛᴀɪʟs  │
├──────────────────────────────┤
│  💬 ᴀɪ ᴄʜᴀᴛ       ɴᴀᴛᴜʀᴀʟ  │
│                   ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs │
├──────────────────────────────┤
│  🧠 ᴍᴇᴍᴏʀʏ        ʀᴇᴄᴇɴᴛ  │
│                   ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ │
├──────────────────────────────┤
│  💕 sᴏᴄɪᴀʟ        ғᴜɴ ɢʀᴏᴜᴘ │
│                   ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs │
├──────────────────────────────┤
│  ⚡ ғᴀsᴛ           ǫᴜɪᴄᴋ ᴀɪ │
│                   ʀᴇsᴘᴏɴsᴇs │
└──────────────────────────────┘</code>

✧ <b>ᴡʜʏ ᴄʜᴏᴏsᴇ ᴇʟᴀʀᴀ?</b> ✧

⭐ sɪᴍᴘʟᴇ ᴄʜᴀᴛ — ɴᴏ ᴄᴏᴍᴘʟɪᴄᴀᴛᴇᴅ sᴇᴛᴜᴘ.
🧠 ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴄᴏɴᴛᴇxᴛ ғᴏʀ ᴍᴏʀᴇ ɴᴀᴛᴜʀᴀʟ ᴄʜᴀᴛs.
💕 sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅs ғᴏʀ ʏᴏᴜʀ ɢʀᴏᴜᴘs.
❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.

<b>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » ᴇʟᴀʀᴀ ᴀɪ</b>
"""


HELP_HOME = """
📜 <b>ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ</b>

❍ ᴘɪᴄᴋ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ ᴛᴏ sᴇᴇ ɪᴛs ᴄᴏᴍᴍᴀɴᴅs.

✦ <b>ʜᴇʟᴘ ғᴇᴀᴛᴜʀᴇs</b> ✦

<code>┌──────────────────────────────┐
│ 🤖 ᴀɪ      ᴄʜᴀᴛ &amp; ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ │
│ 💕 sᴏᴄɪᴀʟ  ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs │
└──────────────────────────────┘</code>

❍ ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ.
"""


AI_HELP = """
🤖 <b>ᴇʟᴀʀᴀ ᴀɪ</b>

✦ <b>ᴄʜᴀᴛ</b>
<code>/ai hello</code> — ᴅɪʀᴇᴄᴛ ᴀɪ ᴄʜᴀᴛ

❍ ᴅᴍ ᴍᴇssᴀɢᴇ
sᴇɴᴅ ᴀ ɴᴏʀᴍᴀʟ ᴍᴇssᴀɢᴇ ᴀɴᴅ ᴇʟᴀʀᴀ ᴡɪʟʟ ʀᴇᴘʟʏ.

✦ <b>ɢʀᴏᴜᴘ ᴄʜᴀᴛ</b>
• <code>Elara hello</code>
• <code>@BotUsername hello</code>
• ʀᴇᴘʟʏ ᴛᴏ ᴇʟᴀʀᴀ

✦ <b>🧠 ᴍᴇᴍᴏʀʏ</b>
ᴇʟᴀʀᴀ ᴜsᴇs ʀᴇᴄᴇɴᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴄᴏɴᴛᴇxᴛ
ᴛᴏ ᴍᴀᴋᴇ ʀᴇᴘʟɪᴇs ᴍᴏʀᴇ ɴᴀᴛᴜʀᴀʟ.
"""


SOCIAL_HELP = """
💕 <b>ᴇʟᴀʀᴀ sᴏᴄɪᴀʟ</b>

❍ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ's ᴍᴇssᴀɢᴇ ғɪʀsᴛ.

<code>🫂 /hug        💋 /kiss
🧛 /bite       👋 /slap
🦵 /kick       🫶 /cuddle
🫳 /pat        ✋ /highfive
😏 /flirt      ❤️ /love
💘 /crush      💞 /couple
💍 /propose    💒 /marriage
💔 /divorce</code>

✦ <i>ʀᴇᴘʟʏ → ᴄᴏᴍᴍᴀɴᴅ → ᴇɴᴊᴏʏ</i> ✦
"""


async def edit_message(query: CallbackQuery, text, markup):
    try:
        await query.message.edit_caption(text, reply_markup=markup)
    except Exception:
        try:
            await query.message.edit_text(text, reply_markup=markup)
        except Exception:
            pass


@app.on_message(filters.command("start"))
async def start(_, message):
    if message.from_user:
        await ensure_user(message.from_user)

    name = esc(message.from_user.first_name or "there")
    text = home_text(name).format(uid=message.from_user.id)

    try:
        await message.delete()
    except Exception:
        pass

    if getattr(config, "START_IMAGE_URL", ""):
        try:
            await message.reply_photo(
                config.START_IMAGE_URL,
                caption=text,
                reply_markup=start_keyboard(),
            )
            return
        except Exception:
            pass

    await message.reply_text(text, reply_markup=start_keyboard())


@app.on_message(filters.command("help"))
async def help_command(_, message):
    try:
        await message.delete()
    except Exception:
        pass

    await message.reply_text(HELP_HOME, reply_markup=help_keyboard())


@app.on_callback_query(filters.regex(r"^elara_help$"))
async def help_home(_, query: CallbackQuery):
    await query.answer()
    await edit_message(query, HELP_HOME, help_keyboard())


@app.on_callback_query(filters.regex(r"^elara_help_ai$"))
async def help_ai(_, query: CallbackQuery):
    await query.answer()
    await edit_message(query, AI_HELP, back_keyboard())


@app.on_callback_query(filters.regex(r"^elara_help_social$"))
async def help_social(_, query: CallbackQuery):
    await query.answer()
    await edit_message(query, SOCIAL_HELP, back_keyboard())


@app.on_callback_query(filters.regex(r"^elara_help_close$"))
async def help_close(_, query: CallbackQuery):
    await query.answer("Closed.")
    try:
        await query.message.delete()
    except Exception:
        pass
