# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/ping.py — Premium PING with dynamic image + rich blockquote
# --------------------------------------------------------------------------------

import asyncio
import os
import time
from datetime import timedelta
from io import BytesIO

import aiohttp
import psutil
import speedtest
from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app

BOT_START_TIME = time.time()

# ⚙️ Config (apne config.py me daal dena)
BOT_NAME       = getattr(config, "BOT_NAME", "ELARA MUSIC")
SUPPORT_URL    = getattr(config, "SUPPORT_URL", "https://t.me/YourSupport")
PING_IMG_URL   = getattr(config, "PING_IMG_URL", "")   # background image URL


# ── Helpers ────────────────────────────────────────────────────────────────────

def _esc(v) -> str:
    return (
        str(v or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _support_markup():
    if not SUPPORT_URL:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🎀 sᴜᴘᴘᴏʀᴛ 🎀", url=SUPPORT_URL)]
    ])


# ── Image Generator (PONG card) ────────────────────────────────────────────────

def _generate_ping_image(latency, api_latency, uptime, bg_url=None):
    """Screenshot jaisi PONG image banata hai."""
    W, H = 900, 500

    # Base background
    if bg_url:
        try:
            import urllib.request
            with urllib.request.urlopen(bg_url, timeout=10) as r:
                bg = Image.open(BytesIO(r.read())).convert("RGBA")
                bg = bg.resize((W, H))
        except Exception:
            bg = Image.new("RGBA", (W, H), (18, 10, 30, 255))
    else:
        bg = Image.new("RGBA", (W, H), (18, 10, 30, 255))

    draw = ImageDraw.Draw(bg)

    # Dark overlay
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 90))
    bg = Image.alpha_composite(bg, overlay)
    draw = ImageDraw.Draw(bg)

    # Neon border
    draw.rounded_rectangle(
        [(10, 10), (W - 10, H - 10)],
        radius=35, outline=(255, 105, 180, 255), width=5
    )

    # Fonts
    try:
        f_big   = ImageFont.truetype("arialbd.ttf", 90)
        f_med   = ImageFont.truetype("arialbd.ttf", 30)
        f_small = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        f_big = f_med = f_small = ImageFont.load_default()

    # PONG title
    draw.text((60, 70), "PONG", font=f_big, fill=(255, 105, 180, 255))

    # Stats lines
    lines = [
        ("⚡ Bot Latency", f"{latency} ms"),
        ("🛰 API Latency", f"{api_latency} ms"),
        ("⏱ Uptime",      uptime),
    ]
    y = 230
    for label, value in lines:
        draw.rounded_rectangle(
            [(60, y), (500, y + 45)],
            radius=12, fill=(40, 20, 60, 220)
        )
        draw.text((80, y + 8),  label, font=f_small, fill=(230, 230, 230))
        draw.text((320, y + 8), value, font=f_small, fill=(255, 105, 180))
        y += 60

    # Footer
    draw.text((60, 440), "Always Online 💗", font=f_small, fill=(255, 182, 220))
    draw.text((640, 445), BOT_NAME, font=f_small, fill=(180, 180, 255))

    out = BytesIO()
    out.name = "ping.jpg"
    bg.convert("RGB").save(out, "JPEG", quality=90)
    out.seek(0)
    return out


