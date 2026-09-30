# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  handlers/start.py — Rich HTML + Tables + 3 Prefixes + Inline Image
# --------------------------------------------------------------------------------

PREFIXES = ["/", "!", "."]

import asyncio
import json
import os
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


# ─── Config ────────────────────────────────────────────────────────────────────
BOT_NAME        = getattr(config, "BOT_NAME", "Elara")
BOT_USERNAME    = (getattr(config, "BOT_USERNAME", "") or "").lstrip("@")
BOT_TOKEN       = getattr(config, "BOT_TOKEN", "")
SUPPORT_URL     = getattr(config, "SUPPORT_URL", "")
UPDATES_URL     = getattr(config, "UPDATES_URL", "")
OWNER_URL       = getattr(config, "OWNER_URL", "")
OWNER_ID        = getattr(config, "OWNER_ID", 0)

# ✅ Hardcoded Start Image URL
START_IMAGE_URL = "https://myimgs.org/storage/images/49868/26203.png"


# ─── Helpers ──────────────────────────────────────────────────────────────────
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


# ─── Bot API caller ───────────────────────────────────────────────────────────
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
#  RICH HTML PAGES
# ══════════════════════════════════════════════════════════════════════════════

def _rich_welcome(user) -> str:
    uid = getattr(user, "id", 0)
    name = _esc(getattr(user, "first_name", None) or "there")
    bot = _esc(BOT_NAME)
    sup = _safe_url(SUPPORT_URL)
    upd = _safe_url(UPDATES_URL)
    img = START_IMAGE_URL

    return f"""<img src="{img}" />
ᴡᴇʟᴄᴏᴍᴇ <a href="tg://user?id={uid}">{name}</a>, ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ! 🎉

ɪ ᴀᴍ <b>「 {bot} 」</b> — ᴀɴ ᴀɪ ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇʀ ᴛʜᴀᴛ ᴋᴇᴇᴘꜱ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴄʟᴇᴀɴ.

<details open>
<summary>✨ ᴍʏ ᴛᴏᴘ ꜰᴇᴀᴛᴜʀᴇꜱ ✨</summary>

<table>
<tr><th>ꜰᴇᴀᴛᴜʀᴇ</th><th>ᴅᴇᴛᴀɪʟꜱ</th></tr>
<tr><td>🤖 <b>AI ᴄʜᴀᴛ</b></td><td>ɴᴀᴛᴜʀᴀʟ ᴀɪ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴꜱ</td></tr>
<tr><td>🧠 <b>ᴍᴇᴍᴏʀʏ</b></td><td>ᴋᴇᴇᴘꜱ ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ</td></tr>
<tr><td>💕 <b>ꜱᴏᴄɪᴀʟ</b></td><td>ʜᴜɢ, ᴋɪꜱꜱ, ᴀɴᴅ ᴍᴀɴʏ ᴍᴏʀᴇ</td></tr>
<tr><td>💰 <b>ᴇᴄᴏɴᴏᴍʏ</b></td><td>ʀᴏʙ, ᴋɪʟʟ, ᴛᴏᴘ ʀᴀɴᴋ</td></tr>
<tr><td>⚡ <b>ꜰᴀꜱᴛ</b></td><td>ǫᴜɪᴄᴋ ʀᴇꜱᴘᴏɴꜱᴇꜱ</td></tr>
</table>
</details>

<details open>
<summary>🎯 ǫᴜɪᴄᴋ ꜱᴛᴀʀᴛ</summary>

❶ ᴛᴀᴘ <b>ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ</b> ʙᴜᴛᴛᴏɴ
❷ ᴀᴅᴅ ᴍᴇ ᴀꜱ ᴀᴅᴍɪɴ
❸ ᴇɴᴊᴏʏ ᴘʀᴇᴍɪᴜᴍ ꜰᴇᴀᴛᴜʀᴇꜱ

</details>

<blockquote>ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <a href="{upd}"><b>{bot}</b></a></blockquote>

🍬 <a href="{sup}"><b>ꜱᴜᴘᴘᴏʀᴛ</b></a>   ·   🍹 <a href="{upd}"><b>ᴜᴘᴅᴀᴛᴇꜱ</b></a>
"""


