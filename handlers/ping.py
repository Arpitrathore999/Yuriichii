# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/ping.py — Music Bot style, Yuriichii compatible
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


def _esc(value) -> str:
    value = str(value or "")
    return (value.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;"))


def _support_markup():
    url = (getattr(config, "SUPPORT_URL", "") or "").strip()
    if not url:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=url)]
    ])


async def _send_ping(client, message: Message):
    """Music-Bot style ping, with a plain Telegram fallback so it cannot
    disappear if the optional Rich UI layer fails."""
    chat_id = message.chat.id
    started = time.perf_counter()

    # First message: same visual flow as the Music Bot.
    try:
        me = await client.get_me()
        bot_name = me.first_name or getattr(config, "BOT_NAME", "Elara")
    except Exception:
        bot_name = getattr(config, "BOT_NAME", "Elara")

    try:
        loading = await message.reply(
            f"❍ <b>{_esc(bot_name)}</b> ɪs ᴘɪɴɢɪɴɢ...",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        loading = None

    latency = round((time.perf_counter() - started) * 1000)
    uptime = str(timedelta(seconds=max(0, int(time.time() - BOT_START_TIME))))

    try:
        cpu = psutil.cpu_percent(interval=0.15)
    except Exception:
        cpu = 0

    try:
        process = psutil.Process(os.getpid())
        ram = process.memory_info().rss / 1024 / 1024
    except Exception:
        ram = 0

    try:
        disk = psutil.disk_usage("/")
        disk_str = (
            f"{disk.used / (1024 ** 3):.1f}GB / "
            f"{disk.total / (1024 ** 3):.1f}GB ({disk.percent}%)"
        )
    except Exception:
        disk_str = "N/A"

    # Yuriichii has no separate PyTgCalls assistant.
    pytgcalls = "N/A"

    if loading:
        try:
            await loading.delete()
        except Exception:
            pass

    bot_name = _esc(getattr(config, "BOT_NAME", bot_name))
    support_url = _esc(getattr(config, "SUPPORT_URL", ""))
    image_url = (getattr(config, "PING_IMAGE_URL", "") or "").strip()

    caption = (
        f"🏓 <b>ᴘᴏɴɢ : {latency}ms</b>\n\n"
        f"<b>ᴜᴘᴛɪᴍᴇ</b> : <code>{_esc(uptime)}</code>\n"
        f"<b>ʀᴀᴍ</b> : <code>{ram:.2f} MB</code>\n"
        f"<b>ᴄᴘᴜ</b> : <code>{cpu}%</code>\n"
        f"<b>ᴅɪsᴋ</b> : <code>{_esc(disk_str)}</code>\n"
        f"<b>ᴘʏᴛɢᴄ</b> : <code>{pytgcalls}</code>\n\n"
    )
    if support_url:
        caption += f'❍ ʙʏ » <a href="{support_url}">{bot_name}</a>'
    else:
        caption += f"❍ ʙʏ » {bot_name}"

    markup = _support_markup()

    # Prefer image like Music Bot, but never let a bad image URL break /ping.
    if image_url:
        try:
            return await client.send_photo(
                chat_id,
                photo=image_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception:
            pass

    return await client.send_message(
        chat_id,
        caption,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        disable_web_page_preview=True,
    )


# ── /ping ──────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message) -> None:
    try:
        await _send_ping(client, message)
    except Exception as exc:
        # Final hard fallback: /ping must still answer even if a system metric,
        # image or formatting operation fails.
        try:
            await message.reply(
                f"🏓 <b>Pong!</b>\n<code>{_esc(type(exc).__name__)}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


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


@app.on_message(
    filters.command(["speedtest", "spt"]) & filters.user(config.OWNER_ID)
)
async def speedtest_cmd(client, message: Message) -> None:
    status = await message.reply(
        "❍ sᴛᴀʀᴛɪɴɢ sᴘᴇᴇᴅ ᴛᴇsᴛ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ..."
    )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_speedtest)

    if not result:
        return await status.edit(
            "❍ sᴘᴇᴇᴅᴛᴇsᴛ ғᴀɪʟᴇᴅ, ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ"
        )

    download = result.get("download", 0) / 1_000_000
    upload = result.get("upload", 0) / 1_000_000
    ping = result.get("ping", 0)
    client_info = result.get("client", {}) or {}
    server_info = result.get("server", {}) or {}
    share = result.get("share")

    text = (
        "⚡ <b>sᴘᴇᴇᴅᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n"
        f"<b>ɪsᴘ</b> : <code>{_esc(client_info.get('isp', 'N/A'))}</code>\n"
        f"<b>ᴄᴏᴜɴᴛʀʏ</b> : <code>{_esc(client_info.get('country', 'N/A'))}</code>\n\n"
        f"<b>sᴇʀᴠᴇʀ</b> : <code>{_esc(server_info.get('name', 'N/A'))}</code>\n"
        f"<b>sᴘᴏɴsᴏʀ</b> : <code>{_esc(server_info.get('sponsor', 'N/A'))}</code>\n"
        f"<b>ʟᴀᴛᴇɴᴄʏ</b> : <code>{server_info.get('latency', 'N/A')} ms</code>\n\n"
        f"<b>ᴘɪɴɢ</b> : <code>{ping:.2f} ms</code>\n"
        f"<b>ᴅᴏᴡɴʟᴏᴀᴅ</b> : <code>{download:.2f} Mbps</code>\n"
        f"<b>ᴜᴘʟᴏᴀᴅ</b> : <code>{upload:.2f} Mbps</code>"
    )

    try:
        await status.delete()
    except Exception:
        pass

    if share:
        try:
            return await client.send_photo(
                message.chat.id,
                share,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=_support_markup(),
            )
        except Exception:
            pass

    await client.send_message(
        message.chat.id,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_support_markup(),
        disable_web_page_preview=True,
    )
