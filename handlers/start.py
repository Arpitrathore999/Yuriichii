import aiohttp
from pyrogram import filters
from pyrogram.types import CallbackQuery
from core.bot import app
from database.users import ensure_user
import config

API = f"https://api.telegram.org/bot{config.BOT_TOKEN}"


def esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def button(text, callback_data=None, url=None, style=None):
    data = {"text": text}
    if callback_data:
        data["callback_data"] = callback_data
    if url:
        data["url"] = url
    if style:
        data["style"] = style
    return data


def keyboard():
    username = getattr(config, "BOT_USERNAME", "")
    add_url = (
        f"https://t.me/{username}?startgroup=true"
        if username else "https://t.me/"
    )

    return {
        "inline_keyboard": [
            [button("⛩️ ADD ME BABY ⛩️", url=add_url, style="primary")],
            [
                button("🍬 SUPPORT 🍬",
                       url=getattr(config, "SUPPORT_URL", "") or "https://t.me/",
                       style="success"),
                button("🍹 UPDATES 🍹",
                       url=getattr(config, "UPDATES_URL", "") or "https://t.me/",
                       style="success"),
            ],
            [button("🏩 HELP & COMMANDS 🏩",
                     callback_data="elara:help",
                     style="primary")],
            [
                button("🫧 OWNER 🫧",
                       url=getattr(config, "OWNER_URL", "") or "https://t.me/",
                       style="secondary"),
                button("🍡 SOURCE 🍡",
                       url=getattr(config, "SOURCE_URL", "") or "https://t.me/",
                       style="secondary"),
            ],
        ]
    }


def help_keyboard():
    return {
        "inline_keyboard": [
            [
                button("🤖 AI", callback_data="elara:ai", style="primary"),
                button("💕 SOCIAL", callback_data="elara:social", style="success"),
            ],
            [button("⌯ BACK ⌯", callback_data="elara:home", style="secondary")],
        ]
    }


def back_keyboard():
    return {
        "inline_keyboard": [
            [button("⬅️ BACK", callback_data="elara:help", style="secondary")]
        ]
    }


def home_text(user):
    name = esc(user.first_name or "there")
    return f"""
❍ <b>HEY <a href="tg://user?id={user.id}">{name}</a>, WELCOME ABOARD! 🌙</b>

I AM <b>ELARA</b> — A FAST &amp; FRIENDLY
TELEGRAM AI COMPANION WITH SOME
AWESOME FEATURES. ✨

<b>✦ KEY FEATURES ✦</b>

<code>┌──────────────────────────────┐
│       FEATURE       DETAILS  │
├──────────────────────────────┤
│ 🤖 AI CHAT        NATURAL AI │
│                  CONVERSATIONS│
├──────────────────────────────┤
│ 🧠 MEMORY         RECENT CHAT│
│                    CONTEXT   │
├──────────────────────────────┤
│ 💕 SOCIAL         FUN GROUP  │
│                  INTERACTIONS│
├──────────────────────────────┤
│ ⚡ FAST            QUICK AI  │
│                   RESPONSES  │
└──────────────────────────────┘</code>

✧ <b>WHY CHOOSE ELARA?</b> ✧

⭐ NATURAL AI CONVERSATIONS.
🧠 SMART CONVERSATION MEMORY.
💕 FUN SOCIAL COMMANDS.
❍ CLICK HELP BELOW FOR ALL COMMANDS.

<b>POWERED BY » ELARA AI</b>
"""


HELP = """
📜 <b>ELARA HELP &amp; COMMANDS</b>

❍ CHOOSE A CATEGORY BELOW TO VIEW
ITS COMMANDS AND FEATURES.

<b>🤖 AI</b>
CHAT, MEMORY &amp; GROUP AI FEATURES.

<b>💕 SOCIAL</b>
FUN INTERACTIONS FOR YOUR GROUP.

<i>Reply to a user before using a social command.</i>
"""

AI = """
🤖 <b>ELARA AI</b>

<b>💬 CHAT</b>
• <code>/ai &lt;message&gt;</code>
• Send a normal message in DM.

<b>👥 GROUP</b>
• <code>Elara hello</code>
• <code>@BotUsername hello</code>
• Reply to Elara.

<b>🧠 MEMORY</b>
Recent conversation context is used for
more natural replies. 🌙
"""

SOCIAL = """
💕 <b>ELARA SOCIAL</b>

Reply to a user's message:

🫂 <code>/hug</code>      💋 <code>/kiss</code>
🧛 <code>/bite</code>     👋 <code>/slap</code>
🦵 <code>/kick</code>     🫶 <code>/cuddle</code>
🫳 <code>/pat</code>      ✋ <code>/highfive</code>
😏 <code>/flirt</code>    ❤️ <code>/love</code>
💘 <code>/crush</code>    💞 <code>/couple</code>
💍 <code>/propose</code>  💒 <code>/marriage</code>
💔 <code>/divorce</code>

<i>REPLY → COMMAND → ENJOY ✦</i>
"""


async def api(method, payload):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API}/{method}", json=payload) as response:
            return await response.json()


async def send_home(message):
    if message.from_user:
        await ensure_user(message.from_user)

    text = home_text(message.from_user)

    # Use Bot API here because button styles (blue/green/dark)
    # are Bot API features and may not be supported by Pyrogram's
    # InlineKeyboardButton class.
    payload = {
        "chat_id": message.chat.id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard(),
        "disable_web_page_preview": True,
    }

    image = getattr(config, "START_IMAGE_URL", "")
    if image:
        photo_payload = {
            "chat_id": message.chat.id,
            "photo": image,
            "caption": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard(),
        }
        result = await api("sendPhoto", photo_payload)
        if result.get("ok"):
            return
    await api("sendMessage", payload)


@app.on_message(filters.command("start"))
async def start(_, message):
    try:
        await message.delete()
    except Exception:
        pass
    await send_home(message)


@app.on_message(filters.command("help"))
async def help_command(_, message):
    try:
        await message.delete()
    except Exception:
        pass
    await api("sendMessage", {
        "chat_id": message.chat.id,
        "text": HELP,
        "parse_mode": "HTML",
        "reply_markup": help_keyboard(),
        "disable_web_page_preview": True,
    })


@app.on_callback_query(filters.regex(r"^elara:(home|help|ai|social)$"))
async def callbacks(_, query: CallbackQuery):
    action = query.data.split(":", 1)[1]
    await api("answerCallbackQuery", {
        "callback_query_id": query.id,
    })

    if action == "home":
        text = home_text(query.from_user)
        markup = keyboard()
    elif action == "help":
        text = HELP
        markup = help_keyboard()
    elif action == "ai":
        text = AI
        markup = back_keyboard()
    else:
        text = SOCIAL
        markup = back_keyboard()

    await api("editMessageText", {
        "chat_id": query.message.chat.id,
        "message_id": query.message.id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    })
