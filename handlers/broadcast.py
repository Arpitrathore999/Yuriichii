# --------------------------------------------------------------------------------
#  Yuriichii © 2026
#  Broadcast system — Music Bot style
# --------------------------------------------------------------------------------

import asyncio
import logging
import re

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    ChatAdminRequired,
    ChatForwardsRestricted,
    ChatWriteForbidden,
    FloodWait,
    MediaEmpty,
    MessageIdInvalid,
    PeerIdInvalid,
    UserIsBlocked,
)
from pyrogram.types import Message

import config
from core.bot import app
from database.broadcast import get_broadcast_chats, get_broadcast_count, remove_broadcast_chat, register_chat
from utils.rich_ui import rich_edit, rich_heading, rich_kv_table, rich_note, rich_send

logger = logging.getLogger(__name__)
_IS_BROADCASTING = False
_broadcast_lock = asyncio.Lock()


def _parse_flags(raw: str):
    pin = bool(re.search(r"-pin(?!loud)", raw))
    pinloud = "-pinloud" in raw
    nogroup = "-nogroup" in raw
    user = "-user" in raw
    return pin, pinloud, nogroup, user


def _strip_flags(text: str):
    for flag in ("-pinloud", "-nogroup", "-user", "-pin"):
        text = text.replace(flag, "")
    return text.strip()


async def _send(target_id: int, bm: Message, broadcast_type: str, text: str):
    if broadcast_type == "text":
        return await app.send_message(target_id, text, parse_mode=ParseMode.HTML)
    try:
        return await app.forward_messages(target_id, bm.chat.id, bm.id)
    except (ChatForwardsRestricted, MediaEmpty, MessageIdInvalid):
        return await app.copy_message(target_id, bm.chat.id, bm.id)


@app.on_message(filters.command(["broadcast", "gcast"]) & filters.user(config.OWNER_ID))
async def broadcast_cmd(_, message: Message):
    global _IS_BROADCASTING
    async with _broadcast_lock:
        if _IS_BROADCASTING:
            await rich_send(
                app, message.chat.id,
                rich_heading("❍ ᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ", level=3)
                + rich_note("ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ɪᴛ ᴛᴏ ғɪɴɪsʜ."),
            )
            return
        _IS_BROADCASTING = True
    try:
        await _run_broadcast(message)
    finally:
        _IS_BROADCASTING = False


