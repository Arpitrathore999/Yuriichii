# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  Rich UI Start — Music Bot Style (OUTLAW X MUSIC clone)
# --------------------------------------------------------------------------------

import asyncio

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from core.bot import app
from database.users import ensure_user

bot = app


# ─── Config ──────────────────────────────────────────────────────────────────
BOT_NAME = getattr(config, "BOT_NAME", "Elara")
BOT_USERNAME = (getattr(config, "BOT_USERNAME", "") or "").lstrip("@")
SUPPORT_URL = getattr(config, "SUPPORT_URL", "")
UPDATES_URL = getattr(config, "UPDATES_URL", "")
OWNER_URL = getattr(config, "OWNER_URL", "")
OWNER_ID = getattr(config, "OWNER_ID", 0)
START_IMAGE_URL = (getattr(config, "START_IMAGE_URL", "") or "").strip()


# ─── Safe URL helpers ────────────────────────────────────────────────────────
_FALLBACK = "https://t.me/telegram"

def _safe_url(u: str, fb: str = _FALLBACK) -> str:
    if not u or not isinstance(u, str):
        return fb
    u = u.strip()
    if not (u.startswith("https://") or u.startswith("tg://")):
        return fb
    if u in ("https://t.me/", "https://t.me"):
        return fb
    return u

def _safe_user_url(uid) -> str:
    try:
        uid = int(uid)
        return f"tg://user?id={uid}" if uid > 0 else _FALLBACK
    except Exception:
        return _FALLBACK

def _safe_startgroup_url() -> str:
    return f"https://t.me/{BOT_USERNAME}?startgroup=true" if BOT_USERNAME else _FALLBACK

def _owner_link() -> str:
    return _safe_url(OWNER_URL) if OWNER_URL else _safe_user_url(OWNER_ID)

def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════════════════════════════════════════════
#  RICH MESSAGE CAPTION  —  OUTLAW X MUSIC style
# ══════════════════════════════════════════════════════════════════════════════

def _rich_welcome(user) -> str:
    """
    Rich HTML with <tg-table>, <tg-collapsible>, <tg-button-pill>.
    Renders like the OUTLAW X MUSIC screenshots when Bot API supports it.
    """
    uid = getattr(user, "id", 0)
    name = _esc(getattr(user, "first_name", None) or "there")
    bot = _esc(BOT_NAME)

    return f"""
❍ ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🎶

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ
ᴛᴇʟᴇɢʀᴀᴍ <b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b> ᴡɪᴛʜ sᴏᴍᴇ
ᴀᴡᴇsᴏᴍᴇ ғᴇᴀᴛᴜʀᴇs.

<tg-collapsible open>
<tg-title>✦ ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs ✦</tg-title>

<tg-table>
<tg-row><tg-cell>🤖 ᴀɪ ᴄʜᴀᴛ</tg-cell><tg-cell>ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs ɪɴ ᴅᴍ &amp; ɢʀᴏᴜᴘs</tg-cell></tg-row>
<tg-row><tg-cell>🧠 ᴍᴇᴍᴏʀʏ</tg-cell><tg-cell>ᴋᴇᴇᴘs ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ ғᴏʀ ʙᴇᴛᴛᴇʀ ʀᴇᴘʟɪᴇs</tg-cell></tg-row>
<tg-row><tg-cell>💕 sᴏᴄɪᴀʟ</tg-cell><tg-cell>ғᴜɴ ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs — ʜᴜɢ, ᴋɪss, ᴍᴀʀʀɪᴀɢᴇ &amp; ᴍᴏʀᴇ</tg-cell></tg-row>
<tg-row><tg-cell>⚡ ғᴀsᴛ</tg-cell><tg-cell>ǫᴜɪᴄᴋ ᴀɪ ʀᴇsᴘᴏɴsᴇs ᴘᴏᴡᴇʀᴇᴅ ʙʏ ɢʀᴏǫ</tg-cell></tg-row>
</tg-table>
</tg-collapsible>

<tg-collapsible open>
<tg-title>✧ ᴡʜʏ ᴄʜᴏᴏsᴇ ɪᴛ? ✧</tg-title>

⭐ sɪᴍᴘʟᴇ sʟᴀsʜ ᴄᴏᴍᴍᴀɴᴅs, ɴᴏ sᴇᴛᴜᴘ ɴᴇᴇᴅᴇᴅ.
🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ.
❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.
</tg-collapsible>

<tg-collapsible>
<tg-title>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » {bot}</tg-title>
</tg-collapsible>

<tg-button-pill url="{_safe_url(SUPPORT_URL)}" color="primary">🍬 sᴜᴘᴘᴏʀᴛ</tg-button-pill> <tg-button-pill url="{_safe_url(UPDATES_URL)}" color="success">🍹 ᴜᴘᴅᴀᴛᴇs</tg-button-pill>
"""