def _rich_help() -> str:
    return """📜 <b>ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ</b>

ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ ꜱᴜᴘᴘᴏʀᴛ <b>3 ᴘʀᴇꜰɪxᴇꜱ</b>:
<code>.</code>  <code>/</code>  <code>!</code>

<details open>
<summary>📌 ᴘʀᴇꜰɪx ᴇxᴀᴍᴘʟᴇꜱ</summary>

<table>
<tr><th>ᴘʀᴇꜰɪx</th><th>ᴇxᴀᴍᴘʟᴇ</th><th>ꜱᴛᴀᴛᴜꜱ</th></tr>
<tr><td><code>.</code>  ᴅᴏᴛ</td><td><code>.ban</code></td><td>✅ ᴡᴏʀᴋꜱ</td></tr>
<tr><td><code>/</code>  ꜱʟᴀꜱʜ</td><td><code>/ban</code></td><td>✅ ᴡᴏʀᴋꜱ</td></tr>
<tr><td><code>!</code>  ᴇxᴄʟᴀᴍᴀᴛɪᴏɴ</td><td><code>!ban</code></td><td>✅ ᴡᴏʀᴋꜱ</td></tr>
</table>
</details>

<details open>
<summary>🤖 ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴀᴛᴇɢᴏʀɪᴇꜱ</summary>

<table>
<tr><th>ᴄᴀᴛᴇɢᴏʀʏ</th><th>ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ</th></tr>
<tr><td>🤖 <b>AI</b></td><td>ᴄʜᴀᴛ, ɪᴍᴀɢᴇ ɢᴇɴᴇʀᴀᴛɪᴏɴ</td></tr>
<tr><td>💕 <b>ꜱᴏᴄɪᴀʟ</b></td><td>ꜰᴜɴ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴꜱ</td></tr>
<tr><td>💰 <b>ᴇᴄᴏɴᴏᴍʏ</b></td><td>ᴇᴅᴏʟʟᴇʀꜱ, ʀᴏʙ, ᴋɪʟʟ, ᴛᴏᴘ</td></tr>
<tr><td>🛡️ <b>ᴍᴀɴᴀɢᴇᴍᴇɴᴛ</b></td><td>ɢʀᴏᴜᴘ ᴀᴅᴍɪɴ ᴛᴏᴏʟꜱ</td></tr>
</table>
</details>

<i>ᴛᴀᴘ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ</i> 👇
"""


def _rich_ai() -> str:
    return """🤖 <b>ᴇʟᴀʀᴀ ᴀɪ ᴄᴏᴍᴍᴀɴᴅꜱ</b>

<i>ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code></i>

<details open>
<summary>💬 ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴋᴀᴀᴍ</th></tr>
<tr><td><code>.ai &lt;msg&gt;</code></td><td>ᴄʜᴀᴛ ᴡɪᴛʜ ᴇʟᴀʀᴀ ᴀɪ</td></tr>
<tr><td>ᴅᴍ ᴍᴇꜱꜱᴀɢᴇ</td><td>ᴅɪʀᴇᴄᴛ ᴀɪ ᴄʜᴀᴛ</td></tr>
<tr><td><code>ᴇʟᴀʀᴀ ʜᴇʟʟᴏ</code></td><td>ɢʀᴏᴜᴘ ᴛʀɪɢɢᴇʀ ᴡᴏʀᴅ</td></tr>
<tr><td><code>@BotUsername ʜɪ</code></td><td>ᴍᴇɴᴛɪᴏɴ ᴛʀɪɢɢᴇʀ</td></tr>
<tr><td>ʀᴇᴘʟʏ ᴛᴏ ᴇʟᴀʀᴀ</td><td>ᴄᴏɴᴛᴇxᴛ ᴄʜᴀᴛ</td></tr>
</table>
</details>

<blockquote>🧠 ᴇʟᴀʀᴀ ʀᴇᴍᴇᴍʙᴇʀꜱ ʀᴇᴄᴇɴᴛ ᴄᴏɴᴛᴇxᴛ ꜰᴏʀ ɴᴀᴛᴜʀᴀʟ ᴄʜᴀᴛꜱ.</blockquote>
"""


def _rich_social() -> str:
    return """💕 <b>ᴇʟᴀʀᴀ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅꜱ</b>

<i>ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code></i>

<details open>
<summary>💕 ᴀʟʟ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅꜱ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴀᴄᴛɪᴏɴ</th></tr>
<tr><td>🫂 <code>.hug</code></td><td>ʜᴜɢ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>💋 <code>.kiss</code></td><td>ᴋɪꜱꜱ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>🧛 <code>.bite</code></td><td>ʙɪᴛᴇ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>👋 <code>.slap</code></td><td>ꜱʟᴀᴘ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>🦵 <code>.kick</code></td><td>ᴋɪᴄᴋ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>🫶 <code>.cuddle</code></td><td>ᴄᴜᴅᴅʟᴇ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>🫳 <code>.pat</code></td><td>ᴘᴀᴛ ᴀ ᴜꜱᴇʀ</td></tr>
<tr><td>✋ <code>.highfive</code></td><td>ʜɪɢʜ ꜰɪᴠᴇ</td></tr>
<tr><td>😏 <code>.flirt</code></td><td>ꜰʟɪʀᴛ</td></tr>
<tr><td>❤️ <code>.love</code></td><td>ʟᴏᴠᴇ ᴘᴇʀᴄᴇɴᴛᴀɢᴇ</td></tr>
<tr><td>💘 <code>.crush</code></td><td>ᴄʀᴜꜱʜ</td></tr>
<tr><td>💞 <code>.couple</code></td><td>ʀᴀɴᴅᴏᴍ ᴄᴏᴜᴘʟᴇ</td></tr>
<tr><td>💍 <code>.propose</code></td><td>ᴘʀᴏᴘᴏꜱᴇ</td></tr>
<tr><td>💒 <code>.marriage</code></td><td>ᴍᴀʀʀɪᴀɢᴇ</td></tr>
<tr><td>💔 <code>.divorce</code></td><td>ᴅɪᴠᴏʀᴄᴇ</td></tr>
</table>
</details>

<blockquote>💡 ᴜꜱᴇ <code>.hug @ᴜꜱᴇʀ</code> ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ'ꜱ ᴍᴇꜱꜱᴀɢᴇ.</blockquote>
"""


