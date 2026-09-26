# --------------------------------------------------------------------------------
#  Yuriichii © 2026
#  Ping / Speedtest — Music Bot style
# --------------------------------------------------------------------------------

import asyncio
import os
import time
from datetime import timedelta

import psutil
import speedtest
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app
from utils.rich_ui import rich_esc, rich_heading, rich_img, rich_kv_table, rich_send, rich_edit

bot_start_time = time.time()


def supp_markup():
    url = getattr(config, "SUPPORT_URL", "")
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=url)]])


# ── /ping ──────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message) -> None:
    chat_id = message.chat.id
    start = time.perf_counter()
    pm = await rich_send(
        app, chat_id,
        rich_heading(f"❍ {rich_esc(getattr(client.me, 'first_name', config.BOT_NAME))} ɪs ᴘɪɴɢɪɴɢ...", level=3),
    )

    latency = round((time.perf_counter() - start) * 1000)
    uptime = str(timedelta(seconds=int(time.time() - bot_start_time)))
    cpu = psutil.cpu_percent(interval=1)

    process = psutil.Process(os.getpid())
    ram = process.memory_info().rss / 1024 / 1024

    disk = psutil.disk_usage("/")
    disk_str = (
        f"{disk.used // (1024**3)}GB / "
        f"{disk.total // (1024**3)}GB "
        f"({disk.percent}%)"
    )

    try:
        await pm.delete()
    except Exception:
        pass

    caption = (
        rich_heading(f"🏓 ᴘᴏɴɢ : {latency}ms", level=3)
        + rich_img(getattr(config, "PING_IMAGE_URL", ""))
        + rich_kv_table([
            ("ᴜᴘᴛɪᴍᴇ", f"<code>{rich_esc(uptime)}</code>"),
            ("ʀᴀᴍ", f"<code>{ram:.2f} MB</code>"),
            ("ᴄᴘᴜ", f"<code>{cpu}%</code>"),
            ("ᴅɪsᴋ", f"<code>{rich_esc(disk_str)}</code>"),
        ])
        + f'<p>❍ ʙʏ » <a href="{rich_esc(getattr(config, "SUPPORT_URL", ""))}">{rich_esc(config.BOT_NAME)}</a></p>'
    )

    image = (getattr(config, "PING_IMAGE_URL", "") or "").strip()
    if image:
        try:
            await app.send_photo(chat_id, image, caption=caption, reply_markup=supp_markup())
            return
        except Exception:
            pass
    await rich_send(app, chat_id, caption, reply_markup=supp_markup())


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


@app.on_message(filters.command(["speedtest", "spt"]) & filters.user(config.OWNER_ID))
async def speedtest_cmd(client, message: Message) -> None:
    chat_id = message.chat.id
    m = await rich_send(app, chat_id, rich_heading("❍ sᴛᴀʀᴛɪɴɢ sᴘᴇᴇᴅ ᴛᴇsᴛ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...", level=3))

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_speedtest)

    if result is None:
        await rich_edit(m, rich_heading("❍ sᴘᴇᴇᴅᴛᴇsᴛ ғᴀɪʟᴇᴅ, ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ", level=3))
        return

    download = result["download"] / 1_000_000
    upload = result["upload"] / 1_000_000
    ping = result["ping"]
    isp = result["client"]["isp"]
    country = result["client"]["country"]
    server = result["server"]["name"]
    sponsor = result["server"]["sponsor"]
    s_cc = result["server"]["cc"]
    s_lat = result["server"]["latency"]
    share = result["share"]

    caption = (
        rich_heading("⚡ sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs", level=3)
        + rich_img(share)
        + rich_kv_table([
            ("ɪsᴘ", f"<code>{rich_esc(isp)}</code>"),
            ("ᴄᴏᴜɴᴛʀʏ", f"<code>{rich_esc(country)}</code>"),
        ], headers=["ᴄʟɪᴇɴᴛ ɪɴғᴏ", ""])
        + rich_kv_table([
            ("ɴᴀᴍᴇ", f"<code>{rich_esc(server)}</code>"),
            ("sᴘᴏɴsᴏʀ", f"<code>{rich_esc(sponsor)}</code>"),
            ("ᴄᴏᴜɴᴛʀʏ", f"<code>{rich_esc(s_cc)}</code>"),
            ("ʟᴀᴛᴇɴᴄʏ", f"<code>{s_lat} ms</code>"),
        ], headers=["sᴇʀᴠᴇʀ ɪɴғᴏ", ""])
        + rich_kv_table([
            ("ᴘɪɴɢ", f"<code>{ping:.2f} ms</code>"),
            ("ᴅᴏᴡɴʟᴏᴀᴅ", f"<code>{download:.2f} Mbps</code>"),
            ("ᴜᴘʟᴏᴀᴅ", f"<code>{upload:.2f} Mbps</code>"),
        ], headers=["sᴘᴇᴇᴅ", ""])
        + f'<p>❍ ʙʏ » <a href="{rich_esc(getattr(config, "SUPPORT_URL", ""))}">{rich_esc(config.BOT_NAME)}</a></p>'
    )

    try:
        await m.delete()
    except Exception:
        pass

    await rich_send(app, chat_id, caption, reply_markup=supp_markup())