def _plain_welcome(user) -> str:
    """Fallback plain HTML — agar rich tags render na ho."""
    uid = getattr(user, "id", 0)
    name = _esc(getattr(user, "first_name", None) or "there")
    bot = _esc(BOT_NAME)

    return f"""
❍ ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🎶

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ
ᴛᴇʟᴇɢʀᴀᴍ <b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b> ᴡɪᴛʜ sᴏᴍᴇ
ᴀᴡᴇsᴏᴍᴇ ғᴇᴀᴛᴜʀᴇs.

✦ <b>ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs</b> ✦

<code>┌──────────────────────────────┐
│    ғᴇᴀᴛᴜʀᴇ      ᴅᴇᴛᴀɪʟs    │
├──────────────────────────────┤
│ 🤖 ᴀɪ ᴄʜᴀᴛ      ɴᴀᴛᴜʀᴀʟ   │
│ 🧠 ᴍᴇᴍᴏʀʏ       ʀᴇᴄᴇɴᴛ    │
│ 💕 sᴏᴄɪᴀʟ        ғᴜɴ      │
│ ⚡ ғᴀsᴛ           ǫᴜɪᴄᴋ    │
└──────────────────────────────┘</code>

✧ <b>ᴡʜʏ ᴄʜᴏᴏsᴇ ɪᴛ?</b> ✧

⭐ sɪᴍᴘʟᴇ sʟᴀsʜ ᴄᴏᴍᴍᴀɴᴅs, ɴᴏ sᴇᴛᴜᴘ ɴᴇᴇᴅᴇᴅ.
🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ.
❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.

<b>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » {bot}</b>
"""


# ─── Keyboard (7 buttons — same as OUTLAW X MUSIC) ────────────────────────────
def _welcome_kb() -> InlineKeyboardMarkup:
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


# ─── Help menus ──────────────────────────────────────────────────────────────
_HELP_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🤖 ᴀɪ", callback_data="elara:ai"),
        InlineKeyboardButton("💕 sᴏᴄɪᴀʟ", callback_data="elara:social"),
    ],
    [InlineKeyboardButton("⌯ ʜᴏᴍᴇ ⌯", callback_data="elara:home")],
])

_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="elara:help")],
    [InlineKeyboardButton("⌯ ᴄʟᴏsᴇ ⌯", callback_data="elara:close")],
])

HELP_MENU = """📜 <b>ᴇʟᴀʀᴀ ʜᴇʟᴘ &amp; ᴄᴏᴍᴍᴀɴᴅs</b>

❍ ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ.

<b>🤖 ᴀɪ</b> — ᴄʜᴀᴛ, ᴍᴇᴍᴏʀʏ, ɢʀᴏᴜᴘ ᴀɪ
<b>💕 sᴏᴄɪᴀʟ</b> — ғᴜɴ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs
"""

AI_HELP = """🤖 <b>ᴇʟᴀʀᴀ ᴀɪ</b>

<b>💬 ᴄʜᴀᴛ</b>
• <code>/ai &lt;msg&gt;</code>
• ɴᴏʀᴍᴀʟ ᴍᴇssᴀɢᴇ ɪɴ ᴅᴍ

<b>👥 ɢʀᴏᴜᴘ</b>
• <code>ᴇʟᴀʀᴀ ʜᴇʟʟᴏ</code>
• <code>@BotUsername ʜɪ</code>
• ʀᴇᴘʟʏ ᴛᴏ ᴇʟᴀʀᴀ

<b>🧠 ᴍᴇᴍᴏʀʏ</b>
ʀᴇᴄᴇɴᴛ ᴄᴏɴᴛᴇxᴛ ᴜsᴇᴅ ғᴏʀ ɴᴀᴛᴜʀᴀʟ ʀᴇᴘʟɪᴇs.
"""

