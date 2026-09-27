# --------------------------------------------------------------------------------
# Elara © 2026
# handlers/warnings.py — GC Warning Management
# --------------------------------------------------------------------------------

import re
from datetime import datetime, timedelta, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import RPCError
from pyrogram.types import ChatPermissions

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
TIME_RE = re.compile(r"^(\d+)([mhdw])$", re.IGNORECASE)
TIME_MULTIPLIERS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
VALID_MODES = {"ban", "mute", "kick", "tban", "tmute"}
DEFAULT_LIMIT = 3
DEFAULT_MODE = "mute"


def _col(name):
    return db[name] if db is not None else None


def _mention(user):
    name = (getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)).strip()
    return f'<a href="tg://user?id={int(user.id)}">{name}</a>'


def _duration(raw):
    if not raw or str(raw).lower() == "off":
        return None
    m = TIME_RE.fullmatch(str(raw).strip())
    if not m or int(m.group(1)) <= 0:
        return None
    seconds = int(m.group(1)) * TIME_MULTIPLIERS[m.group(2).lower()]
    if seconds > 366 * 86400:
        return None
    return timedelta(seconds=seconds)


def _format_duration(td):
    seconds = int(td.total_seconds())
    for suffix, unit in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % unit == 0:
            return f"{seconds // unit}{suffix}"
    return f"{seconds}s"


async def _group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _admin(message):
    if not message.from_user or not await _group(message):
        return False
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _has_warn_right(message):
    if not await _admin(message):
        return False
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        if m.status == ChatMemberStatus.OWNER:
            return True
        if db is not None:
            doc = await db["admin_rights"].find_one({"chat_id": int(message.chat.id), "user_id": int(message.from_user.id)})
            if doc is not None:
                rights = set(doc.get("rights", []))
                return "ban" in rights or "delete" in rights
        privileges = getattr(m, "privileges", None)
        return bool(privileges and getattr(privileges, "can_restrict_members", False))
    except Exception:
        return False


