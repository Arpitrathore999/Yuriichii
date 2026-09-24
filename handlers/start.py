# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  Developed by AN NarissX ❤️
#
#  handlers/start.py  —  EXTENDED VERSION
#  ---------------------------------------------------------------
#  Yeh file /start, /help, aur saare start-menu callbacks ko handle karti hai.
#  Features:
#   • Rich HTML welcome (blockquote boxes, bold, emoji)
#   • Photo support (single ya comma-separated rotation)
#   • Kurigram colored buttons (PRIMARY/SUCCESS/DANGER)
#   • Safe URL fallback (invalid URL se crash nahi)
#   • FloodWait handling
#   • Photo↔Text edit fallback
#   • Group vs Private detection
#   • New user logger
# --------------------------------------------------------------------------------

# ─── Standard library imports ───────────────────────────────────────────────────
import asyncio
import random
from typing import Optional

# ─── Pyrogram / Kurigram imports ────────────────────────────────────────────────
from pyrogram import enums, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    User,
)

# ─── Project imports ────────────────────────────────────────────────────────────
import config
from core.bot import app
from database.users import ensure_user

# ✅ Alias so `bot.` works everywhere (fixes NameError)
bot = app


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG SHORTCUTS
# ═══════════════════════════════════════════════════════════════════════════════

BOT_NAME        = getattr(config, "BOT_NAME", "Elara")
BOT_USERNAME    = (getattr(config, "BOT_USERNAME", "") or "").lstrip("@")
SUPPORT_URL     = getattr(config, "SUPPORT_URL", "")
UPDATES_URL     = getattr(config, "UPDATES_URL", "")
OWNER_URL       = getattr(config, "OWNER_URL", "")
OWNER_ID        = getattr(config, "OWNER_ID", 0)
LOGGER_ID       = getattr(config, "LOGGER_ID", 0)
START_IMAGE_URL = (getattr(config, "START_IMAGE_URL", "") or "").strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  SAFE URL HELPERS
#  ---------------------------------------------------------------
#  Telegram rejects invalid URLs in inline buttons with
#  [400 BUTTON_URL_INVALID]. Yeh helpers us crash ko rok dete hain.
# ═══════════════════════════════════════════════════════════════════════════════

_FALLBACK_URL = "https://t.me/telegram"


def _safe_url(url: str, fallback: str = _FALLBACK_URL) -> str:
    """
    Return a valid https:// or tg:// URL, else fallback.

    Rules:
      • empty/None → fallback
      • not starting with https:// or tg:// → fallback
      • exactly "https://t.me/" → fallback (Telegram rejects)
    """
    if not url or not isinstance(url, str):
        return fallback
    url = url.strip()
    if not (url.startswith("https://") or url.startswith("tg://")):
        return fallback
    if url in ("https://t.me/", "https://t.me"):
        return fallback
    return url


def _safe_user_url(user_id) -> str:
    """
    Build tg://user?id=<id> URL, only if ID is a valid positive integer.
    """
    try:
        uid = int(user_id)
        if uid <= 0:
            return _FALLBACK_URL
        return f"tg://user?id={uid}"
    except (TypeError, ValueError):
        return _FALLBACK_URL


def _safe_startgroup_url() -> str:
    """
    Build ?startgroup=true URL — only if BOT_USERNAME is set.
    """
    if not BOT_USERNAME:
        return _FALLBACK_URL
    return f"https://t.me/{BOT_USERNAME}?startgroup=true"


def _owner_link() -> str:
    """
    Prefer explicit OWNER_URL, else fall back to tg://user?id=<OWNER_ID>.
    """
    if OWNER_URL:
        return _safe_url(OWNER_URL)
    return _safe_user_url(OWNER_ID)


# ═══════════════════════════════════════════════════════════════════════════════
#  ESCAPE / SANITIZE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _esc(value) -> str:
    """
    Escape HTML special chars so user-supplied names don't break the message.
    """
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _sanitize_name(name: Optional[str]) -> str:
    """
    Sanitize a display name: strip, escape HTML, truncate long names.
    """
    if not name:
        return "there"
    name = str(name).strip()
    if len(name) > 40:
        name = name[:37] + "..."
    return _esc(name)


