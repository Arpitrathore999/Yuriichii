# --------------------------------------------------------------------------------
# Elara © 2026
# handlers/bans.py — GC Ban / Mute Management
# --------------------------------------------------------------------------------

import asyncio
import re
from datetime import datetime, timedelta, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, MessageEntityType
from pyrogram.errors import RPCError, ChatWriteForbidden
from pyrogram.types import ChatPermissions

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
TIME_RE = re.compile(r"^(\d+)([mhdw])$", re.IGNORECASE)
TIME_MULTIPLIERS = {
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


def _collection(name):
    return db[name] if db is not None else None


def _display_name(user):
    if not user:
        return "User"
    return (user.first_name or user.username or str(user.id)).strip()


def _mention(user):
    name = _display_name(user)
    return f'<a href="tg://user?id={int(user.id)}">{name}</a>'


async def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _is_admin(message):
    if not message.from_user or not await _is_group(message):
        return False
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _has_right(message, right):
    if not await _is_admin(message):
        return False
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        if member.status == ChatMemberStatus.OWNER:
            return True
        if db is not None:
            doc = await db["admin_rights"].find_one({
                "chat_id": int(message.chat.id),
                "user_id": int(message.from_user.id),
            })
            if doc is not None:
                return right in set(doc.get("rights", []))
        privileges = getattr(member, "privileges", None)
        mapping = {
            "ban": "can_restrict_members",
            "delete": "can_delete_messages",
        }
        return bool(privileges and getattr(privileges, mapping.get(right, right), False))
    except Exception:
        return False


async def _bot_can_restrict(message):
    try:
        me = await app.get_chat_member(message.chat.id, "me")
        return me.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _safe_reply(message, text, **kwargs):
    """Prevents crash if bot is muted or kicked (CHAT_WRITE_FORBIDDEN)"""
    try:
        await message.reply(text, **kwargs)
    except ChatWriteForbidden:
        pass
    except Exception:
        pass

async def _permission_error(message):
    await _safe_reply(message, "❌ <b>You don't have permission to use this command.</b>")

async def _group_error(message):
    await _safe_reply(message, "❌ <b>This command can only be used in groups.</b>")

async def _bot_permission_error(message):
    await _safe_reply(message, "❌ <b>I need the required admin permissions to manage members.</b>")


def _parse_duration(raw):
    if not raw:
        return None
    match = TIME_RE.fullmatch(raw.strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        return None
    seconds = amount * TIME_MULTIPLIERS[unit]
    if seconds > 366 * 24 * 60 * 60:
        return None
    return timedelta(seconds=seconds)


async def _resolve_target(message, arg_index=1):
    """Resolve a target from reply, mention (entity), username, or ID."""
    # 1. Reply Message
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user

    # 2. Text Mention (entities) - e.g., /ban [User](tg://user?id=123)
    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntityType.TEXT_MENTION:
                return entity.user
            if entity.type == MessageEntityType.MENTION:
                username = message.text[entity.offset+1 : entity.offset+entity.length]
                try:
                    return await app.get_users(username)
                except Exception:
                    pass

    # 3. Command Args (Username or ID)
    commands = message.command or []
    # Check first and second arg (sometimes reasons are appended)
    for idx in (1, 2):
        if len(commands) > idx:
            raw = commands[idx].strip()
            if not raw:
                continue
            
            # Numeric ID
            if raw.lstrip("-").isdigit():
                try:
                    return await app.get_users(int(raw))
                except Exception:
                    pass

            # Username
            if raw.startswith("@"):
                raw = raw[1:]
            if raw:
                try:
                    return await app.get_users(raw)
                except Exception:
                    pass

    return None


def _duration_from_args(message, index):
    commands = message.command or []
    # If they replied, duration is at index 1. If no reply, duration is usually at index 2 (after username)
    if message.reply_to_message:
        if len(commands) > 1:
            return _parse_duration(commands[1])
    else:
        if len(commands) > 2:
            return _parse_duration(commands[2])
    return None


async def _delete_message(message):
    try:
        await message.delete()
    except Exception:
        pass


async def _delete_target_message(message):
    if not message.reply_to_message:
        return
    try:
        await message.reply_to_message.delete()
    except Exception:
        pass


async def _save_action(chat_id, user_id, action, until_date=None):
    collection = _collection("moderation_actions")
    if collection is None:
        return
    await collection.update_one(
        {"chat_id": int(chat_id), "user_id": int(user_id), "action": action},
        {
            "$set": {
                "chat_id": int(chat_id),
                "user_id": int(user_id),
                "action": action,
                "until": until_date,
                "created_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def _remove_action(chat_id, user_id, action):
    collection = _collection("moderation_actions")
    if collection is None:
        return
    await collection.delete_one({"chat_id": int(chat_id), "user_id": int(user_id), "action": action})


async def _can_act_on(message, target):
    if not target:
        return False, "❌ <b>User not found. Reply to a message or mention them.</b>"
    if message.from_user and target.id == message.from_user.id:
        return False, "❌ <b>You can't use this command on yourself.</b>"
    try:
        target_member = await app.get_chat_member(message.chat.id, target.id)
        if target_member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return False, "❌ <b>I can't manage another administrator.</b>"
    except Exception:
        pass
    return True, None


async def _ban(message, silent=False, delete_target=False, temporary=False):
    if not await _is_group(message):
        return await _group_error(message)
    if not await _has_right(message, "ban"):
        return await _permission_error(message)
    if not await _bot_can_restrict(message):
        return await _bot_permission_error(message)

    target = await _resolve_target(message)
    ok, error = await _can_act_on(message, target)
    if not ok:
        return await _safe_reply(message, error)

    duration = None
    if temporary:
        duration = _duration_from_args(message, 1)
        if not duration:
            return await _safe_reply(message, "❌ <b>Invalid time.</b> Use <code>4m</code>, <code>3h</code>, <code>6d</code> or <code>5w</code>.")

    until = datetime.now(timezone.utc) + duration if duration else None
    try:
        await app.ban_chat_member(message.chat.id, target.id, until_date=until)
    except RPCError as exc:
        return await _safe_reply(message, f"❌ <b>Ban failed:</b> <code>{type(exc).__name__}</code>")
    except Exception:
        return await _safe_reply(message, "❌ <b>I couldn't ban that user.</b>")

    await _save_action(message.chat.id, target.id, "ban", until)

    if delete_target:
        await _delete_target_message(message)
    if silent:
        await _delete_message(message)
        return

    if temporary:
        label = _format_duration(duration)
        await _safe_reply(message, f"{_mention(target)} 🕊 Bᴀɴɴᴇᴅ Fᴏʀ {label}.")
    else:
        await _safe_reply(message, f"{_mention(target)} 🕊 Bᴀɴɴᴇᴅ.")


async def _mute(message, silent=False, delete_target=False, temporary=False):
    if not await _is_group(message):
        return await _group_error(message)
    if not await _has_right(message, "ban"):
        return await _permission_error(message)
    if not await _bot_can_restrict(message):
        return await _bot_permission_error(message)

    target = await _resolve_target(message)
    ok, error = await _can_act_on(message, target)
    if not ok:
        return await _safe_reply(message, error)

    duration = None
    if temporary:
        duration = _duration_from_args(message, 1)
        if not duration:
            return await _safe_reply(message, "❌ <b>Invalid time.</b> Use <code>4m</code>, <code>3h</code>, <code>6d</code> or <code>5w</code>.")

    until = datetime.now(timezone.utc) + duration if duration else None
    permissions = ChatPermissions(can_send_messages=False)
    try:
        await app.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=permissions,
            until_date=until,
        )
    except RPCError as exc:
        return await _safe_reply(message, f"❌ <b>Mute failed:</b> <code>{type(exc).__name__}</code>")
    except Exception:
        return await _safe_reply(message, "❌ <b>I couldn't mute that user.</b>")

    await _save_action(message.chat.id, target.id, "mute", until)

    if delete_target:
        await _delete_target_message(message)
    if silent:
        await _delete_message(message)
        return

    if temporary:
        label = _format_duration(duration)
        await _safe_reply(message, f"{_mention(target)} 🔇 Mᴜᴛᴇᴅ Fᴏʀ {label}.")
    else:
        await _safe_reply(message, f"{_mention(target)} 🔇 Mᴜᴛᴇᴅ.")


async def _unmute(message):
    if not await _is_group(message):
        return await _group_error(message)
    if not await _has_right(message, "ban"):
        return await _permission_error(message)
    if not await _bot_can_restrict(message):
        return await _bot_permission_error(message)

    target = await _resolve_target(message)
    ok, error = await _can_act_on(message, target)
    if not ok:
        return await _safe_reply(message, error)

    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
    )
    try:
        await app.restrict_chat_member(message.chat.id, target.id, permissions=permissions)
    except Exception:
        return await _safe_reply(message, "❌ <b>I couldn't unmute that user.</b>")

    await _remove_action(message.chat.id, target.id, "mute")
    await _safe_reply(message, f"{_mention(target)} 🕊 Uɴᴍᴜᴛᴇᴅ.")


async def _kick(message, silent=False, delete_target=False):
    if not await _is_group(message):
        return await _group_error(message)
    if not await _has_right(message, "ban"):
        return await _permission_error(message)
    if not await _bot_can_restrict(message):
        return await _bot_permission_error(message)

    target = await _resolve_target(message)
    ok, error = await _can_act_on(message, target)
    if not ok:
        return await _safe_reply(message, error)

    try:
        await app.ban_chat_member(message.chat.id, target.id)
        await app.unban_chat_member(message.chat.id, target.id)
    except RPCError as exc:
        return await _safe_reply(message, f"❌ <b>Kick failed:</b> <code>{type(exc).__name__}</code>")
    except Exception:
        return await _safe_reply(message, "❌ <b>I couldn't kick that user.</b>")

    if delete_target:
        await _delete_target_message(message)
    if silent:
        await _delete_message(message)
        return
    await _safe_reply(message, f"{_mention(target)} 🕊 Kɪᴄᴋᴇᴅ.")


def _format_duration(delta):
    seconds = int(delta.total_seconds())
    units = (("w", 7 * 24 * 3600), ("d", 24 * 3600), ("h", 3600), ("m", 60))
    for suffix, value in units:
        if seconds % value == 0:
            return f"{seconds // value}{suffix}"
    return f"{seconds}s"


# ══════════════════════════════════════════════════════════════════════════════
# BAN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("dban", prefixes=PREFIXES))
async def dban(_, message):
    if not message.reply_to_message:
        return await _safe_reply(message, "❌ <b>Reply to the user's message with</b> <code>/dban</code>.")
    return await _ban(message, delete_target=True)


@app.on_message(filters.command("sban", prefixes=PREFIXES))
async def sban(_, message):
    commands = message.command or []
    duration_arg = commands[1] if message.reply_to_message and len(commands) > 1 else (commands[2] if len(commands) > 2 else None)
    if duration_arg and _parse_duration(duration_arg) is not None:
        return await _ban(message, silent=True, temporary=True)
    return await _ban(message, silent=True)


@app.on_message(filters.command("tban", prefixes=PREFIXES))
async def tban(_, message):
    return await _ban(message, temporary=True)


@app.on_message(filters.command("ban", prefixes=PREFIXES))
async def ban(_, message):
    return await _ban(message)


@app.on_message(filters.command("unban", prefixes=PREFIXES))
async def unban(_, message):
    if not await _is_group(message):
        return await _group_error(message)
    if not await _has_right(message, "ban"):
        return await _permission_error(message)
    if not await _bot_can_restrict(message):
        return await _bot_permission_error(message)

    target = await _resolve_target(message)
    if not target:
        return await _safe_reply(message, "❌ <b>User not found.</b>")
    try:
        await app.unban_chat_member(message.chat.id, target.id)
        await _remove_action(message.chat.id, target.id, "ban")
    except Exception:
        return await _safe_reply(message, "❌ <b>I couldn't unban that user.</b>")
    await _safe_reply(message, f"{_mention(target)} 🕊 Uɴʙᴀɴɴᴇᴅ.")


# ══════════════════════════════════════════════════════════════════════════════
# MUTE COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("mute", prefixes=PREFIXES))
async def mute(_, message):
    return await _mute(message)


@app.on_message(filters.command("dmute", prefixes=PREFIXES))
async def dmute(_, message):
    if not message.reply_to_message:
        return await _safe_reply(message, "❌ <b>Reply to the user's message with</b> <code>/dmute</code>.")
    return await _mute(message, delete_target=True)


@app.on_message(filters.command("smute", prefixes=PREFIXES))
async def smute(_, message):
    commands = message.command or []
    duration_arg = commands[1] if message.reply_to_message and len(commands) > 1 else (commands[2] if len(commands) > 2 else None)
    if duration_arg and _parse_duration(duration_arg) is not None:
        return await _mute(message, silent=True, temporary=True)
    return await _mute(message, silent=True)


@app.on_message(filters.command("tmute", prefixes=PREFIXES))
async def tmute(_, message):
    return await _mute(message, temporary=True)


@app.on_message(filters.command("unmute", prefixes=PREFIXES))
async def unmute(_, message):
    return await _unmute(message)


# ══════════════════════════════════════════════════════════════════════════════
# KICK COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("kick", prefixes=PREFIXES))
async def kick(_, message):
    return await _kick(message)


@app.on_message(filters.command("dkick", prefixes=PREFIXES))
async def dkick(_, message):
    if not message.reply_to_message:
        return await _safe_reply(message, "❌ <b>Reply to the user's message with</b> <code>/dkick</code>.")
    return await _kick(message, delete_target=True)


@app.on_message(filters.command("skick", prefixes=PREFIXES))
async def skick(_, message):
    return await _kick(message, silent=True)
