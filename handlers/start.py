from pyrogram import filters
from pyrogram.types import CallbackQuery
from core.bot import app
from database.users import ensure_user
from utils.keyboards import start_keyboard, back_keyboard
import config

WELCOME = """
🌙 <b>HEY, WELCOME TO ELARA</b> 🌙

I AM <b>ELARA</b> — YOUR AI COMPANION FOR
CONVERSATIONS, CHAOS & LATE-NIGHT TALKS.

<i>“Real conversations. Random thoughts.
Always here.”</i>

✦ <b>KEY FEATURES</b> ✦

┌─────────────────────────────┐
│ 💬 <b>AI CHAT</b>             │
│    Natural conversations    │
├─────────────────────────────┤
│ 🧠 <b>MEMORY</b>              │
│    Recent chat context      │
├─────────────────────────────┤
│ 👥 <b>SOCIAL</b>              │
│    Fun interactions         │
├─────────────────────────────┤
│ ⚡ <b>FAST</b>                 │
│    Quick AI responses       │
└─────────────────────────────┘

<b>TALK • CHAT • CONNECT • ALWAYS HERE</b>
"""

ABOUT = """
📖 <b>ABOUT ELARA</b>

Elara is your AI companion for everyday
conversations, random thoughts and late-night
chats. 🌙

💬 Natural AI conversation
🧠 Conversation memory
💕 Social interaction commands
⚡ Fast responses

<i>Just talk to Elara. No complicated setup.</i>
"""

HELP = """
❓ <b>HELP & COMMANDS</b>

🤖 <b>AI</b>
/ai &lt;message&gt; — Chat with Elara

💕 <b>SOCIAL</b>
Reply to a user's message and use:
/hug  /kiss  /bite  /slap
/kick  /cuddle  /pat  /highfive
/flirt  /love  /crush  /couple
/propose  /marriage  /divorce

💡 In groups you can also say:
<code>Elara hello</code>
or mention the bot.

<b>Tip:</b> Social commands target the user
you reply to.
"""

SOCIAL = """
💕 <b>ELARA SOCIAL</b>

🫂 /hug       💋 /kiss
🧛 /bite      👋 /slap
🦵 /kick      🫶 /cuddle
🫳 /pat       ✋ /highfive
😏 /flirt     ❤️ /love
💘 /crush     💞 /couple
💍 /propose   💒 /marriage
💔 /divorce

<i>Reply to a user's message before using
a targeted social command.</i>
"""

async def send_home(message, edit=False):
    await ensure_user(message.from_user)
    if config.START_IMAGE_URL:
        if edit:
            try:
                await message.edit_media(
                    __import__("pyrogram").types.InputMediaPhoto(
                        config.START_IMAGE_URL,
                        caption=WELCOME
                    ),
                    reply_markup=start_keyboard()
                )
                return
            except Exception:
                pass
        try:
            await message.reply_photo(
                config.START_IMAGE_URL,
                caption=WELCOME,
                reply_markup=start_keyboard()
            )
            return
        except Exception:
            pass

    if edit:
        await message.edit_text(WELCOME, reply_markup=start_keyboard())
    else:
        await message.reply_text(WELCOME, reply_markup=start_keyboard())

@app.on_message(filters.command("start"))
async def start(_, message):
    await send_home(message)

@app.on_callback_query(filters.regex(r"^elara:(home|about|help|social|chat)$"))
async def start_callbacks(_, query: CallbackQuery):
    action = query.data.split(":", 1)[1]

    if action == "home":
        await query.answer()
        await query.message.edit_text(WELCOME, reply_markup=start_keyboard())
        return

    if action == "about":
        await query.answer()
        await query.message.edit_text(ABOUT, reply_markup=back_keyboard())
        return

    if action == "help":
        await query.answer()
        await query.message.edit_text(HELP, reply_markup=back_keyboard())
        return

    if action == "social":
        await query.answer()
        await query.message.edit_text(SOCIAL, reply_markup=back_keyboard())
        return

    if action == "chat":
        await query.answer("Just send me a message 💬")
        await query.message.edit_text(
            "💬 <b>CHAT MODE</b>\n\n"
            "Just send me a message and I'll reply. 🌙\n\n"
            "You can talk normally — no command needed.",
            reply_markup=back_keyboard()
        )