def _mention(user: User) -> str:
    """
    Build a clickable HTML mention for a user.
    """
    name = _sanitize_name(getattr(user, "first_name", None))
    uid = getattr(user, "id", 0)
    return f'<a href="tg://user?id={uid}">{name}</a>'


# ═══════════════════════════════════════════════════════════════════════════════
#  IMAGE PICKER
#  ---------------------------------------------------------------
#  START_IMAGE_URL can be a single URL or comma-separated list.
#  Each /start picks a random one.
# ═══════════════════════════════════════════════════════════════════════════════

def _pick_image() -> str:
    """
    Return a random image URL from START_IMAGE_URL (comma-separated), or "".
    """
    if not START_IMAGE_URL:
        return ""
    parts = [u.strip() for u in START_IMAGE_URL.split(",") if u.strip()]
    if not parts:
        return ""
    return random.choice(parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  CAPTION BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def _welcome_caption(user: User) -> str:
    """
    Rich HTML welcome caption — blockquote boxes, bold, emoji, no raw links.
    """
    uid = getattr(user, "id", 0)
    name = _sanitize_name(getattr(user, "first_name", None))
    bot = _esc(BOT_NAME)

    return f"""❍ ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🎶

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ ᴛᴇʟᴇɢʀᴀᴍ <b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b> ᴡɪᴛʜ sᴏᴍᴇ ᴀᴡᴇsᴏᴍᴇ ғᴇᴀᴛᴜʀᴇs.

<b>✦ ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs ✦</b>

<blockquote>🤖 <b>ᴀɪ ᴄʜᴀᴛ</b>
ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs ɪɴ ᴅᴍ &amp; ɢʀᴏᴜᴘs</blockquote>

<blockquote>🧠 <b>ᴍᴇᴍᴏʀʏ</b>
ᴋᴇᴇᴘs ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ ғᴏʀ ʙᴇᴛᴛᴇʀ ʀᴇᴘʟɪᴇs</blockquote>

<blockquote>💕 <b>sᴏᴄɪᴀʟ</b>
ғᴜɴ ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs — ʜᴜɢ, ᴋɪss, ᴍᴀʀʀɪᴀɢᴇ &amp; ᴍᴏʀᴇ</blockquote>

<blockquote>⚡ <b>ғᴀsᴛ</b>
ǫᴜɪᴄᴋ ᴀɪ ʀᴇsᴘᴏɴsᴇs ᴘᴏᴡᴇʀᴇᴅ ʙʏ ɢʀᴏǫ</blockquote>

<b>✧ ᴡʜʏ ᴄʜᴏᴏsᴇ ɪᴛ? ✧</b>

⭐ sɪᴍᴘʟᴇ sʟᴀsʜ ᴄᴏᴍᴍᴀɴᴅs, ɴᴏ sᴇᴛᴜᴘ ɴᴇᴇᴅᴇᴅ.
🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ.
❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.

<blockquote>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <b>{bot}</b></blockquote>

🍬 <b>sᴜᴘᴘᴏʀᴛ</b>   ·   🍹 <b>ᴜᴘᴅᴀᴛᴇs</b>
"""


def _group_welcome_caption(user: User, chat_title: str) -> str:
    """
    Short group-friendly welcome caption.
    """
    uid = getattr(user, "id", 0)
    name = _sanitize_name(getattr(user, "first_name", None))
    bot = _esc(BOT_NAME)
    title = _esc(chat_title or "this chat")

    return f"""❍ ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴛʜᴀɴᴋs ғᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ! 🎶

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀ ғᴀsᴛ &amp; ғʀɪᴇɴᴅʟʏ ᴛᴇʟᴇɢʀᴀᴍ <b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b>.

<blockquote>ᴛʜᴀɴᴋs ғᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ ɪɴ <b>{title}</b>.
{name} ᴄᴀɴ ɴᴏᴡ ᴛᴀʟᴋ ᴡɪᴛʜ ᴍᴇ ʜᴇʀᴇ. 🌙</blockquote>

🍬 <b>sᴜᴘᴘᴏʀᴛ</b>   ·   🍹 <b>ᴜᴘᴅᴀᴛᴇs</b>
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  HELP MENUS
# ═══════════════════════════════════════════════════════════════════════════════

HELP_MENU = """📜 <b>ᴇʟᴀʀᴀ ʜᴇʟᴘ &amp; ᴄᴏᴍᴍᴀɴᴅs</b>

❍ ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ:

<blockquote>🤖 <b>ᴀɪ</b>
ᴄʜᴀᴛ, ᴍᴇᴍᴏʀʏ &amp; ɢʀᴏᴜᴘ ᴀɪ ғᴇᴀᴛᴜʀᴇs</blockquote>

<blockquote>💕 <b>sᴏᴄɪᴀʟ</b>
ғᴜɴ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs ғᴏʀ ɢʀᴏᴜᴘs</blockquote>

<i>ᴛᴀᴘ ᴀ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ</i> 👇
"""


AI_HELP = """🤖 <b>ᴇʟᴀʀᴀ ᴀɪ ᴄᴏᴍᴍᴀɴᴅs</b>

<blockquote>💬 <b>ᴄʜᴀᴛ</b>
• <code>/ai &lt;msg&gt;</code> — ᴄʜᴀᴛ ᴡɪᴛʜ ᴀɪ
• ᴅᴍ ᴀɴʏ ᴍᴇssᴀɢᴇ — ᴀᴜᴛᴏ ʀᴇᴘʟʏ</blockquote>

<blockquote>👥 <b>ɢʀᴏᴜᴘ</b>
• <code>ᴇʟᴀʀᴀ ʜᴇʟʟᴏ</code> — ᴛʀɪɢɢᴇʀ
• <code>@BotUsername ʜɪ</code> — ᴍᴇɴᴛɪᴏɴ
• ʀᴇᴘʟʏ ᴛᴏ ᴇʟᴀʀᴀ — ᴄᴏɴᴛᴇxᴛ</blockquote>

<blockquote>🧠 <b>ᴍᴇᴍᴏʀʏ</b>
ʀᴇᴄᴇɴᴛ ᴄᴏɴᴛᴇxᴛ ᴜsᴇᴅ ғᴏʀ ɴᴀᴛᴜʀᴀʟ ʀᴇᴘʟɪᴇs.</blockquote>
"""


SOCIAL_HELP = """💕 <b>ᴇʟᴀʀᴀ sᴏᴄɪᴀʟ</b>

<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ's ᴍᴇssᴀɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴛʜᴇsᴇ:</blockquote>

🫂 <code>/hug</code>          💋 <code>/kiss</code>
🧛 <code>/bite</code>         👋 <code>/slap</code>
🦵 <code>/kick</code>         🫶 <code>/cuddle</code>
🫳 <code>/pat</code>          ✋ <code>/highfive</code>
😏 <code>/flirt</code>        ❤️ <code>/love</code>
💘 <code>/crush</code>        💞 <code>/couple</code>
💍 <code>/propose</code>      💒 <code>/marriage</code>
💔 <code>/divorce</code>
"""


ABOUT = """📖 <b>ᴀʙᴏᴜᴛ ᴇʟᴀʀᴀ</b>

ᴇʟᴀʀᴀ ɪs ʏᴏᴜʀ ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ғᴏʀ ᴇᴠᴇʀʏᴅᴀʏ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs, ʀᴀɴᴅᴏᴍ ᴛʜᴏᴜɢʜᴛs ᴀɴᴅ ʟᴀᴛᴇ-ɴɪɢʜᴛ ᴄʜᴀᴛs. 🌙

<blockquote>💬 ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ
🧠 ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ
💕 sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅs
⚡ ғᴀsᴛ ʀᴇsᴘᴏɴsᴇs</blockquote>

<i>ᴊᴜsᴛ ᴛᴀʟᴋ ᴛᴏ ᴇʟᴀʀᴀ. ɴᴏ sᴇᴛᴜᴘ.</i>
"""


CHAT_MODE = """💬 <b>ᴄʜᴀᴛ ᴍᴏᴅᴇ</b>

<blockquote>ᴊᴜsᴛ sᴇɴᴅ ᴍᴇ ᴀ ᴍᴇssᴀɢᴇ ᴀɴᴅ ɪ'ʟʟ ʀᴇᴘʟʏ. 🌙

ʏᴏᴜ ᴄᴀɴ ᴛᴀʟᴋ ɴᴏʀᴍᴀʟʟʏ —
ɴᴏ ᴄᴏᴍᴍᴀɴᴅ ɴᴇᴇᴅᴇᴅ.</blockquote>

<i>ᴛʀʏ ɪᴛ ɴᴏᴡ → sᴇɴᴅ ᴀ ʜᴇʟʟᴏ 👋</i>
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  KEYBOARDS  (colored buttons via Kurigram)
# ═══════════════════════════════════════════════════════════════════════════════

def _welcome_kb() -> InlineKeyboardMarkup:
    """
    7-button welcome keyboard:
      Row 1: Add Me (blue)
      Row 2: Support (green), Updates (green)
      Row 3: Help & Commands (blue)
      Row 4: Owner, Source (default)
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⛩️ ᴀᴅᴅ ᴍᴇ ʙᴀʙʏ ⛩️",
            url=_safe_startgroup_url(),
            style=enums.ButtonStyle.PRIMARY,
        )],
        [
            InlineKeyboardButton(
                "🍬 sᴜᴘᴘᴏʀᴛ 🍬",
                url=_safe_url(SUPPORT_URL),
                style=enums.ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                "🍹 ᴜᴘᴅᴀᴛᴇs 🍹",
                url=_safe_url(UPDATES_URL),
                style=enums.ButtonStyle.SUCCESS,
            ),
        ],
        [InlineKeyboardButton(
            "🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
            callback_data="elara:help",
            style=enums.ButtonStyle.PRIMARY,
        )],
        [
            InlineKeyboardButton(
                "🫧 ᴏᴡɴᴇʀ 🫧",
                url=_owner_link(),
                style=enums.ButtonStyle.DEFAULT,
            ),
            InlineKeyboardButton(
                "🍡 sᴏᴜʀᴄᴇ 🍡",
                callback_data="elara:about",
                style=enums.ButtonStyle.DEFAULT,
            ),
        ],
    ])


def _group_kb() -> InlineKeyboardMarkup:
    """
    Group welcome keyboard (shorter than private).
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⛩️ ᴀᴅᴅ ᴍᴇ ʙᴀʙʏ ⛩️",
                url=_safe_startgroup_url(),
                style=enums.ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                "🍬 sᴜᴘᴘᴏʀᴛ 🍬",
                url=_safe_url(SUPPORT_URL),
                style=enums.ButtonStyle.SUCCESS,
            ),
        ],
        [InlineKeyboardButton(
            "🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
            callback_data="elara:help",
            style=enums.ButtonStyle.PRIMARY,
        )],
    ])