def _rich_economy() -> str:
    return """💰 <b>ᴇʟᴀʀᴀ ᴇᴄᴏɴᴏᴍʏ</b>

<i>ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code></i>

<details open>
<summary>💵 ᴇᴀʀɴ & ɢʀᴏᴡ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴋᴀᴀᴍ</th></tr>
<tr><td><code>.bal</code></td><td>ᴘʀᴏꜰɪʟᴇ & ʙᴀʟᴀɴᴄᴇ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.daily</code></td><td>2,000 ᴇᴅᴏʟʟᴇʀꜱ ᴄʟᴀɪᴍ <i>(ᴅᴍ)</i></td></tr>
<tr><td><code>.wallet +300</code></td><td>ᴡᴀʟʟᴇᴛ ᴍᴇ ᴅᴀʟᴏ</td></tr>
<tr><td><code>.wallet -300</code></td><td>ᴡᴀʟʟᴇᴛ ꜱᴇ ɴɪᴋᴀʟᴏ</td></tr>
<tr><td><code>.give 500</code></td><td>ᴋɪꜱɪ ᴋᴏ ᴅᴏ <i>(ʀᴇᴘʟʏ)</i></td></tr>
</table>
</details>

<details open>
<summary>⚔️ ᴋɪʟʟ & ʀᴏʙ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴋᴀᴀᴍ</th></tr>
<tr><td>⚔️ <code>.kill</code></td><td>ᴋɪꜱɪ ᴋᴏ ᴍᴀᴀʀᴏ <i>(ʀᴇᴘʟʏ)</i></td></tr>
<tr><td>💸 <code>.rob [amount]</code></td><td>ᴋɪꜱɪ ᴋᴏ ʀᴏʙ ᴋᴀʀᴏ <i>(ʀᴇᴘʟʏ)</i></td></tr>
<tr><td>✨ <code>.revive</code></td><td>ᴅᴇᴀᴅ ᴜꜱᴇʀ ᴋᴏ ᴢɪɴᴅᴀ ᴋᴀʀᴏ (500 $)</td></tr>
<tr><td>🛡️ <code>.protect 1d</code></td><td>24ʜ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ (500 $)</td></tr>
<tr><td>🔎 <code>.check</code></td><td>ᴜꜱᴇʀ ᴅᴇᴛᴀɪʟꜱ (500 $)</td></tr>
</table>
</details>

<details open>
<summary>🛒 ꜱʜᴏᴘ & ɢɪꜰᴛꜱ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴋᴀᴀᴍ</th></tr>
<tr><td><code>.shop</code></td><td>ꜱʜᴏᴘ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.buy &lt;id&gt;</code></td><td>ɪᴛᴇᴍ ᴋʜᴀʀɪᴅᴏ</td></tr>
<tr><td><code>.inventory</code></td><td>ᴀᴘɴᴇ ɪᴛᴇᴍꜱ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.sell &lt;id&gt;</code></td><td>ɪᴛᴇᴍ ʙᴇᴄʜᴏ (50% ʀᴇꜰᴜɴᴅ)</td></tr>
<tr><td><code>.gift &lt;id&gt;</code></td><td>ɪᴛᴇᴍ ɢɪꜰᴛ ᴋᴀʀᴏ <i>(ʀᴇᴘʟʏ)</i></td></tr>
</table>
</details>

<details open>
<summary>🏆 ʀᴀɴᴋ & ᴄᴜꜱᴛᴏᴍ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴋᴀᴀᴍ</th></tr>
<tr><td>🏆 <code>.toprich</code></td><td>ᴛᴏᴘ 10 ʀɪᴄʜᴇꜱᴛ</td></tr>
<tr><td>⚔️ <code>.topkillers</code></td><td>ᴛᴏᴘ 10 ᴋɪʟʟᴇʀꜱ</td></tr>
<tr><td>😎 <code>.setemoji 😎</code></td><td>ᴄᴜꜱᴛᴏᴍ ᴇᴍᴏᴊɪ (2000 $)</td></tr>
</table>
</details>

<blockquote>💰 ᴀʟʟ ᴛᴀx & ꜰᴇᴇꜱ ɢᴏ ᴛᴏ ᴇʟᴀʀᴀ'ꜱ ᴠᴀᴜʟᴛ.</blockquote>
"""


