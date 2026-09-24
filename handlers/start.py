from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from core.bot import app
from database.users import ensure_user
import config

WELCOME = """
❍ <b>HEY {name}, WELCOME ABOARD! 🌙</b>

I AM <b>ELARA</b> — YOUR AI COMPANION FOR
CONVERSATIONS, CHAOS & LATE-NIGHT TALKS. ✨

<b>✦ KEY FEATURES ✦</b>

┌──────────────────────────────┐
│ 💬 <b>AI CHAT</b>              │
│    Natural AI conversations  │
├──────────────────────────────┤
│ 🧠 <b>MEMORY</b>               │
│    Remembers recent chats    │
├──────────────────────────────┤
│ 💕 <b>SOCIAL</b>               │
│    Fun group interactions    │
├──────────────────────────────┤
│ ⚡ <b>FAST</b>                  │
│    Quick AI responses        │
└──────────────────────────────┘

✦ <i>Just talk to Elara — no complicated setup.</i> ✦
"""

HELP_HOME = """
📜 <b>ELARA HELP & COMMANDS</b>

❍ Choose a category below to view
its commands and features.

<b>🤖 AI</b>
Chat with Elara and use her AI features.

<b>💕 SOCIAL</b>
Fun interactions with other members.

<i>All social commands work by replying
to the target user's message.</i>
"""

AI_HELP = """
🤖 <b>ELARA AI</b>

<b>💬 CHAT</b>
• Send a normal message in DM
• <code>/ai hello</code> — direct AI chat

<b>👥 GROUP CHAT</b>
• <code>Elara hello</code>
• <code>@BotUsername hello</code>
• Reply to Elara's message

<b>🧠 MEMORY</b>
Elara keeps recent conversation context
for a more natural chat experience. 🌙
"""

SOCIAL_HELP = """
💕 <b>ELARA SOCIAL</b>

Reply to another user's message:

🫂 <code>/hug</code>      💋 <code>/kiss</code>
🧛 <code>/bite</code>     👋 <code>/slap</code>
🦵 <code>/kick</code>     🫶 <code>/cuddle</code>
🫳 <code>/pat</code>      ✋ <code>/highfive</code>
😏 <code>/flirt</code>    ❤️ <code>/love</code>
💘 <code>/crush</code>    💞 <code>/couple</code>
💍 <code>/propose</code>  💒 <code>/marriage</code>
💔 <code>/divorce</code>

<i>Tip: Reply first, then send the command.</i>
"""

def home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⛩️ ADD ME TO A GROUP ⛩️",
                url=f"https://t.me/{config.BOT_USERNAME}?startgroup=true"
                if config.BOT_USERNAME else "https://t.me/",
            )
        ],
        [
            InlineKeyboardButton("🍬 SUPPORT 🍬", url=config.SUPPORT_URL or "https://t.me/"),
            InlineKeyboardButton("🍹 UPDATES 🍹", url=config.UPDATES_URL or "https://t.me/"),
        ],
        [
            InlineKeyboardButton("🏩 HELP & COMMANDS 🏩", callback_data="elara_help"),
        ],
        [
            InlineKeyboardButton("👑 OWNER", url=config.OWNER_URL or "https://t.me/"),
            InlineKeyboardButton("🍡 SOURCE", url=config.SOURCE_URL or "https://t.me/"),
        ],
    ])

def help_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 AI", callback_data="elara_help_ai"),
            InlineKeyboardButton("💕 SOCIAL", callback_data="elara_help_social"),
        ],
        [
            InlineKeyboardButton("✦ CLOSE ✦", callback_data="elara_help_close"),
        ],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ BACK TO HELP", callback_data="elara_help")]
    ])

def _text_name(user):
    return (user.first_name or "there").replace("<", "").replace(">", "")

async def _edit(query, text, markup):
    try:
        if query.message.caption is not None:
            await query.message.edit_caption(text, reply_markup=markup)
        else:
            await query.message.edit_text(text, reply_markup=markup)
    except Exception:
        try:
            await query.message.edit_text(text, reply_markup=markup)
        except Exception:
            pass

@app.on_message(filters.command("start"))
async def start(_, message):
    if message.from_user:
        await ensure_user(message.from_user)

    name = _text_name(message.from_user)
    text = WELCOME.format(name=name)

    if config.START_IMAGE_URL:
        try:
            await message.reply_photo(
                config.START_IMAGE_URL,
                caption=text,
                reply_markup=home_keyboard(),
            )
            return
        except Exception:
            pass

    await message.reply_text(text, reply_markup=home_keyboard())

@app.on_message(filters.command("help"))
async def help_command(_, message):
    await message.reply_text(HELP_HOME, reply_markup=help_keyboard())

@app.on_callback_query(filters.regex(r"^elara_help$"))
async def help_home(_, query: CallbackQuery):
    await query.answer()
    await _edit(query, HELP_HOME, help_keyboard())

@app.on_callback_query(filters.regex(r"^elara_help_ai$"))
async def help_ai(_, query: CallbackQuery):
    await query.answer()
    await _edit(query, AI_HELP, back_keyboard())

@app.on_callback_query(filters.regex(r"^elara_help_social$"))
async def help_social(_, query: CallbackQuery):
    await query.answer()
    await _edit(query, SOCIAL_HELP, back_keyboard())

@app.on_callback_query(filters.regex(r"^elara_help_close$"))
async def help_close(_, query: CallbackQuery):
    await query.answer("Closed.")
    try:
        await query.message.delete()
    except Exception:
        try:
            await _edit(query, "🌙 <b>Elara Help closed.</b>", home_keyboard())
        except Exception:
            pass
