# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  handlers/start.py  —  Rich HTML + Proper table + Colored pill links
# --------------------------------------------------------------------------------

import asyncio
import json
import io
import re
from urllib.request import Request, urlopen

from pyrogram import enums, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

import config
from core.bot import app
from database.users import ensure_user

bot = app


# ─── Config ──────────────────────────────────────────────────────────────────
BOT_NAME        = getattr(config, "BOT_NAME", "Elara")
BOT_USERNAME    = (getattr(config, "BOT_USERNAME", "") or "").lstrip("@")
BOT_TOKEN       = getattr(config, "BOT_TOKEN", "")
SUPPORT_URL     = getattr(config, "SUPPORT_URL", "")
UPDATES_URL     = getattr(config, "UPDATES_URL", "")
OWNER_URL       = getattr(config, "OWNER_URL", "")
OWNER_ID        = getattr(config, "OWNER_ID", 0)
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

def _pick_image():
    if not START_IMAGE_URL:
        return None
    parts = [u.strip() for u in START_IMAGE_URL.split(",") if u.strip()]
    return parts[0] if parts else None


# ══════════════════════════════════════════════════════════════════════════════
#  BOT API CALLER
# ══════════════════════════════════════════════════════════════════════════════

async def _bot_api(method: str, payload: dict) -> dict:
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN missing"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    def _do():
        try:
            with urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "description": str(e)}
    return await asyncio.to_thread(_do)


# ══════════════════════════════════════════════════════════════════════════════
#  RICH HTML — PROPER TABLE with borders
#  ---------------------------------------------------------------
#  Telegram Rich Message supports real HTML <table> with <tr>/<td>/<th>
#  Renders exactly like OUTLAW X MUSIC.
# ══════════════════════════════════════════════════════════════════════════════

def _rich_welcome(user) -> str:
    uid = getattr(user, "id", 0)
    name = _esc(getattr(user, "first_name", None) or "there")
    bot = _esc(BOT_NAME)
    sup = _safe_url(SUPPORT_URL)
    upd = _safe_url(UPDATES_URL)

    # ✅ PROPER TABLE: <table><tr><th>...</th></tr><tr><td>...</td></tr></table>
    return f"""❍ ʜᴇʏ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🎶

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀ ғᴀsᴛ &amp; ᴘᴏᴡᴇʀғᴜʟ ᴛᴇʟᴇɢʀᴀᴍ <b>ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ʙᴏᴛ</b> ᴡɪᴛʜ sᴏᴍᴇ ᴀᴡᴇsᴏᴍᴇ ғᴇᴀᴛᴜʀᴇs.

<details open>
<summary>✦ ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs ✦</summary>

<table>
<tr><th>ғᴇᴀᴛᴜʀᴇ</th><th>ᴅᴇᴛᴀɪʟs</th></tr>
<tr><td>🤖 <b>ᴀɪ ᴄʜᴀᴛ</b></td><td>ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs ɪɴ ᴅᴍ &amp; ɢʀᴏᴜᴘs</td></tr>
<tr><td>🧠 <b>ᴍᴇᴍᴏʀʏ</b></td><td>ᴋᴇᴇᴘs ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ ғᴏʀ ʙᴇᴛᴛᴇʀ ʀᴇᴘʟɪᴇs</td></tr>
<tr><td>💕 <b>sᴏᴄɪᴀʟ</b></td><td>ʜᴜɢ, ᴋɪss, ᴍᴀʀʀɪᴀɢᴇ &amp; ᴍᴏʀᴇ ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs</td></tr>
<tr><td>⚡ <b>ғᴀsᴛ</b></td><td>ǫᴜɪᴄᴋ ᴀɪ ʀᴇsᴘᴏɴsᴇs ᴘᴏᴡᴇʀᴇᴅ ʙʏ ɢʀᴏǫ</td></tr>
</table>
</details>

<details open>
<summary>✧ ᴡʜʏ ᴄʜᴏᴏsᴇ ɪᴛ? ✧</summary>

⭐ sɪᴍᴘʟᴇ sʟᴀsʜ ᴄᴏᴍᴍᴀɴᴅs, ɴᴏ sᴇᴛᴜᴘ ɴᴇᴇᴅᴇᴅ.
🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ.
❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.

</details>

<blockquote>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <b>{bot}</b></blockquote>

🍬 <a href="{sup}"><b>sᴜᴘᴘᴏʀᴛ</b></a>   ·   🍹 <a href="{upd}"><b>ᴜᴘᴅᴀᴛᴇs</b></a>
"""


def _rich_help() -> str:
    return """📜 <b>ᴇʟᴀʀᴀ ʜᴇʟᴘ &amp; ᴄᴏᴍᴍᴀɴᴅs</b>

❍ ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ:

<details open>
<summary>✦ ᴄᴀᴛᴇɢᴏʀɪᴇs ✦</summary>

<table>
<tr><th>ᴄᴀᴛᴇɢᴏʀʏ</th><th>ᴅᴇsᴄʀɪᴘᴛɪᴏɴ</th></tr>
<tr><td>🤖 <b>ᴀɪ</b></td><td>ᴄʜᴀᴛ, ᴍᴇᴍᴏʀʏ &amp; ɢʀᴏᴜᴘ ᴀɪ ғᴇᴀᴛᴜʀᴇs</td></tr>
<tr><td>💕 <b>sᴏᴄɪᴀʟ</b></td><td>ғᴜɴ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs ғᴏʀ ɢʀᴏᴜᴘs</td></tr>
</table>
</details>

<i>ᴛᴀᴘ ᴀ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ</i> 👇
"""


