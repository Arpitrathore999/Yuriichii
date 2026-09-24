# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  Rich Message Start (OUTLAW X MUSIC style)
# --------------------------------------------------------------------------------

import asyncio
import json
from urllib.request import Request, urlopen
from urllib.error import URLError

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ParseMode

import config
from core.bot import app
from database.users import ensure_user

bot = app


# ─── Config ──────────────────────────────────────────────────────────────────
BOT_NAME = getattr(config, "BOT_NAME", "Elara")
BOT_USERNAME = (getattr(config, "BOT_USERNAME", "") or "").lstrip("@")
BOT_TOKEN = getattr(config, "BOT_TOKEN", "")
SUPPORT_URL = getattr(config, "SUPPORT_URL", "")
UPDATES_URL = getattr(config, "UPDATES_URL", "")
OWNER_URL = getattr(config, "OWNER_URL", "")
OWNER_ID = getattr(config, "OWNER_ID", 0)
START_IMAGE_URL = (getattr(config, "START_IMAGE_URL", "") or "").strip()


# ─── Safe URL helpers ────────────────────────────────────────────────────────
_FALLBACK = "https://t.me/telegram"

def _safe_url(u, fb=_FALLBACK):
    if not u or not isinstance(u, str):
        return fb
    u = u.strip()
    if not (u.startswith("https://") or u.startswith("tg://")):
        return fb
    if u in ("https://t.me/", "https://t.me"):
        return fb
    return u

def _safe_user_url(uid):
    try:
        uid = int(uid)
        return f"tg://user?id={uid}" if uid > 0 else _FALLBACK
    except Exception:
        return _FALLBACK

def _safe_startgroup_url():
    return f"https://t.me/{BOT_USERNAME}?startgroup=true" if BOT_USERNAME else _FALLBACK

def _owner_link():
    return _safe_url(OWNER_URL) if OWNER_URL else _safe_user_url(OWNER_ID)

def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════════════════════════════════════════════
#  RAW BOT API CALL — sendRichMessage
# ══════════════════════════════════════════════════════════════════════════════

async def _bot_api(method: str, payload: dict) -> dict:
    """Call Telegram Bot API raw HTTP (for sendRichMessage etc.)."""
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN missing"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    def _do():
        try:
            with urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except URLError as e:
            return {"ok": False, "description": str(e)}
        except Exception as e:
            return {"ok": False, "description": str(e)}

    return await asyncio.to_thread(_do)


# ══════════════════════════════════════════════════════════════════════════════
#  RICH MESSAGE HTML — OUTLAW X MUSIC EXACT STYLE
# ══════════════════════════════════════════════════════════════════════════════

def _rich_html(user) -> str:
    uid = getattr(user, "id", 0)
    name = _esc(getattr(user, "first_name", None) or "there")
    bot = _esc(BOT_NAME)

    support = _safe_url(SUPPORT_URL)
    updates = _safe_url(UPDATES_URL)

    # Rich message HTML — Telegram renders tables, collapsibles, pills
    return f"""❍ ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🎶

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ ᴛᴇʟᴇɢʀᴀᴍ
<b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b> ᴡɪᴛʜ sᴏᴍᴇ ᴀᴡᴇsᴏᴍᴇ
ғᴇᴀᴛᴜʀᴇs.

<details open><summary>✦ ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs ✦</summary>

| ғᴇᴀᴛᴜʀᴇ | ᴅᴇᴛᴀɪʟs |
|---|---|
| 🤖 **ᴀɪ ᴄʜᴀᴛ** | ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs ɪɴ ᴅᴍ &amp; ɢʀᴏᴜᴘs |
| 🧠 **ᴍᴇᴍᴏʀʏ** | ᴋᴇᴇᴘs ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ ғᴏʀ ʙᴇᴛᴛᴇʀ ʀᴇᴘʟɪᴇs |
| 💕 **sᴏᴄɪᴀʟ** | ғᴜɴ ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs ᴡɪᴛʜ ᴜsᴇʀs |
| ⚡ **ғᴀsᴛ** | ǫᴜɪᴄᴋ ᴀɪ ʀᴇsᴘᴏɴsᴇs ᴘᴏᴡᴇʀᴇᴅ ʙʏ ɢʀᴏǫ |
</details>

<details open><summary>✧ ᴡʜʏ ᴄʜᴏᴏsᴇ ɪᴛ? ✧</summary>

⭐ sɪᴍᴘʟᴇ sʟᴀsʜ ᴄᴏᴍᴍᴀɴᴅs, ɴᴏ sᴇᴛᴜᴘ ɴᴇᴇᴅᴇᴅ.
🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ.
❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.
</details>

<blockquote>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <b>{bot}</b></blockquote>

[🍬 sᴜᴘᴘᴏʀᴛ]({support}) · [🍹 ᴜᴘᴅᴀᴛᴇs]({updates})
"""


# ══════════════════════════════════════════════════════════════════════════════
#  KEYBOARD
# ══════════════════════════════════════════════════════════════════════════════

def _welcome_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛩️ ᴀᴅᴅ ᴍᴇ ʙᴀʙʏ ⛩️", url=_safe_startgroup_url())],
        [
            InlineKeyboardButton("🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=_safe_url(SUPPORT_URL)),
            InlineKeyboardButton("🍹 ᴜᴘᴅᴀᴛᴇs 🍹", url=_safe_url(UPDATES_URL)),
        ],
        [InlineKeyboardButton("🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩", callback_data="elara:help")],
        [
            InlineKeyboardButton("🫧 ᴏᴡɴᴇʀ 🫧", url=_owner_link()),
            InlineKeyboardButton("🍡 sᴏᴜʀᴄᴇ 🍡", callback_data="elara:about"),
        ],
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  SEND START MESSAGE
# ══════════════════════════════════════════════════════════════════════════════

async def _send_start(chat_id: int, user):
    kb = _welcome_kb()
    html = _rich_html(user)

    # Convert InlineKeyboardMarkup to dict for raw API
    kb_dict = {
        "inline_keyboard": [
            [
                {
                    "text": b.text,
                    **({"url": b.url} if b.url else {}),
                    **({"callback_data": b.callback_data} if b.callback_data else {}),
                }
                for b in row
            ]
            for row in kb.inline_keyboard
        ]
    }

    image = START_IMAGE_URL.split(",")[0].strip() if START_IMAGE_URL else ""

    # Try sendRichMessage first
    payload = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
        "reply_markup": kb_dict,
    }
    if image:
        payload["rich_message"]["photo_url"] = image

    result = await _bot_api("sendRichMessage", payload)
    if result.get("ok"):
        return

    print(f"[start] sendRichMessage failed: {result.get('description')}")

    # Fallback: sendPhoto with caption
    if image:
        try:
            return await bot.send_photo(
                chat_id,
                photo=image,
                caption=html,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[start] sendPhoto failed: {e}")

    # Last fallback: sendMessage
    return await bot.send_message(
        chat_id,
        html,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("start"))
async def start_handler(_, message):
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    await _send_start(message.chat.id, message.from_user)


@bot.on_callback_query(filters.regex(r"^elara:help$"))
async def help_cb(_, q: CallbackQuery):
    await q.answer("Help coming soon!")


@bot.on_callback_query(filters.regex(r"^elara:about$"))
async def about_cb(_, q: CallbackQuery):
    await q.answer("Elara AI Bot 🌙")