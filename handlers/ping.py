# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/ping.py — Native Rich Message ping (kurigram)
# --------------------------------------------------------------------------------

import os
import time
import asyncio
from urllib.request import Request, urlopen
from datetime import timedelta

import psutil
import speedtest
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app

from utils.rich_ui import (
    rich_esc,
    rich_heading,
    rich_img,
    rich_kv_table,
    rich_send,
    rich_edit,
    rich_note,
)

BOT_START_TIME = time.time()


def supp_markup():
    url = (getattr(config, "SUPPORT_GROUP", None)
           or getattr(config, "SUPPORT_URL", ""))
    if not url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(text="🎀 sᴜᴘᴘᴏʀᴛ 🎀", url=url),
    ]])


# ── /ping ──────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("ping") & (filters.private | filters.group))
async def ping_cmd(client, message: Message):
    """Reliable /ping for private chats and groups."""
    start = time.perf_counter()

    try:
        await client.get_me()
    except Exception:
        pass

    latency = max(1, round((time.perf_counter() - start) * 1000))
    uptime = str(timedelta(seconds=int(time.time() - BOT_START_TIME)))

    try:
        cpu = psutil.cpu_percent(interval=0.5)
    except Exception:
        cpu = 0

    try:
        ram = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except Exception:
        ram = 0

    try:
        disk = psutil.disk_usage("/")
        disk_str = f"{disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent}%)"
    except Exception:
        disk_str = "N/A"

    bot_name = getattr(config, "BOT_NAME", "Elara")
    img_url = (getattr(config, "PING_IMAGE_URL", "") or "").strip()

    caption = (
        f"🏓 <b>ᴘᴏɴɢ : {latency}ms</b>\n\n"
        f"❍ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{uptime}</code>\n"
        f"❍ <b>ʀᴀᴍ:</b> <code>{ram:.2f} MB</code>\n"
        f"❍ <b>ᴄᴘᴜ:</b> <code>{cpu}%</code>\n"
        f"❍ <b>ᴅɪsᴋ:</b> <code>{disk_str}</code>\n"
        f"❍ <b>ᴘʏᴛɢᴄ:</b> <code>N/A</code>\n\n"
        f"❍ ʙʏ » <b>{rich_esc(bot_name)}</b>"
    )

    markup = supp_markup()

    # Download the image ourselves so Telegram does not have to fetch the URL.
    if img_url:
        try:
            req = Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            def _download():
                with urlopen(req, timeout=15) as r:
                    return r.read()
            image_bytes = await asyncio.to_thread(_download)
            await client.send_photo(
                chat_id=message.chat.id,
                photo=image_bytes,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            return
        except Exception as e:
            print(f"[/ping] image send failed: {e}")

    # Always respond even if the image URL is unavailable.
    await client.send_message(
        chat_id=message.chat.id,
        text=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


# ── /speedtest ─────────────────────────────────────────────────────────────────

def _run_speedtest():
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        st.download()
        st.upload()
        st.results.share()
        return st.results.dict()
    except Exception:
        return None


@app.on_message(
    filters.command(["speedtest", "spt"]) & filters.user(config.OWNER_ID)
)
async def speedtest_cmd(client, message: Message):
    chat_id = message.chat.id
    m = await rich_send(
        client, chat_id,
        rich_heading("❍ sᴛᴀʀᴛɪɴɢ sᴘᴇᴇᴅ ᴛᴇsᴛ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...", level=3)
    )

    import asyncio
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_speedtest)

    if result is None:
        return await rich_edit(m, rich_heading("❍ sᴘᴇᴇᴅᴛᴇsᴛ ғᴀɪʟᴇᴅ", level=3))

    download = result["download"] / 1_000_000
    upload   = result["upload"]   / 1_000_000
    ping     = result["ping"]
    isp      = result["client"]["isp"]
    country  = result["client"]["country"]
    server   = result["server"]["name"]
    sponsor  = result["server"]["sponsor"]
    s_cc     = result["server"]["cc"]
    s_lat    = result["server"]["latency"]
    share    = result["share"]

    support_url = (getattr(config, "SUPPORT_GROUP", None)
                   or getattr(config, "SUPPORT_URL", ""))
    bot_name    = getattr(config, "BOT_NAME", "Elara")

    caption = (
        rich_heading("⚡ sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs", level=3)
        + rich_img(share)
        + rich_kv_table([
            ("ɪsᴘ",     f"<code>{rich_esc(isp)}</code>"),
            ("ᴄᴏᴜɴᴛʀʏ", f"<code>{rich_esc(country)}</code>"),
        ], headers=["ᴄʟɪᴇɴᴛ ɪɴғᴏ", ""])
        + rich_kv_table([
            ("ɴᴀᴍᴇ",    f"<code>{rich_esc(server)}</code>"),
            ("sᴘᴏɴsᴏʀ", f"<code>{rich_esc(sponsor)}</code>"),
            ("ᴄᴏᴜɴᴛʀʏ", f"<code>{rich_esc(s_cc)}</code>"),
            ("ʟᴀᴛᴇɴᴄʏ", f"<code>{s_lat} ms</code>"),
        ], headers=["sᴇʀᴠᴇʀ ɪɴғᴏ", ""])
        + rich_kv_table([
            ("ᴘɪɴɢ",     f"<code>{ping:.2f} ms</code>"),
            ("ᴅᴏᴡɴʟᴏᴀᴅ", f"<code>{download:.2f} Mbps</code>"),
            ("ᴜᴘʟᴏᴀᴅ",   f"<code>{upload:.2f} Mbps</code>"),
        ], headers=["sᴘᴇᴇᴅ", ""])
        + f'❍ ʙʏ » <a href="{support_url}">{rich_esc(bot_name)}</a>'
    )

    try:
        await m.delete()
    except Exception:
        pass

    await rich_send(client, chat_id, caption, reply_markup=supp_markup())