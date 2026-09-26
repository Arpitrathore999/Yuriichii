import asyncio
import logging
import re

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    ChatForwardsRestricted, ChatWriteForbidden, FloodWait,
    MediaEmpty, MessageIdInvalid, PeerIdInvalid, UserIsBlocked,
)
from pyrogram.types import Message

import config
from core.bot import app
from database.broadcast import (
    get_broadcast_chats, get_broadcast_count, remove_broadcast_chat,
)

logger = logging.getLogger(__name__)
_broadcast_lock = asyncio.Lock()
_IS_BROADCASTING = False

def _owner(message):
    return bool(
        message.from_user
        and config.OWNER_ID
        and int(message.from_user.id) == int(config.OWNER_ID)
    )

def _parse_flags(raw):
    return (
        bool(re.search(r"-pin(?!loud)", raw)),
        "-pinloud" in raw,
        "-nogroup" in raw,
        "-user" in raw,
    )

def _strip_flags(text):
    for flag in ("-pinloud", "-nogroup", "-user", "-pin"):
        text = text.replace(flag, "")
    return text.strip()

async def _send(target_id, source, mode, text):
    if mode == "text":
        return await app.send_message(target_id, text, parse_mode=ParseMode.HTML)
    try:
        return await app.forward_messages(target_id, source.chat.id, source.id)
    except (ChatForwardsRestricted, MediaEmpty, MessageIdInvalid):
        return await app.copy_message(target_id, source.chat.id, source.id)

@app.on_message(filters.command(["broadcast", "gcast"]))
async def broadcast_cmd(_, message: Message):
    if not _owner(message):
        return
    global _IS_BROADCASTING
    async with _broadcast_lock:
        if _IS_BROADCASTING:
            return await message.reply_text("❍ ᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ.")
        _IS_BROADCASTING = True
        try:
            await _run_broadcast(message)
        finally:
            _IS_BROADCASTING = False

async def _run_broadcast(message):
    raw = message.text or ""
    parts = raw.split(None, 1)
    raw_args = parts[1] if len(parts) > 1 else ""

    pin, pinloud, nogroup, users = _parse_flags(raw_args)
    clean_text = _strip_flags(raw_args)

    source = message.reply_to_message if message.reply_to_message else None
    if source:
        mode = "reply"
    elif clean_text:
        mode = "text"
    else:
        return await message.reply_text(
            "❍ Reply to a message or use:\n"
            "`/broadcast Hello everyone`\n\n"
            "Flags: `-pin` `-pinloud` `-nogroup` `-user`"
        )

    docs = await get_broadcast_chats()
    groups = [d for d in docs if d.get("type") == "group"]
    private = [d for d in docs if d.get("type") == "private"]
    targets = (0 if nogroup else len(groups)) + (len(private) if users else 0)

    if not targets:
        return await message.reply_text("❍ ɴᴏ ᴛᴀʀɢᴇᴛs ғᴏᴜɴᴅ.")

    counts = await get_broadcast_count()
    status = await message.reply_text(
        f"❍ <b>ʙʀᴏᴀᴅᴄᴀsᴛ sᴛᴀʀᴛᴇᴅ</b>\n\n"
        f"ᴛᴏᴛᴀʟ: <code>{counts['total']}</code>\n"
        f"ɢʀᴏᴜᴘs: <code>{len(groups)}</code>\n"
        f"ᴜsᴇʀs: <code>{len(private)}</code>\n"
        f"ᴛᴀʀɢᴇᴛs: <code>{targets}</code>"
    )

    ok_g = ok_u = failed = pinned = 0

    async def deliver(doc, is_group):
        nonlocal ok_g, ok_u, failed, pinned
        cid = int(doc["chat_id"])
        try:
            sent = await _send(cid, source, mode, clean_text)
            if is_group:
                ok_g += 1
                if pin or pinloud:
                    try:
                        await app.pin_chat_message(cid, sent.id,
                                                   disable_notification=not pinloud)
                        pinned += 1
                    except Exception:
                        pass
            else:
                ok_u += 1
        except FloodWait as e:
            if int(e.value) <= 200:
                await asyncio.sleep(int(e.value))
                try:
                    await _send(cid, source, mode, clean_text)
                    if is_group: ok_g += 1
                    else: ok_u += 1
                except Exception:
                    failed += 1
            else:
                failed += 1
        except (UserIsBlocked, ChatWriteForbidden, PeerIdInvalid):
            await remove_broadcast_chat(cid)
            failed += 1
        except Exception as e:
            logger.warning("Broadcast %s: %s", cid, e)
            failed += 1
        await asyncio.sleep(0.4)

    if not nogroup:
        for doc in groups:
            await deliver(doc, True)
    if users:
        for doc in private:
            await deliver(doc, False)

    await status.edit_text(
        f"❍ <b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ✅</b>\n\n"
        f"ɢʀᴏᴜᴘs: <code>{ok_g}</code>\n"
        f"ᴜsᴇʀs: <code>{ok_u}</code>\n"
        f"ᴘɪɴɴᴇᴅ: <code>{pinned}</code>\n"
        f"ғᴀɪʟᴇᴅ: <code>{failed}</code>"
    )

# Register every chat in which the bot receives a message.
@app.on_message()
async def _register_chat(_, message: Message):
    try:
        from database.broadcast import register_chat
        await register_chat(message.chat)
    except Exception:
        pass