async def _run_broadcast(message: Message):
    raw = message.text or ""
    try:
        raw_args = raw.split(None, 1)[1]
    except IndexError:
        raw_args = ""

    flag_pin, flag_pinloud, flag_nogroup, flag_user = _parse_flags(raw_args)
    clean_text = _strip_flags(raw_args)

    if message.reply_to_message:
        bm = message.reply_to_message
        broadcast_type = "reply"
    elif clean_text:
        bm = None
        broadcast_type = "text"
    else:
        await rich_send(
            app, message.chat.id,
            rich_heading("❍ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴏʀ ᴘʀᴏᴠɪᴅᴇ ᴛᴇxᴛ", level=3)
            + rich_kv_table([
                ("-pin", "ᴘɪɴ sɪʟᴇɴᴛʟʏ ɪɴ ɢʀᴏᴜᴘs"),
                ("-pinloud", "ᴘɪɴ ᴡɪᴛʜ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ"),
                ("-nogroup", "sᴋɪᴘ ɢʀᴏᴜᴘs"),
                ("-user", "ᴀʟsᴏ sᴇɴᴅ ᴛᴏ ᴘʀɪᴠᴀᴛᴇ ᴜsᴇʀs"),
            ], headers=["ғʟᴀɢ", "ᴇғғᴇᴄᴛ"]),
        )
        return

    all_docs = await get_broadcast_chats()
    counts = await get_broadcast_count()
    groups = [d for d in all_docs if d.get("type") == "group"]
    private = [d for d in all_docs if d.get("type") == "private"]
    targets = (0 if flag_nogroup else len(groups)) + (len(private) if flag_user else 0)

    if targets == 0:
        await rich_send(app, message.chat.id, rich_heading("❍ ɴᴏ ᴛᴀʀɢᴇᴛs ғᴏᴜɴᴅ ɪɴ ʙʀᴏᴀᴅᴄᴀsᴛ ʟɪsᴛ", level=3))
        return

    active_flags = " ".join(filter(None, [
        "-pin" if flag_pin else "",
        "-pinloud" if flag_pinloud else "",
        "-nogroup" if flag_nogroup else "",
        "-user" if flag_user else "",
    ])) or "none"

    pm = await rich_send(
        app, message.chat.id,
        rich_heading("❍ ʙʀᴏᴀᴅᴄᴀsᴛ sᴛᴀʀᴛᴇᴅ", level=3)
        + rich_kv_table([
            ("ᴛᴏᴛᴀʟ", f"<code>{counts['total']}</code>"),
            ("ɢʀᴏᴜᴘs", f"<code>{len(groups)}</code>"),
            ("ᴜsᴇʀs", f"<code>{len(private)}</code>"),
            ("ᴛᴀʀɢᴇᴛs", f"<code>{targets}</code>"),
            ("ғʟᴀɢs", f"<code>{active_flags}</code>"),
        ]),
    )

    success_g = success_u = pinned = failed = 0

    if not flag_nogroup:
        for doc in groups:
            cid = int(doc["chat_id"])
            try:
                sent = await _send(cid, bm, broadcast_type, clean_text)
                success_g += 1
                if flag_pin or flag_pinloud:
                    try:
                        await app.pin_chat_message(cid, sent.id, disable_notification=not flag_pinloud)
                        pinned += 1
                    except ChatAdminRequired:
                        pass
                    except Exception:
                        pass
            except FloodWait as e:
                wait = int(e.value)
                if wait > 200:
                    failed += 1
                    continue
                await asyncio.sleep(wait)
                try:
                    await _send(cid, bm, broadcast_type, clean_text)
                    success_g += 1
                except Exception:
                    failed += 1
            except (UserIsBlocked, ChatWriteForbidden, PeerIdInvalid):
                await remove_broadcast_chat(cid)
                failed += 1
            except Exception as e:
                logger.warning(f"[Broadcast] group {cid}: {e}")
                failed += 1
            await asyncio.sleep(0.4)

    if flag_user:
        for doc in private:
            uid = int(doc["chat_id"])
            try:
                await _send(uid, bm, broadcast_type, clean_text)
                success_u += 1
            except FloodWait as e:
                wait = int(e.value)
                if wait > 200:
                    failed += 1
                    continue
                await asyncio.sleep(wait)
                try:
                    await _send(uid, bm, broadcast_type, clean_text)
                    success_u += 1
                except Exception:
                    failed += 1
            except (UserIsBlocked, PeerIdInvalid):
                await remove_broadcast_chat(uid)
                failed += 1
            except Exception as e:
                logger.warning(f"[Broadcast] user {uid}: {e}")
                failed += 1
            await asyncio.sleep(0.4)

    await rich_edit(
        pm,
        rich_heading("❍ ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ✅", level=3)
        + rich_kv_table([
            ("ɢʀᴏᴜᴘs", f"<code>{success_g}</code>"),
            ("ᴜsᴇʀs", f"<code>{success_u}</code>"),
            ("ᴘɪɴɴᴇᴅ", f"<code>{pinned}</code>"),
            ("ғᴀɪʟᴇᴅ", f"<code>{failed}</code>"),
        ]),
    )


# Register chats for the broadcast list.
@app.on_message()
async def _register_chat(_, message: Message):
    try:
        await register_chat(message.chat)
    except Exception as e:
        logger.debug(f"[Broadcast] register failed: {e}")
