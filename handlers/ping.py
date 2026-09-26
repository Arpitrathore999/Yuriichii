import os
import time
from datetime import timedelta

import psutil
import asyncio
try:
    import speedtest
except Exception:
    speedtest = None
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app

_STARTED_AT = time.time()

def _esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def _owner(message):
    return bool(message.from_user and config.OWNER_ID and int(message.from_user.id) == int(config.OWNER_ID))

def _support_markup():
    url = getattr(config, "SUPPORT_URL", "") or getattr(config, "UPDATES_URL", "")
    if not url:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🍬 sᴜᴘᴘᴏʀᴛ", url=url)]]
    )

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    started = time.perf_counter()
    try:
        wait = await message.reply_text("❍ ᴘɪɴɢɪɴɢ...")
    except Exception:
        wait = None

    latency = round((time.perf_counter() - started) * 1000)
    uptime = str(timedelta(seconds=int(time.time() - _STARTED_AT)))
    cpu = psutil.cpu_percent(interval=0.15)
    process = psutil.Process(os.getpid())
    ram = process.memory_info().rss / 1024 / 1024
    disk = psutil.disk_usage("/")
    disk_str = f"{disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent}%)"

    try:
        me = await client.get_me()
        bot_name = _esc(me.first_name)
    except Exception:
        bot_name = "ᴇʟᴀʀᴀ"

    try:
        await wait.delete()
    except Exception:
        pass

    caption = (
        f"🏓 <b>ᴘᴏɴɢ : {latency}ms</b>\n\n"
        f"╭──────────────╮\n"
        f"│ <b>ᴜᴘᴛɪᴍᴇ</b>  <code>{_esc(uptime)}</code>\n"
        f"│ <b>ʀᴀᴍ</b>     <code>{ram:.2f} MB</code>\n"
        f"│ <b>ᴄᴘᴜ</b>     <code>{cpu:.1f}%</code>\n"
        f"│ <b>ᴅɪsᴋ</b>    <code>{_esc(disk_str)}</code>\n"
        f"╰──────────────╯\n\n"
        f"❍ ʙʏ » <b>{bot_name}</b>"
    )

    image = (getattr(config, "PING_IMAGE_URL", "") or "").strip()
    markup = _support_markup()
    try:
        if image:
            await message.reply_photo(image, caption=caption, parse_mode=ParseMode.HTML,
                                      reply_markup=markup)
        else:
            await message.reply_text(caption, parse_mode=ParseMode.HTML,
                                     reply_markup=markup)
    except Exception:
        await message.reply_text(caption, parse_mode=ParseMode.HTML,
                                 reply_markup=markup)


def _speedtest_sync():
    if speedtest is None:
        return None
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        st.download()
        st.upload()
        return st.results.dict()
    except Exception:
        return None

@app.on_message(filters.command(["speedtest", "spt"]))
async def speedtest_cmd(_, message: Message):
    if not _owner(message):
        return
    status = await message.reply_text("❍ sᴛᴀʀᴛɪɴɢ sᴘᴇᴇᴅ ᴛᴇsᴛ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...")
    result = await asyncio.get_running_loop().run_in_executor(None, _speedtest_sync)
    if not result:
        return await status.edit_text("❍ sᴘᴇᴇᴅᴛᴇsᴛ ғᴀɪʟᴇᴅ. ᴛʀʏ ᴀɢᴀɪɴ.")
    download = result["download"] / 1_000_000
    upload = result["upload"] / 1_000_000
    ping = result["ping"]
    server = result["server"]["name"]
    isp = result["client"]["isp"]
    await status.edit_text(
        f"⚡ <b>sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n"
        f"ɪsᴘ: <code>{_esc(isp)}</code>\n"
        f"sᴇʀᴠᴇʀ: <code>{_esc(server)}</code>\n"
        f"ᴘɪɴɢ: <code>{ping:.2f} ms</code>\n"
        f"ᴅᴏᴡɴʟᴏᴀᴅ: <code>{download:.2f} Mbps</code>\n"
        f"ᴜᴘʟᴏᴀᴅ: <code>{upload:.2f} Mbps</code>"
    )