def _rich_ai() -> str:
    return """🤖 <b>ᴇʟᴀʀᴀ ᴀɪ ᴄᴏᴍᴍᴀɴᴅs</b>

<details open>
<summary>💬 ᴄʜᴀᴛ ᴄᴏᴍᴍᴀɴᴅs</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴅᴇsᴄʀɪᴘᴛɪᴏɴ</th></tr>
<tr><td><code>/ai &lt;msg&gt;</code></td><td>ᴄʜᴀᴛ ᴡɪᴛʜ ᴇʟᴀʀᴀ ᴀɪ</td></tr>
<tr><td>ᴅᴍ ᴀɴʏ ᴍᴇssᴀɢᴇ</td><td>ᴀɪ ʀᴇᴘʟɪᴇs ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ</td></tr>
<tr><td><code>ᴇʟᴀʀᴀ ʜᴇʟʟᴏ</code></td><td>ɢʀᴏᴜᴘ ᴛʀɪɢɢᴇʀ</td></tr>
<tr><td><code>@BotUsername ʜɪ</code></td><td>ᴍᴇɴᴛɪᴏɴ ᴛʀɪɢɢᴇʀ</td></tr>
<tr><td>ʀᴇᴘʟʏ ᴛᴏ ᴇʟᴀʀᴀ</td><td>ᴄᴏɴᴛᴇxᴛ ᴄʜᴀᴛ</td></tr>
</table>
</details>

<blockquote>🧠 ʀᴇᴄᴇɴᴛ ᴄᴏɴᴛᴇxᴛ ᴜsᴇᴅ ғᴏʀ ɴᴀᴛᴜʀᴀʟ ʀᴇᴘʟɪᴇs.</blockquote>
"""


def _rich_social() -> str:
    return """💕 <b>ᴇʟᴀʀᴀ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅs</b>

ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ's ᴍᴇssᴀɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴛʜᴇsᴇ:

<details open>
<summary>💕 ᴀʟʟ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅs</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴀᴄᴛɪᴏɴ</th></tr>
<tr><td>🫂 <code>/hug</code></td><td>ʜᴜɢ ᴀ ᴜsᴇʀ</td></tr>
<tr><td>💋 <code>/kiss</code></td><td>ᴋɪss ᴀ ᴜsᴇʀ</td></tr>
<tr><td>🧛 <code>/bite</code></td><td>ʙɪᴛᴇ ᴀ ᴜsᴇʀ</td></tr>
<tr><td>👋 <code>/slap</code></td><td>sʟᴀᴘ ᴀ ᴜsᴇʀ</td></tr>
<tr><td>🦵 <code>/kick</code></td><td>ᴋɪᴄᴋ ᴀ ᴜsᴇʀ</td></tr>
<tr><td>🫶 <code>/cuddle</code></td><td>ᴄᴜᴅᴅʟᴇ ᴀ ᴜsᴇʀ</td></tr>
<tr><td>🫳 <code>/pat</code></td><td>ᴘᴀᴛ ᴀ ᴜsᴇʀ</td></tr>
<tr><td>✋ <code>/highfive</code></td><td>ʜɪɢʜ ғɪᴠᴇ</td></tr>
<tr><td>😏 <code>/flirt</code></td><td>ғʟɪʀᴛ</td></tr>
<tr><td>❤️ <code>/love</code></td><td>ʟᴏᴠᴇ ᴘᴇʀᴄᴇɴᴛᴀɢᴇ</td></tr>
<tr><td>💘 <code>/crush</code></td><td>ᴄʀᴜsʜ</td></tr>
<tr><td>💞 <code>/couple</code></td><td>ʀᴀɴᴅᴏᴍ ᴄᴏᴜᴘʟᴇ</td></tr>
<tr><td>💍 <code>/propose</code></td><td>ᴘʀᴏᴘᴏsᴇ</td></tr>
<tr><td>💒 <code>/marriage</code></td><td>ᴍᴀʀʀʏ</td></tr>
<tr><td>💔 <code>/divorce</code></td><td>ᴅɪᴠᴏʀᴄᴇ</td></tr>
</table>
</details>
"""


