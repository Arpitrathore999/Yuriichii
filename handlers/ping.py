# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  handlers/ping.py — Music Bot style, Yuriichii compatible
# --------------------------------------------------------------------------------

import asyncio
import json
import os
import time
from datetime import timedelta
from urllib.request import Request, urlopen

import psutil
import speedtest
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Message

import config
from core.bot import app

bot = app
BOT_TOKEN = getattr(config, "BOT_TOKEN", "")
SUPPORT_URL = getattr(config, "SUPPORT_URL", "") or "https://t.me/telegram"
PING_IMAGE_URL = getattr(config, "PING_IMAGE_URL", "") or ""
BOT_NAME = getattr(config, "BOT_NAME", "Elara")
BOT_START_TIME = time.time()


def supp_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(text="🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=SUPPORT_URL),
    ]])


def _esc(value) -> str:
    return (str(value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


async def _bot_api(method: str, payload: dict) -> dict:
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN missing"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")

    def _do():
        try:
            req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "description": str(e)}

    return await asyncio.to_thread(_do)


async def _send_rich(chat_id: int, html: str, image: str = "", reply_markup=None):
    """Use the same Rich Message API approach as Yuriichii's start handler."""
    payload = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
    }
    if image:
        payload["rich_message"]["photo_url"] = image

    if reply_markup:
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {
                    "text": b.text,
                    **({"url": b.url} if b.url else {}),
                    **({"callback_data": b.callback_data} if getattr(b, "callback_data", None) else {}),
                }
                for b in row
            ] for row in reply_markup.inline_keyboard]
        }

    result = await _bot_api("sendRichMessage", payload)
    if result.get("ok"):
        return result

    # Normal Telegram fallback if Rich Message API is unavailable.
    if image:
        try:
            return await bot.send_photo(
                chat_id,
                photo=image,
                caption=html,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    return await bot.send_message(
        chat_id,
        html,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def _edit_message(message: Message, html: str):
    try:
        await message.edit_text(
            html,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception:
        try:
            await message.delete()
        except Exception:
            pass
        return await bot.send_message(
            message.chat.id,
            html,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


# ── /ping ──────────────────────────────────────────────────────────────────────

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message) -> None:
    chat_id = message.chat.id
    start = time.perf_counter()

    try:
        me = await client.get_me()
        first_name = _esc(me.first_name or BOT_NAME)
    except Exception:
        first_name = _esc(BOT_NAME)

    # Same "is pinging..." flow as the Music Bot.
    pm = await _send_rich(
        chat_id,
        f"❍ <b>{first_name}</b> ɪs ᴘɪɴɢɪɴɢ...",
    )

    latency = round((time.perf_counter() - start) * 1000)
    uptime = str(timedelta(seconds=int(time.time() - BOT_START_TIME)))
    cpu = psutil.cpu_percent(interval=1)

    process = psutil.Process(os.getpid())
    ram = process.memory_info().rss / 1024 / 1024

    disk = psutil.disk_usage("/")
    disk_str = (
        f"{disk.used // (1024**3)}GB / "
        f"{disk.total // (1024**3)}GB "
        f"({disk.percent}%)"
    )

    # Yuriichii has no separate music assistant/pytgcalls client.
    pytg = "N/A"

    try:
        await pm.delete()
    except Exception:
        pass

    caption = (
        f"🏓 <b>ᴘᴏɴɢ : {latency}ms</b>\n\n"
        + "<table>"
        + "<tr><th>sʏsᴛᴇᴍ</th><th>ᴠᴀʟᴜᴇ</th></tr>"
        + f"<tr><td>ᴜᴘᴛɪᴍᴇ</td><td><code>{_esc(uptime)}</code></td></tr>"
        + f"<tr><td>ʀᴀᴍ</td><td><code>{ram:.2f} MB</code></td></tr>"
        + f"<tr><td>ᴄᴘᴜ</td><td><code>{cpu}%</code></td></tr>"
        + f"<tr><td>ᴅɪsᴋ</td><td><code>{_esc(disk_str)}</code></td></tr>"
        + f"<tr><td>ᴘʏᴛɢᴄ</td><td><code>{pytg}</code></td></tr>"
        + "</table>\n\n"
        + f'❍ ʙʏ » <a href="{_esc(SUPPORT_URL)}">{_esc(BOT_NAME)}</a>'
    )

    await _send_rich(
        chat_id,
        caption,
        image=PING_IMAGE_URL,
        reply_markup=supp_markup(),
    )


# ── /speedtest ─────────────────────────────────────────────────────────────────

def _run_speedtest():
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        st.download()
        st.upload()
        try:
            st.results.share()
        except Exception:
            pass
        return st.results.dict()
    except Exception:
        return None


@bot.on_message(filters.command(["speedtest", "spt"]) & filters.user(getattr(config, "OWNER_ID", 0)))
async def speedtest_cmd(client, message: Message) -> None:
    chat_id = message.chat.id
    m = await _send_rich(
        chat_id,
        "❍ sᴛᴀʀᴛɪɴɢ sᴘᴇᴇᴅ ᴛᴇsᴛ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...",
    )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_speedtest)

    if result is None:
        return await _edit_message(
            m,
            "❍ sᴘᴇᴇᴅᴛᴇsᴛ ғᴀɪʟᴇᴅ, ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ",
        )

    download = result["download"] / 1_000_000
    upload = result["upload"] / 1_000_000
    ping = result["ping"]
    client_info = result.get("client", {})
    server_info = result.get("server", {})

    isp = client_info.get("isp", "N/A")
    country = client_info.get("country", "N/A")
    server = server_info.get("name", "N/A")
    sponsor = server_info.get("sponsor", "N/A")
    s_cc = server_info.get("cc", "N/A")
    s_lat = server_info.get("latency", "N/A")
    share = result.get("share", "")

    caption = (
        "⚡ <b>sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n"
        + (f'<a href="{_esc(share)}">sᴘᴇᴇᴅᴛᴇsᴛ ɪᴍᴀɢᴇ</a>\n\n' if share else "")
        + "<table>"
        + "<tr><th>ᴄʟɪᴇɴᴛ ɪɴғᴏ</th><th></th></tr>"
        + f"<tr><td>ɪsᴘ</td><td><code>{_esc(isp)}</code></td></tr>"
        + f"<tr><td>ᴄᴏᴜɴᴛʀʏ</td><td><code>{_esc(country)}</code></td></tr>"
        + "</table>\n\n"
        + "<table>"
        + "<tr><th>sᴇʀᴠᴇʀ ɪɴғᴏ</th><th></th></tr>"
        + f"<tr><td>ɴᴀᴍᴇ</td><td><code>{_esc(server)}</code></td></tr>"
        + f"<tr><td>sᴘᴏɴsᴏʀ</td><td><code>{_esc(sponsor)}</code></td></tr>"
        + f"<tr><td>ᴄᴏᴜɴᴛʀʏ</td><td><code>{_esc(s_cc)}</code></td></tr>"
        + f"<tr><td>ʟᴀᴛᴇɴᴄʏ</td><td><code>{_esc(s_lat)} ms</code></td></tr>"
        + "</table>\n\n"
        + "<table>"
        + "<tr><th>sᴘᴇᴇᴅ</th><th></th></tr>"
        + f"<tr><td>ᴘɪɴɢ</td><td><code>{ping:.2f} ms</code></td></tr>"
        + f"<tr><td>ᴅᴏᴡɴʟᴏᴀᴅ</td><td><code>{download:.2f} Mbps</code></td></tr>"
        + f"<tr><td>ᴜᴘʟᴏᴀᴅ</td><td><code>{upload:.2f} Mbps</code></td></tr>"
        + "</table>\n\n"
        + f'❍ ʙʏ » <a href="{_esc(SUPPORT_URL)}">{_esc(BOT_NAME)}</a>'
    )

    try:
        await m.delete()
    except Exception:
        pass

    await _send_rich(
        chat_id,
        caption,
        image=share,
        reply_markup=supp_markup(),
    )