SOCIAL_HELP = """💕 <b>ᴇʟᴀʀᴀ sᴏᴄɪᴀʟ</b>

ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ's ᴍᴇssᴀɢᴇ:

🫂 <code>/hug</code>    💋 <code>/kiss</code>
🧛 <code>/bite</code>   👋 <code>/slap</code>
🦵 <code>/kick</code>   🫶 <code>/cuddle</code>
🫳 <code>/pat</code>    ✋ <code>/highfive</code>
😏 <code>/flirt</code>  ❤️ <code>/love</code>
💘 <code>/crush</code>  💞 <code>/couple</code>
💍 <code>/propose</code> 💒 <code>/marriage</code>
💔 <code>/divorce</code>
"""

ABOUT = """📖 <b>ᴀʙᴏᴜᴛ ᴇʟᴀʀᴀ</b>

ᴇʟᴀʀᴀ ɪs ʏᴏᴜʀ ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ғᴏʀ ᴇᴠᴇʀʏᴅᴀʏ
ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs, ʀᴀɴᴅᴏᴍ ᴛʜᴏᴜɢʜᴛs ᴀɴᴅ
ʟᴀᴛᴇ-ɴɪɢʜᴛ ᴄʜᴀᴛs. 🌙

💬 ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ
🧠 ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ
💕 sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅs
⚡ ғᴀsᴛ ʀᴇsᴘᴏɴsᴇs

<i>ᴊᴜsᴛ ᴛᴀʟᴋ ᴛᴏ ᴇʟᴀʀᴀ.</i>
"""


# ══════════════════════════════════════════════════════════════════════════════
#  SEND HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _try_rich(chat_id: int, user, caption: str, kb):
    """Try sending rich message first, fallback to plain."""
    # Rich HTML version
    rich_caption = _rich_welcome(user)
    image = START_IMAGE_URL.split(",")[0].strip() if START_IMAGE_URL else ""

    if image:
        try:
            return await bot.send_photo(
                chat_id,
                photo=image,
                caption=rich_caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[rich] photo failed: {e}")

    # Try plain text send (rich HTML will render as-is if unsupported)
    try:
        return await bot.send_message(
            chat_id,
            rich_caption,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        print(f"[rich] text failed: {e}")

    # Last fallback: plain
    if image:
        try:
            return await bot.send_photo(
                chat_id,
                photo=image,
                caption=_plain_welcome(user),
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    return await bot.send_message(
        chat_id,
        _plain_welcome(user),
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("start"))
async def start_handler(_, message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    chat_id = message.chat.id

    try:
        await _try_rich(chat_id, message.from_user, _plain_welcome(message.from_user), _welcome_kb())
    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        await _try_rich(chat_id, message.from_user, _plain_welcome(message.from_user), _welcome_kb())


@bot.on_message(filters.command("help"))
async def help_handler(_, message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    await bot.send_message(
        message.chat.id, HELP_MENU,
        reply_markup=_HELP_KB,
        parse_mode=ParseMode.HTML,
    )


@bot.on_callback_query(filters.regex(r"^elara:(home|help|about|social|ai|close)$"))
async def cb(_, q: CallbackQuery) -> None:
    d = q.data.split(":", 1)[1]

    if d == "close":
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    if d == "home":
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await _try_rich(q.message.chat.id, q.from_user, "", _welcome_kb())
        return

    if d == "help":
        await q.answer()
        await q.message.edit_text(HELP_MENU, reply_markup=_HELP_KB, parse_mode=ParseMode.HTML)
        return

    if d == "ai":
        await q.answer()
        await q.message.edit_text(AI_HELP, reply_markup=_BACK_KB, parse_mode=ParseMode.HTML)
        return

    if d == "social":
        await q.answer()
        await q.message.edit_text(SOCIAL_HELP, reply_markup=_BACK_KB, parse_mode=ParseMode.HTML)
        return

    if d == "about":
        await q.answer()
        await q.message.edit_text(ABOUT, reply_markup=_BACK_KB, parse_mode=ParseMode.HTML)
        return