async def _bot_can_restrict(message):
    try:
        m = await app.get_chat_member(message.chat.id, "me")
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _resolve_target(message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    args = message.command or []
    if len(args) < 2:
        return None
    raw = args[1].strip()
    try:
        if raw.lstrip("-").isdigit():
            return await app.get_users(int(raw))
        return await app.get_users(raw[1:] if raw.startswith("@") else raw)
    except Exception:
        return None


async def _target_guard(message, target):
    if not target:
        return False, "❌ <b>User not found.</b>"
    if target.is_bot:
        return False, "❌ <b>Bots cannot be warned.</b>"
    if message.from_user and target.id == message.from_user.id:
        return False, "❌ <b>You can't warn yourself.</b>"
    try:
        m = await app.get_chat_member(message.chat.id, target.id)
        if m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return False, "❌ <b>I can't warn another administrator.</b>"
    except Exception:
        pass
    return True, None


async def _settings(chat_id):
    col = _col("warning_settings")
    if col is None:
        return {"limit": DEFAULT_LIMIT, "mode": DEFAULT_MODE, "duration": None}
    doc = await col.find_one({"chat_id": int(chat_id)})
    if not doc:
        return {"limit": DEFAULT_LIMIT, "mode": DEFAULT_MODE, "duration": None}
    return {"limit": int(doc.get("limit", DEFAULT_LIMIT)), "mode": doc.get("mode", DEFAULT_MODE), "duration": doc.get("duration")}


async def _save_settings(chat_id, **values):
    col = _col("warning_settings")
    if col is None:
        return
    await col.update_one({"chat_id": int(chat_id)}, {"$set": {"chat_id": int(chat_id), **values}}, upsert=True)


async def _prune(chat_id, user_id=None):
    col = _col("chat_warnings")
    if col is None:
        return
    q = {"chat_id": int(chat_id), "expires_at": {"$ne": None, "$lte": datetime.now(timezone.utc)}}
    if user_id is not None:
        q["user_id"] = int(user_id)
    await col.delete_many(q)


async def _warnings(chat_id, user_id):
    await _prune(chat_id, user_id)
    col = _col("chat_warnings")
    if col is None:
        return []
    return await col.find({"chat_id": int(chat_id), "user_id": int(user_id)}).sort("created_at", 1).to_list(length=1000)


async def _punish(message, target, mode):
    if not await _bot_can_restrict(message):
        return False, "❌ <b>I need admin permissions to apply the warning action.</b>"
    cid, uid = message.chat.id, target.id
    try:
        if mode in ("ban", "tban"):
            until = None
            if mode == "tban":
                until = datetime.now(timezone.utc) + timedelta(hours=24)
            await app.ban_chat_member(cid, uid, until_date=until)
        elif mode in ("mute", "tmute"):
            until = None
            if mode == "tmute":
                until = datetime.now(timezone.utc) + timedelta(hours=24)
            await app.restrict_chat_member(cid, uid, ChatPermissions(can_send_messages=False), until_date=until)
        elif mode == "kick":
            await app.ban_chat_member(cid, uid)
            await app.unban_chat_member(cid, uid)
        return True, None
    except RPCError as exc:
        return False, f"❌ <b>Warning action failed:</b> <code>{type(exc).__name__}</code>"
    except Exception:
        return False, "❌ <b>I couldn't apply the warning action.</b>"


async def _warn(message, silent=False, delete_target=False):
    if not await _group(message):
        return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message):
        return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    target = await _resolve_target(message)
    ok, err = await _target_guard(message, target)
    if not ok:
        return await message.reply(err)

    args = message.command or []
    reason_start = 1 if message.reply_to_message else 2
    reason = " ".join(args[reason_start:]).strip() if len(args) > reason_start else "No reason provided"
    settings = await _settings(message.chat.id)
    expires = None if not settings["duration"] else datetime.now(timezone.utc) + timedelta(seconds=int(settings["duration"]))

    col = _col("chat_warnings")
    if col is None:
        return await message.reply("❌ <b>Warning database is unavailable.</b>")
    await col.insert_one({
        "chat_id": int(message.chat.id), "user_id": int(target.id),
        "reason": reason, "created_at": datetime.now(timezone.utc),
        "expires_at": expires, "warned_by": int(message.from_user.id),
    })

    warns = await _warnings(message.chat.id, target.id)
    count = len(warns)
    triggered = count >= settings["limit"]
    if triggered:
        ok, err = await _punish(message, target, settings["mode"])
        if not ok:
            return await message.reply(err)
        await col.delete_many({"chat_id": int(message.chat.id), "user_id": int(target.id)})
        if delete_target:
            try: await message.reply_to_message.delete()
            except Exception: pass
        if silent:
            try: await message.delete()
            except Exception: pass
            return
        return await message.reply(f"{_mention(target)} ⚠️ Wᴀʀɴ Lɪᴍɪᴛ Rᴇᴀᴄʜᴇᴅ • {settings['mode'].upper()}.")

    if delete_target:
        try: await message.reply_to_message.delete()
        except Exception: pass
    if silent:
        try: await message.delete()
        except Exception: pass
        return
    await message.reply(f"{_mention(target)} ⚠️ Wᴀʀɴᴇᴅ [{count}/{settings['limit']}] — {reason}")


@app.on_message(filters.command("warn", prefixes=PREFIXES))
async def warn(_, message): return await _warn(message)

@app.on_message(filters.command("dwarn", prefixes=PREFIXES))
async def dwarn(_, message):
    if not message.reply_to_message: return await message.reply("❌ <b>Reply to the user's message with</b> <code>/dwarn</code>.")
    return await _warn(message, delete_target=True)

@app.on_message(filters.command("swarn", prefixes=PREFIXES))
async def swarn(_, message): return await _warn(message, silent=True)


