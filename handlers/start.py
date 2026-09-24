import asyncio
import json
from urllib.request import Request, urlopen
from urllib.error import URLError

from pyrogram import filters
from pyrogram.types import CallbackQuery
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


def btn(text, callback_data=None, url=None, style=None):
    item = {"text": text}
    if callback_data:
        item["callback_data"] = callback_data
    if url:
        item["url"] = url
    # Telegram supports: primary, success, danger.
    # Do not send unsupported values such as "secondary".
    if style in ("primary", "success", "danger"):
        item["style"] = style
    return item


def keyboard():
    username = getattr(config, "BOT_USERNAME", "").lstrip("@")
    add_url = (
        f"https://t.me/{username}?startgroup=true"
        if username else "https://t.me/"
    )

    return {
        "inline_keyboard": [
            [btn("⛩️ ADD ME BABY ⛩️", url=add_url, style="primary")],
            [
                btn(
                    "🍬 SUPPORT 🍬",
                    url=getattr(config, "SUPPORT_URL", "") or "https://t.me/",
                    style="success",
                ),
                btn(
                    "🍹 UPDATES 🍹",
                    url=getattr(config, "UPDATES_URL", "") or "https://t.me/",
                    style="success",
                ),
            ],
            [btn("🏩 HELP & COMMANDS 🏩", callback_data="elara:help", style="primary")],
            [
                btn(
                    "🫧 OWNER 🫧",
                    url=getattr(config, "OWNER_URL", "") or "https://t.me/",
                ),
                btn(
                    "🍡 SOURCE 🍡",
                    url=getattr(config, "SOURCE_URL", "") or "https://t.me/",
                ),
            ],
        ]
    }


def help_keyboard():
    return {
        "inline_keyboard": [
            [
                btn("🤖 AI", callback_data="elara:ai", style="primary"),
                btn("💕 SOCIAL", callback_data="elara:social", style="success"),
            ],
            [btn("⌯ BACK ⌯", callback_data="elara:home")],
        ]
    }


def back_keyboard():
    return {
        "inline_keyboard": [
            [btn("⬅️ BACK", callback_data="elara:help")]
        ]
    }


def home_text(user):
    name = esc(getattr(user, "first_name", None) or "there")
    uid = getattr(user, "id", 0)

    return f"""
❍ <b>HEY <a href="tg://user?id={uid}">{name}</a>, WELCOME ABOARD! 🌙</b>

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
"""


async def api(method, payload):
    """Call Telegram Bot API without requiring an extra HTTP package."""
    if not config.BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN is missing"}

    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    def do_request():
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "description": str(e)}

    return await asyncio.to_thread(do_request)


async def send_home(message):
    if message.from_user:
        try:
            await ensure_user(message.from_user)
        except Exception:
            pass

    text = home_text(message.from_user)
    markup = keyboard()
    image = getattr(config, "START_IMAGE_URL", "").strip()

    if image:
        result = await api("sendPhoto", {
            "chat_id": message.chat.id,
            "photo": image,
            "caption": text,
            "parse_mode": "HTML",
            "reply_markup": markup,
        })
        if result.get("ok"):
            return

    # Always fall back to plain text if the image URL is invalid.
    result = await api("sendMessage", {
        "chat_id": message.chat.id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    })

    # Last-resort Pyrogram send so /start never silently fails.
    if not result.get("ok"):
        await app.send_message(
            message.chat.id,
            text,
            disable_web_page_preview=True,
        )


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

    result = await api("sendMessage", {
        "chat_id": message.chat.id,
        "text": HELP,
        "parse_mode": "HTML",
        "reply_markup": help_keyboard(),
        "disable_web_page_preview": True,
    })

    if not result.get("ok"):
        await app.send_message(message.chat.id, HELP, disable_web_page_preview=True)


@app.on_callback_query(filters.regex(r"^elara:(home|help|ai|social)$"))
async def callbacks(_, query: CallbackQuery):
    await api("answerCallbackQuery", {
        "callback_query_id": query.id,
    })

    action = query.data.split(":", 1)[1]

    if action == "home":
        text, markup = home_text(query.from_user), keyboard()
    elif action == "help":
        text, markup = HELP, help_keyboard()
    elif action == "ai":
        text, markup = AI, back_keyboard()
    else:
        text, markup = SOCIAL, back_keyboard()

    result = await api("editMessageText", {
        "chat_id": query.message.chat.id,
        "message_id": query.message.id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    })

    if not result.get("ok"):
        try:
            await query.message.edit_text(
                text,
                disable_web_page_preview=True,
            )
        except Exception:
            pass