def _rich_management() -> str:
    return """🛡️ <b>ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ</b>

<i>ᴀʟʟ ᴛʜᴇ ᴛᴏᴏʟꜱ ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ.</i>

<details open>
<summary>📂 ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴀᴛᴇɢᴏʀɪᴇꜱ</summary>

<table>
<tr><th>ᴄᴀᴛᴇɢᴏʀʏ</th><th>ᴋᴀᴀᴍ</th></tr>
<tr><td>👑 <b>ᴀᴅᴍɪɴ</b></td><td>ᴘʀᴏᴍᴏᴛᴇ, ᴅᴇᴍᴏᴛᴇ, ᴀᴅᴍɪɴ ʟɪꜱᴛ</td></tr>
<tr><td>🔨 <b>ʙᴀɴꜱ</b></td><td>ʙᴀɴ, ᴍᴜᴛᴇ, ᴋɪᴄᴋ</td></tr>
<tr><td>🔎 <b>ꜰɪʟᴛᴇʀꜱ</b></td><td>ᴀᴜᴛᴏ ʀᴇᴘʟʏ ᴛʀɪɢɢᴇʀꜱ</td></tr>
<tr><td>👋 <b>ɢʀᴇᴇᴛɪɴɢꜱ</b></td><td>ᴡᴇʟᴄᴏᴍᴇ & ɢᴏᴏᴅʙʏᴇ</td></tr>
<tr><td>🔒 <b>ʟᴏᴄᴋꜱ</b></td><td>ʟᴏᴄᴋ ᴄᴏɴᴛᴇɴᴛ ᴛʏᴘᴇꜱ</td></tr>
<tr><td>📌 <b>ᴘɪɴꜱ</b></td><td>ᴘɪɴ & ᴜɴᴘɪɴ ᴍᴇꜱꜱᴀɢᴇꜱ</td></tr>
<tr><td>🧹 <b>ᴘᴜʀɢᴇꜱ</b></td><td>ʙᴜʟᴋ ᴍᴇꜱꜱᴀɢᴇ ᴅᴇʟᴇᴛᴇ</td></tr>
<tr><td>🚨 <b>ʀᴇᴘᴏʀᴛꜱ</b></td><td>ᴜꜱᴇʀ ʀᴇᴘᴏʀᴛꜱ</td></tr>
<tr><td>⚠️ <b>ᴡᴀʀɴɪɴɢꜱ</b></td><td>ᴡᴀʀɴ ꜱʏꜱᴛᴇᴍ</td></tr>
<tr><td>🏷️ <b>ᴛᴀɢ</b></td><td>ᴛᴀɢ ᴀʟʟ ᴍᴇᴍʙᴇʀꜱ</td></tr>
</table>
</details>

<blockquote>ᴛᴀᴘ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ ᴛᴏ ᴠɪᴇᴡ ᴄᴏᴍᴍᴀɴᴅꜱ 👇</blockquote>
"""


# ── Sub-page builder ──────────────────────────────────────────────────────────

def _management_page(title: str, intro: str, rows_html: str, tip: str = "") -> str:
    tip_block = f"\n<blockquote>{tip}</blockquote>\n" if tip else ""
    return f"""🛡️ <b>{title}</b>

<i>{intro}</i>

<details open>
<summary>📖 ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴏᴍᴍᴀɴᴅꜱ</summary>

<table>
<tr><th>ᴄᴏᴍᴍᴀɴᴅ</th><th>ᴋᴀᴀᴍ</th></tr>
{rows_html}
</table>
</details>
{tip_block}"""


def _rich_admin() -> str:
    return _management_page(
        "ᴀᴅᴍɪɴ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ",
        "ᴘʀᴏᴍᴏᴛᴇ, ᴅᴇᴍᴏᴛᴇ ᴀɴᴅ ᴍᴀɴᴀɢᴇ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴꜱ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.promote [0-3]</code></td><td>ᴜꜱᴇʀ ᴋᴏ ᴀᴅᴍɪɴ ʙᴀɴᴀᴏ</td></tr>
<tr><td><code>.demote</code></td><td>ᴀᴅᴍɪɴ ʜᴀᴛᴀᴏ</td></tr>
<tr><td><code>.add &lt;rights&gt;</code></td><td>ꜱᴇʟᴇᴄᴛɪᴠᴇ ʀɪɢʜᴛꜱ ᴅᴏ</td></tr>
<tr><td><code>.remove &lt;rights&gt;</code></td><td>ꜱᴇʟᴇᴄᴛɪᴠᴇ ʀɪɢʜᴛꜱ ʜᴀᴛᴀᴏ</td></tr>
<tr><td><code>.adminlist</code></td><td>ᴀᴅᴍɪɴ ʟɪꜱᴛ ᴅᴇᴋʜᴏ</td></tr>""",
        "💡 ᴘʀᴏᴍᴏᴛᴇ ᴍᴏᴅᴇꜱ: <code>0</code> ᴛᴇᴍᴘ, <code>1</code> ᴊᴜɴɪᴏʀ, <code>2</code> ᴀꜱꜱɪꜱᴛᴀɴᴛ, <code>3</code> ꜰᴜʟʟ"
    )


def _rich_bans() -> str:
    return _management_page(
        "ʙᴀɴ & ᴍᴜᴛᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ",
        "ᴜꜱᴇʀꜱ ᴋᴏ ʀᴇꜱᴛʀɪᴄᴛ ᴋᴀʀɴᴇ ᴋᴇ ᴄᴏᴍᴍᴀɴᴅꜱ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td>🔨 <code>.ban</code></td><td>ᴘᴇʀᴍᴀɴᴇɴᴛ ʙᴀɴ</td></tr>
<tr><td>⏱️ <code>.tban 4h</code></td><td>ᴛᴇᴍᴘᴏʀᴀʀʏ ʙᴀɴ</td></tr>
<tr><td>🤫 <code>.sban</code></td><td>ꜱɪʟᴇɴᴛ ʙᴀɴ</td></tr>
<tr><td>🗑️ <code>.dban</code></td><td>ᴅᴇʟᴇᴛᴇ + ʙᴀɴ</td></tr>
<tr><td>🔇 <code>.mute</code></td><td>ᴍᴜᴛᴇ ᴜꜱᴇʀ</td></tr>
<tr><td>⏱️ <code>.tmute 2h</code></td><td>ᴛᴇᴍᴘᴏʀᴀʀʏ ᴍᴜᴛᴇ</td></tr>
<tr><td>👢 <code>.kick</code></td><td>ᴋɪᴄᴋ ᴜꜱᴇʀ</td></tr>
<tr><td>🔓 <code>.unban</code></td><td>ᴜɴʙᴀɴ</td></tr>
<tr><td>🔊 <code>.unmute</code></td><td>ᴜɴᴍᴜᴛᴇ</td></tr>""",
        "⏱️ ᴛɪᴍᴇ ꜰᴏʀᴍᴀᴛ: <code>4m</code> <code>3h</code> <code>6d</code> <code>5w</code>"
    )