@app.on_message(filters.command("warns", prefixes=PREFIXES))
async def warns(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    target = await _resolve_target(message) or message.from_user
    rows = await _warnings(message.chat.id, target.id)
    if not rows: return await message.reply(f"{_mention(target)} has <b>0</b> warnings.")
    text = f"{_mention(target)} ⚠️ <b>{len(rows)} Warnings</b>\n"
    for i, row in enumerate(rows, 1): text += f"\n{i}. {row.get('reason','No reason')}"
    await message.reply(text)


@app.on_message(filters.command("rmwarn", prefixes=PREFIXES))
async def rmwarn(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    target = await _resolve_target(message) or message.from_user
    col = _col("chat_warnings")
    if col is None: return await message.reply("❌ <b>Warning database is unavailable.</b>")
    await _prune(message.chat.id, target.id)
    row = await col.find_one({"chat_id": int(message.chat.id), "user_id": int(target.id)}, sort=[("created_at", -1)])
    if not row: return await message.reply(f"{_mention(target)} has no warnings.")
    await col.delete_one({"_id": row["_id"]})
    await message.reply(f"{_mention(target)} 🕊 Lᴀᴛᴇsᴛ Wᴀʀɴɪɴɢ Rᴇᴍᴏᴠᴇᴅ.")


@app.on_message(filters.command("resetwarn", prefixes=PREFIXES))
async def resetwarn(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    target = await _resolve_target(message) or message.from_user
    col = _col("chat_warnings")
    if col is not None: await col.delete_many({"chat_id": int(message.chat.id), "user_id": int(target.id)})
    await message.reply(f"{_mention(target)} 🕊 Wᴀʀɴɪɴɢs Rᴇsᴇᴛ Tᴏ 0.")


@app.on_message(filters.command("resetallwarns", prefixes=PREFIXES))
async def resetallwarns(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    col = _col("chat_warnings")
    if col is not None: await col.delete_many({"chat_id": int(message.chat.id)})
    await message.reply("🕊 Aʟʟ Wᴀʀɴɪɴɢs Rᴇsᴇᴛ Tᴏ 0.")


@app.on_message(filters.command("warnings", prefixes=PREFIXES))
async def warnings(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    s = await _settings(message.chat.id)
    duration = "off" if not s["duration"] else _format_duration(timedelta(seconds=int(s["duration"])))
    await message.reply(f"⚠️ <b>Wᴀʀɴɪɴɢ Sᴇᴛᴛɪɴɢs</b>\nLɪᴍɪᴛ: <code>{s['limit']}</code>\nMᴏᴅᴇ: <code>{s['mode']}</code>\nTɪᴍᴇ: <code>{duration}</code>")


@app.on_message(filters.command("warnmode", prefixes=PREFIXES))
async def warnmode(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    args = message.command or []
    s = await _settings(message.chat.id)
    if len(args) == 1: return await message.reply(f"⚠️ Wᴀʀɴ Mᴏᴅᴇ: <code>{s['mode']}</code>")
    mode = args[1].lower()
    if mode not in VALID_MODES: return await message.reply("❌ <b>Invalid mode.</b> Use: <code>ban</code>, <code>mute</code>, <code>kick</code>, <code>tban</code>, <code>tmute</code>.")
    await _save_settings(message.chat.id, mode=mode)
    await message.reply(f"⚠️ Wᴀʀɴ Mᴏᴅᴇ Sᴇᴛ Tᴏ <code>{mode}</code>.")


@app.on_message(filters.command("warnlimit", prefixes=PREFIXES))
async def warnlimit(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    args = message.command or []
    s = await _settings(message.chat.id)
    if len(args) == 1: return await message.reply(f"⚠️ Wᴀʀɴ Lɪᴍɪᴛ: <code>{s['limit']}</code>")
    try: limit = int(args[1])
    except ValueError: limit = 0
    if not 1 <= limit <= 100: return await message.reply("❌ <b>Limit must be between 1 and 100.</b>")
    await _save_settings(message.chat.id, limit=limit)
    await message.reply(f"⚠️ Wᴀʀɴ Lɪᴍɪᴛ Sᴇᴛ Tᴏ <code>{limit}</code>.")


@app.on_message(filters.command("warntime", prefixes=PREFIXES))
async def warntime(_, message):
    if not await _group(message): return await message.reply("❌ <b>This command can only be used in groups.</b>")
    if not await _has_warn_right(message): return await message.reply("❌ <b>You don't have permission to use this command.</b>")
    args = message.command or []
    s = await _settings(message.chat.id)
    if len(args) == 1:
        value = "off" if not s["duration"] else _format_duration(timedelta(seconds=int(s["duration"])))
        return await message.reply(f"⚠️ Wᴀʀɴ Tɪᴍᴇ: <code>{value}</code>")
    raw = args[1].lower()
    if raw == "off":
        await _save_settings(message.chat.id, duration=None)
        return await message.reply("⚠️ Wᴀʀɴ Tɪᴍᴇ Dɪsᴀʙʟᴇᴅ.")
    td = _duration(raw)
    if not td: return await message.reply("❌ <b>Invalid time.</b> Use <code>4m</code>, <code>3h</code>, <code>6d</code> or <code>5w</code>, or <code>off</code>.")
    await _save_settings(message.chat.id, duration=int(td.total_seconds()))
    await message.reply(f"⚠️ Wᴀʀɴ Tɪᴍᴇ Sᴇᴛ Tᴏ <code>{_format_duration(td)}</code>.")
