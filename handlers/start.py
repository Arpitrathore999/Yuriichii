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
#  START MESSAGE
# ══════════════════════════════════════════════════════════════════════════════

def _rich_html(user) -> str:
    uid = getattr(user, "id", 0)
    name = _esc(getattr(user, "first_name", None) or "there")
    bot_name = _esc(BOT_NAME)

    return f"""❍ <b>ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🎶</b>

ɪ ᴀᴍ <b>「 {bot_name} 」</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ
<b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b> ᴡɪᴛʜ sᴏᴍᴇ ᴀᴡᴇsᴏᴍᴇ ғᴇᴀᴛᴜʀᴇs.

<b>✦ ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs ✦</b>

🤖 <b>ᴀɪ ᴄʜᴀᴛ</b> — ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs
🧠 <b>ᴍᴇᴍᴏʀʏ</b> — ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ ғᴏʀ ʙᴇᴛᴛᴇʀ ʀᴇᴘʟɪᴇs
💕 <b>sᴏᴄɪᴀʟ</b> — ғᴜɴ ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs
⚡ <b>ғᴀsᴛ</b> — ǫᴜɪᴄᴋ ᴀɪ ʀᴇsᴘᴏɴsᴇs

<b>✧ ᴡʜʏ ᴄʜᴏᴏsᴇ ᴇʟᴀʀᴀ? ✧</b>

⭐ sɪᴍᴘʟᴇ sʟᴀsʜ ᴄᴏᴍᴍᴀɴᴅs
🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ
❍ ᴄʟɪᴄᴋ <b>ʜᴇʟᴘ &amp; ᴄᴏᴍᴍᴀɴᴅs</b> ғᴏʀ ᴍᴏʀᴇ

<blockquote>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <b>{bot_name}</b></blockquote>"""


def _welcome_kb():
    rows = [
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
    ]
    return InlineKeyboardMarkup(rows)


async def _send_start(chat_id: int, user):
    html = _rich_html(user)
    kb = _welcome_kb()
    image = START_IMAGE_URL.split(",")[0].strip() if START_IMAGE_URL else ""

    # Use Pyrogram directly. The old code called "sendRichMessage", which
    # is not a standard Telegram Bot API method and caused /start to fail.
    if image:
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=image,
                caption=html,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[start] send_photo failed, falling back to text: {e}")

    return await bot.send_message(
        chat_id=chat_id,
        text=html,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
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
    except Exception as e:
        print(f"[start] ensure_user failed: {e}")

    try:
        await _send_start(message.chat.id, message.from_user)
    except Exception as e:
        print(f"[start] send failed: {e}")
        try:
            await bot.send_message(
                message.chat.id,
                f"ʜᴇʏ <a href="tg://user?id={message.from_user.id}">{_esc(message.from_user.first_name or 'there')}</a>! 🌙\n\n"
                f"「 <b>{_esc(BOT_NAME)}</b> 」 ɪs ᴏɴʟɪɴᴇ.\n\nᴛʀʏ /help",
                parse_mode=ParseMode.HTML,
            )
        except Exception as fallback_error:
            print(f"[start] final fallback failed: {fallback_error}")


@bot.on_callback_query(filters.regex(r"^elara:help$"))
async def help_cb(_, q: CallbackQuery):
    await q.answer("Help coming soon!")


@bot.on_callback_query(filters.regex(r"^elara:about$"))
async def about_cb(_, q: CallbackQuery):
    await q.answer("Elara AI Bot 🌙")