# ── /ping ──────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    chat_id = message.chat.id
    started = time.perf_counter()

    # Loading
    try:
        loading = await message.reply("🏓 <b>ᴘɪɴɢɪɴɢ...</b>", parse_mode=ParseMode.HTML)
    except Exception:
        loading = None

    # Bot latency
    bot_latency = round((time.perf_counter() - started) * 1000)

    # API latency (get_me round trip)
    api_start = time.perf_counter()
    try:
        await client.get_me()
    except Exception:
        pass
    api_latency = round((time.perf_counter() - api_start) * 1000)

    # Uptime
    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_str = str(timedelta(seconds=uptime_sec))
    # Short format: 2d 14h 36m
    d = uptime_sec // 86400
    h = (uptime_sec % 86400) // 3600
    m = (uptime_sec % 3600) // 60
    uptime_short = (f"{d}d " if d else "") + (f"{h}h " if h else "") + f"{m}m"

    # Stats
    try:
        cpu = psutil.cpu_percent(interval=0.2)
    except Exception:
        cpu = 0

    try:
        proc = psutil.Process(os.getpid())
        ram = proc.memory_info().rss / 1024 / 1024
    except Exception:
        ram = 0

    try:
        disk = psutil.disk_usage("/")
        disk_str = f"{disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent}%)"
    except Exception:
        disk_str = "N/A"

    pytgc = "N/A"  # Yuriichii

    # Delete loading
    if loading:
        try:
            await loading.delete()
        except Exception:
            pass

    # Generate image in executor
    loop = asyncio.get_running_loop()
    img = await loop.run_in_executor(
        None, _generate_ping_image,
        bot_latency, api_latency, uptime_short, PING_IMG_URL
    )

    # Caption with rich blockquote (Telegram expandable quote)
    caption = (
        f"🏓 <b>ᴘᴏɴɢ : {bot_latency}ms</b>\n\n"
        f"<blockquote expandable>"
        f"<b>ᴜᴘᴛɪᴍᴇ</b> : <code>{_esc(uptime_str)}</code>\n"
        f"<b>ʀᴀᴍ</b> : <code>{ram:.2f} MB</code>\n"
        f"<b>ᴄᴘᴜ</b> : <code>{cpu}%</code>\n"
        f"<b>ᴅɪsᴋ</b> : <code>{_esc(disk_str)}</code>\n"
        f"<b>ᴘʏᴛɢᴄ</b> : <code>{pytgc}</code>"
        f"</blockquote>\n\n"
        f"❍ ʙʏ » <a href=\"{SUPPORT_URL}\">{_esc(BOT_NAME)}</a>"
    )

    try:
        await client.send_photo(
            chat_id,
            photo=img,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=_support_markup(),
        )
    except Exception:
        # Fallback text-only
        await client.send_message(
            chat_id, caption,
            parse_mode=ParseMode.HTML,
            reply_markup=_support_markup(),
            disable_web_page_preview=True,
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


@app.on_message(filters.command(["speedtest", "spt"]) & filters.user(config.OWNER_ID))
async def speedtest_cmd(client, message: Message):
    status = await message.reply("❍ sᴛᴀʀᴛɪɴɢ sᴘᴇᴇᴅᴛᴇsᴛ...")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_speedtest)

    if not result:
        return await status.edit("❍ sᴘᴇᴇᴅᴛᴇsᴛ ғᴀɪʟᴇᴅ")

    download = result.get("download", 0) / 1_000_000
    upload   = result.get("upload", 0) / 1_000_000
    ping     = result.get("ping", 0)
    cinfo    = result.get("client", {}) or {}
    sinfo    = result.get("server", {}) or {}
    share    = result.get("share")

    text = (
        "⚡ <b>sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n"
        f"<blockquote expandable>"
        f"<b>ɪsᴘ</b> : <code>{_esc(cinfo.get('isp','N/A'))}</code>\n"
        f"<b>ᴄᴏᴜɴᴛʀʏ</b> : <code>{_esc(cinfo.get('country','N/A'))}</code>\n\n"
        f"<b>sᴇʀᴠᴇʀ</b> : <code>{_esc(sinfo.get('name','N/A'))}</code>\n"
        f"<b>sᴘᴏɴsᴏʀ</b> : <code>{_esc(sinfo.get('sponsor','N/A'))}</code>\n"
        f"<b>ʟᴀᴛᴇɴᴄʏ</b> : <code>{sinfo.get('latency','N/A')} ms</code>\n\n"
        f"<b>ᴘɪɴɢ</b> : <code>{ping:.2f} ms</code>\n"
        f"<b>ᴅᴏᴡɴʟᴏᴀᴅ</b> : <code>{download:.2f} Mbps</code>\n"
        f"<b>ᴜᴘʟᴏᴀᴅ</b> : <code>{upload:.2f} Mbps</code>"
        f"</blockquote>"
    )

    try:
        await status.delete()
    except Exception:
        pass

    if share:
        try:
            return await client.send_photo(
                message.chat.id, share, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=_support_markup()
            )
        except Exception:
            pass

    await client.send_message(
        message.chat.id, text,
        parse_mode=ParseMode.HTML,
        reply_markup=_support_markup(),
        disable_web_page_preview=True,
    )