_HELP_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🤖 ᴀɪ", callback_data="elara:ai",
                             style=enums.ButtonStyle.PRIMARY),
        InlineKeyboardButton("💕 sᴏᴄɪᴀʟ", callback_data="elara:social",
                             style=enums.ButtonStyle.SUCCESS),
    ],
    [InlineKeyboardButton("⌯ ʜᴏᴍᴇ ⌯", callback_data="elara:home",
                          style=enums.ButtonStyle.PRIMARY)],
])


_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="elara:help",
                          style=enums.ButtonStyle.PRIMARY)],
    [InlineKeyboardButton("⌯ ᴄʟᴏsᴇ ⌯", callback_data="elara:close",
                          style=enums.ButtonStyle.DANGER)],
])


# ═══════════════════════════════════════════════════════════════════════════════
#  LINK PREVIEW OPTIONS  (fixes deprecation warning)
# ═══════════════════════════════════════════════════════════════════════════════

_LPO = LinkPreviewOptions(is_disabled=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SEND / EDIT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _send_welcome(chat_id: int, caption: str, kb: InlineKeyboardMarkup) -> None:
    """
    Send the welcome message — with photo if configured, else plain text.
    Also handles FloodWait retries.
    """
    image = _pick_image()

    if image:
        try:
            await bot.send_photo(
                chat_id,
                photo=image,
                caption=caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
            return
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            return await _send_welcome(chat_id, caption, kb)
        except Exception as e:
            print(f"[start] photo failed, falling back to text: {e}")

    try:
        await bot.send_message(
            chat_id,
            caption,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            link_preview_options=_LPO,
        )
    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        await bot.send_message(
            chat_id,
            caption,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            link_preview_options=_LPO,
        )


async def _send_text(chat_id: int, text: str, kb: InlineKeyboardMarkup = None) -> None:
    """
    Send a plain text message with optional keyboard.
    """
    await bot.send_message(
        chat_id,
        text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
        link_preview_options=_LPO,
    )


async def _edit_safely(msg: Message, text: str, kb: InlineKeyboardMarkup = None) -> None:
    """
    Edit current message. If old message was a photo, delete it and send new text.
    """
    try:
        if getattr(msg, "photo", None):
            try:
                await msg.delete()
            except Exception:
                pass
            await _send_text(msg.chat.id, text, kb)
            return
        await msg.edit_text(
            text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            link_preview_options=_LPO,
        )
    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        await _edit_safely(msg, text, kb)
    except Exception as e:
        print(f"[edit] failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  LOGGER HELPER
# ═══════════════════════════════════════════════════════════════════════════════

async def _log_new_user(user: User) -> None:
    """
    Log a new /start user to LOGGER_ID (if configured).
    Silent failure — never blocks the actual /start.
    """
    if not LOGGER_ID:
        return
    try:
        uid = getattr(user, "id", 0)
        name = _sanitize_name(getattr(user, "first_name", None))
        username = getattr(user, "username", None)
        uname_display = f"@{_esc(username)}" if username else "N/A"

        await _send_text(
            LOGGER_ID,
            (
                "<b>#ɴᴇᴡᴜsᴇʀ sᴛᴀʀᴛᴇᴅ</b>\n\n"
                f"• <b>ɴᴀᴍᴇ:</b> <a href='tg://user?id={uid}'>{name}</a>\n"
                f"• <b>ɪᴅ:</b> <code>{uid}</code>\n"
                f"• <b>ᴜsᴇʀɴᴀᴍᴇ:</b> {uname_display}"
            ),
        )
    except Exception as e:
        print(f"[_log_new_user] failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  HANDLER —  /start
# ═══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("start"))
async def start_handler(_, message: Message) -> None:
    """
    Handle /start in private and group chats.
    """
    # ── Delete the user's /start command ────────────────────────────────────
    try:
        await message.delete()
    except Exception:
        pass

    # ── Save user to DB (silent fail) ───────────────────────────────────────
    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    # ── Private chat: full welcome ──────────────────────────────────────────
    if message.chat.type == ChatType.PRIVATE:
        caption = _welcome_caption(message.from_user)
        await _send_welcome(message.chat.id, caption, _welcome_kb())
        await _log_new_user(message.from_user)
        return

    # ── Group chat: short welcome ───────────────────────────────────────────
    chat_title = message.chat.title or "this chat"
    caption = _group_welcome_caption(message.from_user, chat_title)
    await _send_welcome(message.chat.id, caption, _group_kb())


# ═══════════════════════════════════════════════════════════════════════════════
#  HANDLER —  /help
# ═══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("help"))
async def help_handler(_, message: Message) -> None:
    """
    Handle /help — shows the help menu with AI/Social buttons.
    """
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    await _send_text(message.chat.id, HELP_MENU, _HELP_KB)


# ═══════════════════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

@bot.on_callback_query(
    filters.regex(r"^elara:(home|help|about|social|ai|chat|close)$")
)
async def start_callbacks(_, query: CallbackQuery) -> None:
    """
    Handle all start-menu button callbacks.
    """
    data = query.data.split(":", 1)[1]

    # ── CLOSE ───────────────────────────────────────────────────────────────
    if data == "close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── HOME ────────────────────────────────────────────────────────────────
    if data == "home":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        caption = _welcome_caption(query.from_user)
        await _send_welcome(query.message.chat.id, caption, _welcome_kb())
        return

    # ── HELP ────────────────────────────────────────────────────────────────
    if data == "help":
        await query.answer()
        await _edit_safely(query.message, HELP_MENU, _HELP_KB)
        return

    # ── AI ──────────────────────────────────────────────────────────────────
    if data == "ai":
        await query.answer()
        await _edit_safely(query.message, AI_HELP, _BACK_KB)
        return

    # ── SOCIAL ──────────────────────────────────────────────────────────────
    if data == "social":
        await query.answer()
        await _edit_safely(query.message, SOCIAL_HELP, _BACK_KB)
        return

    # ── ABOUT ───────────────────────────────────────────────────────────────
    if data == "about":
        await query.answer()
        await _edit_safely(query.message, ABOUT, _BACK_KB)
        return

    # ── CHAT MODE ───────────────────────────────────────────────────────────
    if data == "chat":
        await query.answer("Just send me a message 💬")
        await _edit_safely(query.message, CHAT_MODE, _BACK_KB)
        return