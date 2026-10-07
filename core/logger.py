# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/logger.py — 📝 Bot Activity Logger
#  Logs go to: LOG_GROUP_ID (fallback: OWNER_ID)
# --------------------------------------------------------------------------------

from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import psutil

import config
from core.bot import app
from database.mongo import db


# ══════════════════════════════════════════════════════════════════════════════
#  📢 LOG DESTINATION
# ══════════════════════════════════════════════════════════════════════════════
# Logs will go to this group/channel. Fallback = OWNER_ID DM.
LOG_GROUP_ID = -1004454997629


# ══════════════════════════════════════════════════════════════════════════════
#  DB Collections
# ══════════════════════════════════════════════════════════════════════════════
def _logs_col():
    return db["bot_logs"] if db is not None else None


def _groups_col():
    return db["bot_groups"] if db is not None else None


def _startups_col():
    return db["bot_startups"] if db is not None else None


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════
def _now():
    return datetime.now(timezone.utc)


def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _send_log(text: str):
    """Send log to LOG_GROUP_ID. Fallback to OWNER_ID DM if group fails."""
    sent = False

    # Try LOG_GROUP_ID first
    if LOG_GROUP_ID:
        try:
            await app.send_message(
                LOG_GROUP_ID,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent = True
        except Exception as e:
            print(f"[LOGGER log-group] {type(e).__name__}: {e}", flush=True)

    # Fallback: OWNER_ID DM
    if not sent and config.OWNER_ID:
        try:
            await app.send_message(
                int(config.OWNER_ID),
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent = True
        except Exception as e:
            print(f"[LOGGER owner-dm] {type(e).__name__}: {e}", flush=True)

    return sent


def _group_link(chat) -> str:
    """Return invite link if available."""
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}"
    try:
        if chat.id < 0:
            short = str(chat.id)[4:]
            return f"https://t.me/c/{short}/1"
    except Exception:
        pass
    return "🔒 Private (no public link)"


# ══════════════════════════════════════════════════════════════════════════════
#  1️⃣ BOT STARTUP LOG
# ══════════════════════════════════════════════════════════════════════════════
async def log_startup():
    """Log bot startup: system info, timestamp, etc."""
    try:
        boot_time = datetime.now(timezone.utc)

        try:
            cpu_count = os.cpu_count() or 0
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            ram_total_gb = round(ram.total / (1024 ** 3), 2)
            disk_total_gb = round(disk.total / (1024 ** 3), 2)
            cpu_percent = psutil.cpu_percent(interval=0.5)
        except Exception:
            cpu_count = 0
            ram_total_gb = 0
            disk_total_gb = 0
            cpu_percent = 0

        try:
            me = await app.get_me()
            bot_id = me.id
            bot_username = me.username or "—"
            bot_name = me.first_name or "—"
        except Exception as e:
            print(f"[LOGGER startup] get_me failed: {e}", flush=True)
            bot_id = 0
            bot_username = "—"
            bot_name = config.BOT_NAME or "Elara"

        data = {
            "boot_time": boot_time,
            "bot_id": bot_id,
            "bot_username": bot_username,
            "bot_name": bot_name,
            "python_version": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "cpu_count": cpu_count,
            "cpu_percent": cpu_percent,
            "ram_total_gb": ram_total_gb,
            "disk_total_gb": disk_total_gb,
            "pid": os.getpid(),
        }

        col = _startups_col()
        if col is not None:
            await col.insert_one(data)

        text = (
            "🚀 <b>ᴇʟᴀʀᴀ sᴛᴀʀᴛᴇᴅ</b>\n\n"
            f"🕐 <b>ᴛɪᴍᴇ:</b> <code>{boot_time.strftime('%Y-%m-%d %H:%M:%S')} UTC</code>\n\n"
            f"🤖 <b>ʙᴏᴛ:</b> <a href=\"https://t.me/{bot_username}\">{_esc(bot_name)}</a>\n"
            f"🆔 <b>ʙᴏᴛ ɪᴅ:</b> <code>{bot_id}</code>\n"
            f"👤 <b>ᴜsᴇʀɴᴀᴍᴇ:</b> <code>@{bot_username}</code>\n\n"
            f"💻 <b>sʏsᴛᴇᴍ:</b>\n"
            f"  • <b>ᴏs:</b> <code>{data['platform']}</code>\n"
            f"  • <b>ᴘʏᴛʜᴏɴ:</b> <code>{data['python_version']}</code>\n"
            f"  • <b>ᴄᴘᴜ:</b> <code>{cpu_count} cores ({cpu_percent}%)</code>\n"
            f"  • <b>ʀᴀᴍ:</b> <code>{ram_total_gb} GB</code>\n"
            f"  • <b>ᴅɪsᴋ:</b> <code>{disk_total_gb} GB</code>\n"
            f"  • <b>ᴘɪᴅ:</b> <code>{data['pid']}</code>"
        )
        await _send_log(text)

        print(f"[LOGGER] startup logged — {bot_username}", flush=True)
    except Exception as e:
        print(f"[LOGGER startup] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  2️⃣ GROUP JOIN LOG
# ══════════════════════════════════════════════════════════════════════════════
async def log_group_join(chat, added_by=None, is_new: bool = True):
    """Log when bot is added to a new group."""
    try:
        group_link = _group_link(chat)
        member_count = getattr(chat, "members_count", 0) or 0

        data = {
            "chat_id": int(chat.id),
            "title": getattr(chat, "title", "Unknown"),
            "username": getattr(chat, "username", None) or "",
            "type": str(getattr(chat, "type", "unknown")).lower(),
            "member_count": member_count,
            "link": group_link,
            "joined_at": _now(),
        }

        col = _groups_col()
        if col is not None:
            await col.update_one(
                {"chat_id": int(chat.id)},
                {
                    "$set": {
                        **data,
                        "last_joined_at": _now(),
                        "active": True,
                    },
                    "$setOnInsert": {
                        "first_joined_at": _now(),
                    },
                    "$inc": {"join_count": 1},
                },
                upsert=True,
            )

        # Adder info
        adder_line = "—"
        if added_by:
            adder_name = added_by.first_name or added_by.username or str(added_by.id)
            adder_mention = f'<a href="tg://user?id={added_by.id}">{_esc(adder_name)}</a>'
            adder_line = (
                f"{adder_mention}\n"
                f"🆔 <b>ᴀᴅᴅᴇʀ ɪᴅ:</b> <code>{added_by.id}</code>\n"
                f"🔗 <b>ᴜsᴇʀɴᴀᴍᴇ:</b> <code>@{added_by.username or '—'}</code>"
            )

        status = "🆕 ᴊᴏɪɴᴇᴅ" if is_new else "🔄 ʀᴇ-ᴊᴏɪɴᴇᴅ"

        text = (
            f"📍 <b>ɢʀᴏᴜᴘ {status}</b>\n\n"
            f"📛 <b>ᴛɪᴛʟᴇ:</b> {_esc(data['title'])}\n"
            f"🆔 <b>ɢʀᴏᴜᴘ ɪᴅ:</b> <code>{chat.id}</code>\n"
            f"🔗 <b>ʟɪɴᴋ:</b> {group_link}\n"
            f"👥 <b>ᴍᴇᴍʙᴇʀs:</b> <code>{member_count}</code>\n"
            f"📂 <b>ᴛʏᴘᴇ:</b> <code>{data['type']}</code>\n\n"
            f"👤 <b>ᴀᴅᴅᴇᴅ ʙʏ:</b>\n{adder_line}"
        )
        await _send_log(text)

        print(f"[LOGGER] group joined: {data['title']} ({chat.id})", flush=True)
    except Exception as e:
        print(f"[LOGGER group] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  3️⃣ GROUP LEAVE LOG
# ══════════════════════════════════════════════════════════════════════════════
async def log_group_leave(chat):
    """Log when bot is removed from a group."""
    try:
        col = _groups_col()
        if col is not None:
            await col.update_one(
                {"chat_id": int(chat.id)},
                {"$set": {"left_at": _now(), "active": False}},
            )

        text = (
            "🚪 <b>ɢʀᴏᴜᴘ ʟᴇꜰᴛ</b>\n\n"
            f"📛 <b>ᴛɪᴛʟᴇ:</b> {_esc(getattr(chat, 'title', 'Unknown'))}\n"
            f"🆔 <b>ɢʀᴏᴜᴘ ɪᴅ:</b> <code>{chat.id}</code>"
        )
        await _send_log(text)
        print(f"[LOGGER] group left: {chat.id}", flush=True)
    except Exception as e:
        print(f"[LOGGER leave] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  4️⃣ INITIAL GROUPS SYNC
# ══════════════════════════════════════════════════════════════════════════════
async def sync_existing_groups():
    """On startup, log count of known groups."""
    try:
        col = _groups_col()
        if col is None:
            return
        total = await col.count_documents({"active": {"$ne": False}})
        print(f"[LOGGER] syncing {total} known groups", flush=True)
    except Exception as e:
        print(f"[LOGGER sync] {type(e).__name__}: {e}", flush=True)
