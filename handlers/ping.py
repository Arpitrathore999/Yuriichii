# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/ping.py — Music Bot style /ping (image direct from config)
# --------------------------------------------------------------------------------

import asyncio
import os
import time
from datetime import timedelta

import psutil
import speedtest
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app

BOT_START_TIME = time.time()


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
    url = (getattr(config, "SUPPORT_URL", "") or "").strip()
    if not url:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🎀 sᴜᴘᴘᴏʀᴛ 🎀", url=url)]
    ])


# ── /ping ──────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    chat_id = message.chat.id
    started = time.perf_counter()

    # ── measure bot latency
    bot_latency = round((time.perf_counter() - started) * 1000)

    # ── measure API latency
    api_start = time.perf_counter()
    try:
        await client.get_me()
    except Exception:
        pass
    api_latency = round((time.perf_counter() - api_start) * 1000)

    # ── uptime
    up = int(time.time() - BOT_START_TIME)
    uptime_full = str(timedelta(seconds=up))

    # ── stats
    try:
        cpu = psutil.cpu_percent(interval=0.2)
    except Exception:
        cpu = 0

    try:
        ram = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except Exception:
        ram = 0

    try:
        disk = psutil.disk_usage("/")
        disk_str = (
            f"{disk.used // (1024 ** 3)}GB / "
            f"{disk.total // (1024 ** 3)}GB "
            f"({disk.percent}%)"
        )
    except Exception:
        disk_str = "N/A"

    pytgc = "N/A"   # Yuriichii me alag assistant nahi hota

    bot_name    = getattr(config, "BOT_NAME", "Elara Music")
    support_url = getattr(config, "SUPPORT_URL", "")
    img_url     = (getattr(config, "PING_IMG_URL", "") or "").strip()

    # ── Caption (screenshot jaisa)
    caption = (
        f"🏓 <b>ᴘᴏɴɢ : {bot_latency}ms</b>\n\n"
        f"<blockquote expandable>"
        f"<b>ᴜᴘᴛɪᴍᴇ</b> : <code>{_esc(uptime_full)}</code>\n"
        f"<b>ʀᴀᴍ</b> : <code>{ram:.2f} MB</code>\n"
        f"<b>ᴄᴘᴜ</b> : <code>{cpu}%</code>\n"
        f"<b>ᴅɪsᴋ</b> : <code>{_esc(disk_str)}</code>\n"
        f"<b>ᴘʏᴛɢᴄ</b> : <code>{pytgc}</code>"
        f"</blockquote>\n\n"
    )

    if support_url:
        caption += f'❍ ʙʏ » <a href="{support_url}">{_esc(bot_name)}</a>'
    else:
        caption += f"❍ ʙʏ » {_esc(bot_name)}"

    # ── Send (image direct from config URL)
    if img_url:
        try:
            return await client.send_photo(
                chat_id,
                photo=img_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=_support_markup(),
            )
        except Exception:
            pass

    # fallback: text only
    await client.send_message(
        chat_id,
        caption,
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

    dl = result.get("download", 0) / 1_000_000
    ul = result.get("upload", 0) / 1_000_000
    pg = result.get("ping", 0)
    ci = result.get("client", {}) or {}
    si = result.get("server", {}) or {}
    share = result.get("share")

    text = (
        "⚡ <b>sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n"
        f"<blockquote expandable>"
        f"<b>ɪsᴘ</b> : <code>{_esc(ci.get('isp','N/A'))}</code>\n"
        f"<b>ᴄᴏᴜɴᴛʀʏ</b> : <code>{_esc(ci.get('country','N/A'))}</code>\n\n"
        f"<b>sᴇʀᴠᴇʀ</b> : <code>{_esc(si.get('name','N/A'))}</code>\n"
        f"<b>sᴘᴏɴsᴏʀ</b> : <code>{_esc(si.get('sponsor','N/A'))}</code>\n"
        f"<b>ʟᴀᴛᴇɴᴄʏ</b> : <code>{si.get('latency','N/A')} ms</code>\n\n"
        f"<b>ᴘɪɴɢ</b> : <code>{pg:.2f} ms</code>\n"
        f"<b>ᴅᴏᴡɴʟᴏᴀᴅ</b> : <code>{dl:.2f} Mbps</code>\n"
        f"<b>ᴜᴘʟᴏᴀᴅ</b> : <code>{ul:.2f} Mbps</code>"
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