def _rich_filters() -> str:
    return _management_page(
        "ꜰɪʟᴛᴇʀꜱ",
        "ᴀᴜᴛᴏ ʀᴇᴘʟʏ ᴛʀɪɢɢᴇʀꜱ ꜱᴇᴛ ᴋᴀʀᴏ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.filter &lt;trigger&gt; &lt;reply&gt;</code></td><td>ɴᴀʏᴀ ꜰɪʟᴛᴇʀ</td></tr>
<tr><td><code>.filters</code></td><td>ꜱᴀᴀʀᴇ ꜰɪʟᴛᴇʀꜱ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.stopfilter &lt;trigger&gt;</code></td><td>ᴇᴋ ʜᴀᴛᴀᴏ</td></tr>
<tr><td><code>.stopall</code></td><td>ꜱᴀᴀʀᴇ ʜᴀᴛᴀᴏ</td></tr>""",
        "💡 ᴛʀɪɢɢᴇʀ ᴋᴇꜱ-ɪɴꜱᴇɴꜱɪᴛɪᴠᴇ. ᴍᴜʟᴛɪ ᴡᴏʀᴅ: <code>.filter \"hello bro\" ʜɪ!</code>"
    )


def _rich_greetings() -> str:
    return _management_page(
        "ɢʀᴇᴇᴛɪɴɢꜱ",
        "ᴡᴇʟᴄᴏᴍᴇ & ɢᴏᴏᴅʙʏᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ᴍᴀɴᴀɢᴇ ᴋᴀʀᴏ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.welcome on/off</code></td><td>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏɢɢʟᴇ</td></tr>
<tr><td><code>.goodbye on/off</code></td><td>ɢᴏᴏᴅʙʏᴇ ᴛᴏɢɢʟᴇ</td></tr>
<tr><td><code>.setwelcome &lt;text&gt;</code></td><td>ᴄᴜꜱᴛᴏᴍ ᴡᴇʟᴄᴏᴍᴇ</td></tr>
<tr><td><code>.resetwelcome</code></td><td>ᴅᴇꜰᴀᴜʟᴛ ᴡᴇʟᴄᴏᴍᴇ</td></tr>
<tr><td><code>.setgoodbye &lt;text&gt;</code></td><td>ᴄᴜꜱᴛᴏᴍ ɢᴏᴏᴅʙʏᴇ</td></tr>
<tr><td><code>.resetgoodbye</code></td><td>ᴅᴇꜰᴀᴜʟᴛ ɢᴏᴏᴅʙʏᴇ</td></tr>
<tr><td><code>.cleanwelcome on/off</code></td><td>5ᴍɪɴ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ</td></tr>""",
        "📝 ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀꜱ: <code>{name}</code> <code>{mention}</code> <code>{id}</code> <code>{chat}</code>"
    )


def _rich_locks() -> str:
    return _management_page(
        "ʟᴏᴄᴋꜱ",
        "ɢʀᴏᴜᴘ ᴍᴇ ᴄᴏɴᴛᴇɴᴛ ᴛʏᴘᴇꜱ ʟᴏᴄᴋ ᴋᴀʀᴏ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.lock &lt;types&gt;</code></td><td>ᴛʏᴘᴇꜱ ʟᴏᴄᴋ ᴋᴀʀᴏ</td></tr>
<tr><td><code>.unlock &lt;types&gt;</code></td><td>ᴛʏᴘᴇꜱ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴏ</td></tr>
<tr><td><code>.locks</code></td><td>ᴀᴄᴛɪᴠᴇ ʟᴏᴄᴋꜱ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.locktypes</code></td><td>ꜱᴀᴀʀᴇ ᴛʏᴘᴇꜱ ʟɪꜱᴛ</td></tr>
<tr><td><code>.lockwarns on/off</code></td><td>ᴡᴀʀɴ ᴛᴏɢɢʟᴇ</td></tr>""",
        "🔐 ᴛʏᴘᴇꜱ: <code>stickers</code> <code>gif</code> <code>text</code> <code>photo</code> <code>video</code> <code>music</code> <code>files</code> <code>voice msg</code> <code>video msg</code> <code>link</code> <code>all</code>"
    )


def _rich_pins() -> str:
    return _management_page(
        "ᴘɪɴꜱ",
        "ᴍᴇꜱꜱᴀɢᴇꜱ ᴘɪɴ ᴋᴀʀᴏ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.pin</code></td><td>ʀᴇᴘʟʏ ᴡᴀʟɪ ᴘɪɴ</td></tr>
<tr><td><code>.pin loud</code></td><td>ɴᴏᴛɪꜰʏ ᴋᴇ ꜱᴀᴀᴛʜ ᴘɪɴ</td></tr>
<tr><td><code>.unpin</code></td><td>ᴘɪɴ ʜᴀᴛᴀᴏ</td></tr>
<tr><td><code>.pinned</code></td><td>ᴄᴜʀʀᴇɴᴛ ᴘɪɴ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.unpinall</code></td><td>ꜱᴀᴀʀᴇ ᴘɪɴꜱ ʜᴀᴛᴀᴏ</td></tr>""",
        "📌 ᴘɪɴ ʀɪɢʜᴛ ᴡᴀʟᴇ ᴀᴅᴍɪɴꜱ ᴏɴʟʏ ᴜꜱᴇ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ."
    )