def _rich_about() -> str:
    return f"""📖 <b>ᴀʙᴏᴜᴛ ᴇʟᴀʀᴀ</b>

ᴇʟᴀʀᴀ ɪs ʏᴏᴜʀ ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ғᴏʀ ᴇᴠᴇʀʏᴅᴀʏ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs, ʀᴀɴᴅᴏᴍ ᴛʜᴏᴜɢʜᴛs ᴀɴᴅ ʟᴀᴛᴇ-ɴɪɢʜᴛ ᴄʜᴀᴛs. 🌙

<details open>
<summary>✦ ᴀʙᴏᴜᴛ ғᴇᴀᴛᴜʀᴇs ✦</summary>

<table>
<tr><th>ғᴇᴀᴛᴜʀᴇ</th><th>ᴅᴇᴛᴀɪʟs</th></tr>
<tr><td>💬 ᴛᴀʟᴋ</td><td>ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ</td></tr>
<tr><td>🧠 ᴍᴇᴍᴏʀʏ</td><td>ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ</td></tr>
<tr><td>💕 sᴏᴄɪᴀʟ</td><td>ғᴜɴ ɢʀᴏᴜᴘ ᴄᴏᴍᴍᴀɴᴅs</td></tr>
<tr><td>⚡ sᴘᴇᴇᴅ</td><td>ғᴀsᴛ ɢʀᴏǫ ᴀɪ ʀᴇsᴘᴏɴsᴇs</td></tr>
</table>
</details>

<blockquote><i>ᴊᴜsᴛ ᴛᴀʟᴋ ᴛᴏ ᴇʟᴀʀᴀ. ɴᴏ sᴇᴛᴜᴘ.</i></blockquote>
"""


# ══════════════════════════════════════════════════════════════════════════════
#  KEYBOARDS — Colored buttons (Kurigram)
# ══════════════════════════════════════════════════════════════════════════════

def _welcome_kb() -> InlineKeyboardMarkup:
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
                "📖 ᴀʙᴏᴜᴛ 📖",
                callback_data="elara:about",
                style=enums.ButtonStyle.DEFAULT,
            ),
        ],
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


# ══════════════════════════════════════════════════════════════════════════════
#  SEND HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _kb_to_dict(kb):
    return {
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


async def _send_rich(chat_id, html, kb, image=None):
    """Send via Rich Message API. Fallback to photo/text."""
    payload = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
        "reply_markup": _kb_to_dict(kb),
    }
    if image:
        payload["rich_message"]["photo_url"] = image

    result = await _bot_api("sendRichMessage", payload)
    if result.get("ok"):
        return

    print(f"[rich] failed: {result.get('description')}")

    if image:
        try:
            # Telegram captions do not support the Rich Message <table>/<details> HTML.
            # Keep the existing rich message untouched; only the fallback caption is sanitized.
            plain_caption = re.sub(r"<[^>]+>", "", html).strip()
            return await bot.send_photo(
                chat_id, photo=image, caption=plain_caption,
                reply_markup=kb, parse_mode=None,
            )
        except Exception:
            # If Telegram cannot fetch the configured URL directly, download it first.
            try:
                req = Request(image, headers={"User-Agent": "Mozilla/5.0"})
                data = await asyncio.to_thread(lambda: urlopen(req, timeout=20).read())
                return await bot.send_photo(
                    chat_id, photo=io.BytesIO(data), caption=plain_caption,
                    reply_markup=kb, parse_mode=None,
                )
            except Exception as e:
                print(f"[start] image fallback failed: {e}")

    return await bot.send_message(
        chat_id, html, reply_markup=kb, parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def _edit_rich(msg, html, kb):
    try:
        payload = {
            "chat_id": msg.chat.id,
            "message_id": msg.id,
            "rich_message": {"html": html},
            "reply_markup": _kb_to_dict(kb),
        }
        result = await _bot_api("editMessageText", payload)
        if result.get("ok"):
            return
    except Exception:
        pass

    try:
        if getattr(msg, "photo", None):
            try:
                await msg.delete()
            except Exception:
                pass
            await bot.send_message(
                msg.chat.id, html, reply_markup=kb,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            return
        await msg.edit_text(
            html, reply_markup=kb, parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception as e:
        print(f"[edit] failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("start"))
async def start_handler(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    try:
        await _send_rich(
            message.chat.id,
            _rich_welcome(message.from_user),
            _welcome_kb(),
            _pick_image(),
        )
    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        await _send_rich(
            message.chat.id,
            _rich_welcome(message.from_user),
            _welcome_kb(),
            _pick_image(),
        )


@bot.on_message(filters.command("help"))
async def help_handler(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass

    await _send_rich(message.chat.id, _rich_help(), _HELP_KB, _pick_image())


@bot.on_callback_query(filters.regex(r"^elara:(home|help|about|social|ai|close)$"))
async def cb(_, q: CallbackQuery):
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
        await _send_rich(
            q.message.chat.id,
            _rich_welcome(q.from_user),
            _welcome_kb(),
            _pick_image(),
        )
        return

    if d == "help":
        await q.answer()
        await _edit_rich(q.message, _rich_help(), _HELP_KB)
        return

    if d == "ai":
        await q.answer()
        await _edit_rich(q.message, _rich_ai(), _BACK_KB)
        return

    if d == "social":
        await q.answer()
        await _edit_rich(q.message, _rich_social(), _BACK_KB)
        return

    if d == "about":
        await q.answer()
        await _edit_rich(q.message, _rich_about(), _BACK_KB)
        return