def _rich_purges() -> str:
    return _management_page(
        "ᴘᴜʀɢᴇꜱ",
        "ʙᴜʟᴋ ᴍᴇꜱꜱᴀɢᴇ ᴅᴇʟᴇᴛᴇ ᴋᴀʀᴏ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.purge</code></td><td>ʀᴇᴘʟʏ ꜱᴇ ꜱᴀʙ ᴅᴇʟᴇᴛᴇ</td></tr>
<tr><td><code>.purge 50</code></td><td>50 ᴍᴇꜱꜱᴀɢᴇꜱ</td></tr>
<tr><td><code>.spurge</code></td><td>ꜱɪʟᴇɴᴛ ᴘᴜʀɢᴇ</td></tr>
<tr><td><code>.del</code> / <code>.d</code></td><td>ꜱɪɴɢʟᴇ ᴅᴇʟᴇᴛᴇ</td></tr>
<tr><td><code>.purgefrom</code></td><td>ꜱᴛᴀʀᴛ ᴍᴀʀᴋ</td></tr>
<tr><td><code>.purgeto</code></td><td>ᴛɪʟʟ ᴍᴀʀᴋ ᴅᴇʟᴇᴛᴇ</td></tr>""",
        "⚠️ ᴍᴀx 1000 ᴍᴇꜱꜱᴀɢᴇꜱ ᴇᴋ ʙᴀᴀʀ ᴍᴇ."
    )


def _rich_reports() -> str:
    return _management_page(
        "ʀᴇᴘᴏʀᴛꜱ",
        "ᴜꜱᴇʀꜱ ᴀᴅᴍɪɴꜱ ᴋᴏ ʀᴇᴘᴏʀᴛ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.report</code></td><td>ʀᴇᴘʟʏ ᴡᴀʟɪ ʀᴇᴘᴏʀᴛ</td></tr>
<tr><td><code>@admin</code></td><td>ᴍᴇɴᴛɪᴏɴ ꜱᴇ ʀᴇᴘᴏʀᴛ</td></tr>
<tr><td><code>.reports on/off</code></td><td>ꜱʏꜱᴛᴇᴍ ᴛᴏɢɢʟᴇ</td></tr>
<tr><td><code>.reports</code></td><td>ꜱᴛᴀᴛᴜꜱ ᴅᴇᴋʜᴏ</td></tr>""",
        "🚨 ᴀᴅᴍɪɴꜱ ᴋᴏ ᴍᴇɴᴛɪᴏɴ ʜᴏᴛᴀ ʜᴀɪ ʀᴇᴘᴏʀᴛ ᴍᴇ."
    )


def _rich_warnings() -> str:
    return _management_page(
        "ᴡᴀʀɴɪɴɢꜱ",
        "ᴜꜱᴇʀ ᴡᴀʀɴ ꜱʏꜱᴛᴇᴍ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td><code>.warn</code></td><td>ᴡᴀʀɴ ᴅᴏ</td></tr>
<tr><td><code>.dwarn</code></td><td>ᴅᴇʟᴇᴛᴇ + ᴡᴀʀɴ</td></tr>
<tr><td><code>.swarn</code></td><td>ꜱɪʟᴇɴᴛ ᴡᴀʀɴ</td></tr>
<tr><td><code>.warns</code></td><td>ᴡᴀʀɴ ʟɪꜱᴛ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.rmwarn</code></td><td>ʟᴀᴛᴇꜱᴛ ᴡᴀʀɴ ʜᴀᴛᴀᴏ</td></tr>
<tr><td><code>.resetwarn</code></td><td>ꜱᴀᴀʀᴇ ᴡᴀʀɴꜱ ʜᴀᴛᴀᴏ</td></tr>
<tr><td><code>.warnings</code></td><td>ꜱᴇᴛᴛɪɴɢꜱ ᴅᴇᴋʜᴏ</td></tr>
<tr><td><code>.warnmode &lt;mode&gt;</code></td><td>ᴘᴜɴɪꜱʜ ᴍᴏᴅᴇ ꜱᴇᴛ</td></tr>
<tr><td><code>.warnlimit &lt;1-100&gt;</code></td><td>ᴍᴀx ᴡᴀʀɴꜱ</td></tr>
<tr><td><code>.warntime 7d</code></td><td>ᴡᴀʀɴ ᴇxᴘɪʀʏ</td></tr>""",
        "⚙️ ᴍᴏᴅᴇꜱ: <code>ban</code> <code>mute</code> <code>kick</code> <code>tban</code> <code>tmute</code>"
    )


def _rich_tag() -> str:
    return _management_page(
        "ᴛᴀɢ ᴀʟʟ",
        "ɢʀᴏᴜᴘ ᴋᴇ ꜱᴀᴀʀᴇ ᴍᴇᴍʙᴇʀꜱ ᴋᴏ ᴛᴀɢ ᴋᴀʀᴏ. ᴘʀᴇꜰɪxᴇꜱ: <code>.</code> <code>/</code> <code>!</code>",
        """<tr><td>🏷️ <code>.all &lt;text&gt;</code></td><td>ꜱᴀʙᴋᴏ ᴛᴀɢ ᴋᴀʀᴏ</td></tr>
<tr><td>🏷️ <code>.call &lt;text&gt;</code></td><td>ꜱᴀᴍᴇ (ᴀʟɪᴀꜱ)</td></tr>
<tr><td>🏷️ <code>.tagall &lt;text&gt;</code></td><td>ꜱᴀᴍᴇ (ᴀʟɪᴀꜱ)</td></tr>
<tr><td>📩 <code>.all</code> <i>(reply)</i></td><td>ʀᴇᴘʟʏ ᴍᴇꜱꜱᴀɢᴇ ᴛᴀɢ</td></tr>
<tr><td>🛑 <code>.cancel</code></td><td>ᴛᴀɢɢɪɴɢ ʀᴏᴋᴏ</td></tr>
<tr><td>🛑 <code>.stop</code></td><td>ꜱᴀᴍᴇ (ᴀʟɪᴀꜱ)</td></tr>""",
        "⚠️ ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴛᴀɢ. 5 ᴍᴇᴍʙᴇʀꜱ ᴘᴇʀ 2 ꜱᴇᴄᴏɴᴅꜱ."
    )


def _rich_about() -> str:
    return f"""📖 <b>ᴀʙᴏᴜᴛ ᴇʟᴀʀᴀ</b>

ᴇʟᴀʀᴀ ɪꜱ ʏᴏᴜʀ ᴀɪ ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇʀ ꜰᴏʀ ᴇᴠᴇʀʏᴅᴀʏ ᴄᴏɴᴠᴇʀꜱᴀᴛɪᴏɴꜱ, ʀᴇᴀᴅʏ ᴛᴏ ʜᴀɴᴅʟᴇ ᴀɴʏ ᴄʜᴀᴛ. 🌙

<details open>
<summary>✨ ᴀʙᴏᴜᴛ ꜰᴇᴀᴛᴜʀᴇꜱ</summary>

<table>
<tr><th>ꜰᴇᴀᴛᴜʀᴇ</th><th>ᴅᴇᴛᴀɪʟꜱ</th></tr>
<tr><td>💬 ᴄʜᴀᴛ</td><td>ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀꜱᴀᴛɪᴏɴ</td></tr>
<tr><td>🧠 ᴍᴇᴍᴏʀʏ</td><td>ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ</td></tr>
<tr><td>💕 ꜱᴏᴄɪᴀʟ</td><td>ꜰᴜɴ ɢʀᴏᴜᴘ ᴄᴏᴍᴍᴀɴᴅꜱ</td></tr>
<tr><td>💰 ᴇᴄᴏɴᴏᴍʏ</td><td>ᴇᴅᴏʟʟᴇʀꜱ ɢᴀᴍᴇ</td></tr>
<tr><td>⚡ ꜱᴘᴇᴇᴅ</td><td>ꜰᴀꜱᴛ ʀᴇꜱᴘᴏɴꜱᴇꜱ</td></tr>
</table>
</details>

<blockquote><i>ᴜꜱᴇ ᴛʜᴇ ᴍᴇɴᴜ ʙᴇʟᴏᴡ ᴛᴏ ᴇxᴘʟᴏʀᴇ.</i></blockquote>
"""


# ══════════════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════════════════

def _welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ ➕",
            url=_safe_startgroup_url(),
            style=enums.ButtonStyle.PRIMARY,
        )],
        [
            InlineKeyboardButton("🍬 ꜱᴜᴘᴘᴏʀᴛ 🍬", url=_safe_url(SUPPORT_URL),
                                 style=enums.ButtonStyle.SUCCESS),
            InlineKeyboardButton("🍹 ᴜᴘᴅᴀᴛᴇꜱ 🍹", url=_safe_url(UPDATES_URL),
                                 style=enums.ButtonStyle.SUCCESS),
        ],
        [InlineKeyboardButton("🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ 🏩",
                              callback_data="elara:help",
                              style=enums.ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton("🫧 ᴏᴡɴᴇʀ 🫧", url=_owner_link(),
                                 style=enums.ButtonStyle.DANGER),
            InlineKeyboardButton("📖 ᴀʙᴏᴜᴛ 📖", callback_data="elara:about",
                                 style=enums.ButtonStyle.DANGER),
        ],
    ])


_HELP_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🤖 ᴀɪ", callback_data="elara:ai",
                             style=enums.ButtonStyle.PRIMARY),
        InlineKeyboardButton("💕 ꜱᴏᴄɪᴀʟ", callback_data="elara:social",
                             style=enums.ButtonStyle.SUCCESS),
    ],
    [
        InlineKeyboardButton("💰 ᴇᴄᴏɴᴏᴍʏ", callback_data="elara:economy",
                             style=enums.ButtonStyle.SUCCESS),
        InlineKeyboardButton("🛡️ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ", callback_data="elara:management",
                             style=enums.ButtonStyle.PRIMARY),
    ],
    [InlineKeyboardButton("⌯ ʜᴏᴍᴇ ⌯", callback_data="elara:home",
                          style=enums.ButtonStyle.PRIMARY)],
])


_MANAGEMENT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("👑 ᴀᴅᴍɪɴ", callback_data="elara:mg_admin",
                             style=enums.ButtonStyle.DANGER),
        InlineKeyboardButton("🔨 ʙᴀɴꜱ", callback_data="elara:mg_bans",
                             style=enums.ButtonStyle.PRIMARY),
        InlineKeyboardButton("🔎 ꜰɪʟᴛᴇʀꜱ", callback_data="elara:mg_filters",
                             style=enums.ButtonStyle.SUCCESS),
    ],
    [
        InlineKeyboardButton("👋 ɢʀᴇᴇᴛ", callback_data="elara:mg_greetings",
                             style=enums.ButtonStyle.SUCCESS),
        InlineKeyboardButton("🔒 ʟᴏᴄᴋꜱ", callback_data="elara:mg_locks",
                             style=enums.ButtonStyle.PRIMARY),
        InlineKeyboardButton("📌 ᴘɪɴꜱ", callback_data="elara:mg_pins",
                             style=enums.ButtonStyle.PRIMARY),
    ],
    [
        InlineKeyboardButton("🧹 ᴘᴜʀɢᴇꜱ", callback_data="elara:mg_purges",
                             style=enums.ButtonStyle.DANGER),
        InlineKeyboardButton("🚨 ʀᴇᴘᴏʀᴛꜱ", callback_data="elara:mg_reports",
                             style=enums.ButtonStyle.DANGER),
        InlineKeyboardButton("⚠️ ᴡᴀʀɴꜱ", callback_data="elara:mg_warnings",
                             style=enums.ButtonStyle.PRIMARY),
    ],
    [
        InlineKeyboardButton("🏷️ ᴛᴀɢ", callback_data="elara:mg_tag",
                             style=enums.ButtonStyle.SUCCESS),
        InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="elara:help",
                             style=enums.ButtonStyle.PRIMARY),
        InlineKeyboardButton("✖ ᴄʟᴏꜱᴇ", callback_data="elara:close",
                             style=enums.ButtonStyle.DANGER),
    ],
])


_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="elara:help",
                          style=enums.ButtonStyle.PRIMARY)],
    [InlineKeyboardButton("⌯ ᴄʟᴏꜱᴇ ⌯", callback_data="elara:close",
                          style=enums.ButtonStyle.DANGER)],
])


def _mg_subpage_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="elara:management",
                                 style=enums.ButtonStyle.PRIMARY),
            InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data="elara:home",
                                 style=enums.ButtonStyle.SUCCESS),
            InlineKeyboardButton("✖ ᴄʟᴏꜱᴇ", callback_data="elara:close",
                                 style=enums.ButtonStyle.DANGER),
        ],
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
                    **({"style": getattr(getattr(b, "style", None), "value", b.style)}
                       if getattr(b, "style", None) else {}),
                }
                for b in row
            ]
            for row in kb.inline_keyboard
        ]
    }


async def _send_rich(chat_id, html, kb, image=None):
    # ✅ Image <img> tag se HTML ke andar embed hoti hai
    payload = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
        "reply_markup": _kb_to_dict(kb),
    }

    result = await _bot_api("sendRichMessage", payload)
    if result.get("ok"):
        return

    print(f"[rich] failed: {result.get('description')}")

    try:
        import re
        clean_html = re.sub(r"<img[^>]*/?>", "", html)
        return await bot.send_message(
            chat_id, clean_html, reply_markup=kb, parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception as e:
        print(f"[rich-fallback] failed: {e}")
        return None


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

@bot.on_message(filters.command("start", prefixes=PREFIXES))
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
        )
    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        await _send_rich(
            message.chat.id,
            _rich_welcome(message.from_user),
            _welcome_kb(),
        )


@bot.on_message(filters.command("help", prefixes=PREFIXES))
async def help_handler(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass

    await _send_rich(message.chat.id, _rich_help(), _HELP_KB)


@bot.on_callback_query(filters.regex(
    r"^elara:(home|help|about|social|ai|economy|management|"
    r"mg_admin|mg_bans|mg_filters|mg_greetings|mg_locks|mg_pins|"
    r"mg_purges|mg_reports|mg_warnings|mg_tag|close)$"
))
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

    if d == "economy":
        await q.answer()
        await _edit_rich(q.message, _rich_economy(), _BACK_KB)
        return

    if d == "management":
        await q.answer()
        await _edit_rich(q.message, _rich_management(), _MANAGEMENT_KB)
        return

    management_pages = {
        "mg_admin":     _rich_admin,
        "mg_bans":      _rich_bans,
        "mg_filters":   _rich_filters,
        "mg_greetings": _rich_greetings,
        "mg_locks":     _rich_locks,
        "mg_pins":      _rich_pins,
        "mg_purges":    _rich_purges,
        "mg_reports":   _rich_reports,
        "mg_warnings":  _rich_warnings,
        "mg_tag":       _rich_tag,
    }

    if d in management_pages:
        await q.answer()
        await _edit_rich(q.message, management_pages[d](), _mg_subpage_kb())
        return

    if d == "about":
        await q.answer()
        await _edit_rich(q.message, _rich_about(), _BACK_KB)
        return
