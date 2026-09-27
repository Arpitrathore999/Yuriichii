# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  handlers/broadcast.py — Music Bot style, Yuriichii compatible
# --------------------------------------------------------------------------------

import asyncio
import json
import logging
import re
from urllib.request import Request, urlopen

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
from database.mongo import db

bot = app
logger = logging.getLogger(__name__)

BOT_TOKEN = getattr(config, "BOT_TOKEN", "")

_IS_BROADCASTING = False
_broadcast_lock = asyncio.Lock()


# ── Yuriichii Rich Message API helpers ────────────────────────────────────────

async def _bot_api(method: str, payload: dict) -> dict:
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN missing"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")

    def _do():
        try:
            req = Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "description": str(exc)}

    return await asyncio.to_thread(_do)


def _esc(value) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _heading(text: str) -> str:
    return f"<b>{text}</b>"


def _note(text: str) -> str:
    return f"\n<i>{text}</i>"


def _kv_table(rows, headers=None) -> str:
    html = "\n<table>"
    if headers:
        html += f"<tr><th>{_esc(headers[0])}</th><th>{_esc(headers[1])}</th></tr>"
    for key, value in rows:
        html += f"<tr><td>{_esc(key)}</td><td>{value}</td></tr>"
    html += "</table>\n"
    return html


def _kb_dict(reply_markup):
    if not reply_markup:
        return None
    return {
        "inline_keyboard": [
            [
                {
                    "text": button.text,
                    **({"url": button.url} if button.url else {}),
                    **(
                        {"callback_data": button.callback_data}
                        if getattr(button, "callback_data", None)
                        else {}
                    ),
                }
                for button in row
            ]
            for row in reply_markup.inline_keyboard
        ]
    }


async def _rich_send(chat_id: int, html: str, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
    }
    kb = _kb_dict(reply_markup)
    if kb:
        payload["reply_markup"] = kb

    result = await _bot_api("sendRichMessage", payload)
    if result.get("ok"):
        return result

    return await bot.send_message(
        chat_id,
        html,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


async def _rich_edit(message: Message, html: str):
    payload = {
        "chat_id": message.chat.id,
        "message_id": message.id,
        "rich_message": {"html": html},
    }
    result = await _bot_api("editMessageText", payload)
    if result.get("ok"):
        return result

    try:
        return await message.edit_text(html, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await message.delete()
        except Exception:
            pass
        return await bot.send_message(
            message.chat.id,
            html,
            parse_mode=ParseMode.HTML,
        )


# ── Broadcast database ────────────────────────────────────────────────────────

async def _broadcast_collection():
    if db is None:
        return None
    return db["broadcast_chats"]


async def _track_chat(message: Message):
    """Keep the broadcast list populated without requiring another module."""
    if not message.chat:
        return

    collection = await _broadcast_collection()
    if collection is None:
        return

    chat_type = "private" if str(message.chat.type).lower().endswith("private") else "group"
    try:
        await collection.update_one(
            {"chat_id": int(message.chat.id)},
            {
                "$set": {
                    "chat_id": int(message.chat.id),
                    "type": chat_type,
                    "title": getattr(message.chat, "title", None) or "",
                }
            },
            upsert=True,
        )
    except Exception as exc:
        logger.warning("[Broadcast] chat tracking failed: %s", exc)


@bot.on_message(filters.all, group=99)
async def _broadcast_chat_tracker(_, message: Message):
    try:
        await _track_chat(message)
    except Exception:
        pass


async def get_broadcast_chats():
    collection = await _broadcast_collection()
    if collection is None:
        return []
    return await collection.find({}).to_list(length=None)


async def get_broadcast_count():
    collection = await _broadcast_collection()
    if collection is None:
        return {"total": 0, "groups": 0, "private": 0}

    total = await collection.count_documents({})
    groups = await collection.count_documents({"type": "group"})
    private = await collection.count_documents({"type": "private"})
    return {"total": total, "groups": groups, "private": private}


async def remove_broadcast_chat(chat_id: int):
    collection = await _broadcast_collection()
    if collection is None:
        return
    try:
        await collection.delete_one({"chat_id": int(chat_id)})
    except Exception:
        pass


# ── Flags ─────────────────────────────────────────────────────────────────────


def _parse_flags(raw: str) -> tuple[bool, bool, bool, bool]:
    pin = bool(re.search(r"-pin(?!loud)", raw))
    pinloud = "-pinloud" in raw
    nogroup = "-nogroup" in raw
    user = "-user" in raw
    return pin, pinloud, nogroup, user


def _strip_flags(text: str) -> str:
    for flag in ("-pinloud", "-nogroup", "-user", "-pin"):
        text = text.replace(flag, "")
    return text.strip()


# ── Send one message ──────────────────────────────────────────────────────────

async def _send(target_id: int, bm: Message, broadcast_type: str, text: str) -> Message:
    if broadcast_type == "text":
        return await bot.send_message(
            target_id,
            text,
            parse_mode=ParseMode.HTML,
        )

    try:
        return await bot.forward_messages(target_id, bm.chat.id, bm.id)
    except (ChatForwardsRestricted, MediaEmpty, MessageIdInvalid):
        return await bot.copy_message(target_id, bm.chat.id, bm.id)


# ── Main command ──────────────────────────────────────────────────────────────

@bot.on_message(
    filters.command(["broadcast", "gcast"])
    & filters.user(getattr(config, "OWNER_ID", 0))
)
async def broadcast_cmd(_, message: Message) -> None:
    global _IS_BROADCASTING

    async with _broadcast_lock:
        if _IS_BROADCASTING:
            await _rich_send(
                message.chat.id,
                _heading("❍ ᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ")
                + _note("ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ɪᴛ ᴛᴏ ғɪɴɪsʜ."),
            )
            return
        _IS_BROADCASTING = True

    try:
        await _run_broadcast(message)
    finally:
        _IS_BROADCASTING = False


async def _run_broadcast(message: Message) -> None:
    raw = message.text or ""
    raw_args = raw.split(None, 1)[1] if len(raw.split(None, 1)) > 1 else ""

    flag_pin, flag_pinloud, flag_nogroup, flag_user = _parse_flags(raw_args)
    clean_text = _strip_flags(raw_args)

    # Same Music Bot behavior: reply-to-message OR direct text.
    if message.reply_to_message:
        bm = message.reply_to_message
        broadcast_type = "reply"
    elif clean_text:
        bm = None
        broadcast_type = "text"
    else:
        await _rich_send(
            message.chat.id,
            _heading("❍ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴏʀ ᴘʀᴏᴠɪᴅᴇ ᴛᴇxᴛ")
            + _kv_table([
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
        await _rich_send(
            message.chat.id,
            _heading("❍ ɴᴏ ᴛᴀʀɢᴇᴛs ғᴏᴜɴᴅ ɪɴ ʙʀᴏᴀᴅᴄᴀsᴛ ʟɪsᴛ"),
        )
        return

    active_flags = " ".join(filter(None, [
        "-pin" if flag_pin else "",
        "-pinloud" if flag_pinloud else "",
        "-nogroup" if flag_nogroup else "",
        "-user" if flag_user else "",
    ])) or "none"

    pm = await _rich_send(
        message.chat.id,
        _heading("❍ ʙʀᴏᴀᴅᴄᴀsᴛ sᴛᴀʀᴛᴇᴅ")
        + _kv_table([
            ("ᴛᴏᴛᴀʟ", f"<code>{counts['total']}</code>"),
            ("ɢʀᴏᴜᴘs", f"<code>{len(groups)}</code>"),
            ("ᴜsᴇʀs", f"<code>{len(private)}</code>"),
            ("ᴛᴀʀɢᴇᴛs", f"<code>{targets}</code>"),
            ("ғʟᴀɢs", f"<code>{_esc(active_flags)}</code>"),
        ]),
    )

    # sendRichMessage returns a Telegram API result, not a Pyrogram Message.
    # For the completion edit, send a separate status message instead when needed.
    status_message = None
    try:
        if isinstance(pm, dict):
            status_message = None
        else:
            status_message = pm
    except Exception:
        status_message = None

    success_g = success_u = pinned = failed = 0

    if not flag_nogroup:
        for doc in groups:
            cid = int(doc["chat_id"])
            try:
                sent = await _send(cid, bm, broadcast_type, clean_text)
                success_g += 1

                if flag_pin or flag_pinloud:
                    try:
                        await bot.pin_chat_message(
                            cid,
                            sent.id,
                            disable_notification=not flag_pinloud,
                        )
                        pinned += 1
                    except ChatAdminRequired:
                        pass
                    except Exception:
                        pass

            except FloodWait as exc:
                wait = int(exc.value)
                if wait > 200:
                    failed += 1
                    continue
                await asyncio.sleep(wait)
                try:
                    sent = await _send(cid, bm, broadcast_type, clean_text)
                    success_g += 1
                    if flag_pin or flag_pinloud:
                        try:
                            await bot.pin_chat_message(
                                cid,
                                sent.id,
                                disable_notification=not flag_pinloud,
                            )
                            pinned += 1
                        except Exception:
                            pass
                except Exception:
                    failed += 1

            except (UserIsBlocked, ChatWriteForbidden, PeerIdInvalid):
                await remove_broadcast_chat(cid)
                failed += 1

            except Exception as exc:
                logger.warning("[Broadcast] group %s: %s", cid, exc)
                failed += 1

            await asyncio.sleep(0.4)

    if flag_user:
        for doc in private:
            uid = int(doc["chat_id"])
            try:
                await _send(uid, bm, broadcast_type, clean_text)
                success_u += 1

            except FloodWait as exc:
                wait = int(exc.value)
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

            except Exception as exc:
                logger.warning("[Broadcast] user %s: %s", uid, exc)
                failed += 1

            await asyncio.sleep(0.4)

    completed = (
        _heading("❍ ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ✅")
        + _kv_table([
            ("ɢʀᴏᴜᴘs", f"<code>{success_g}</code>"),
            ("ᴜsᴇʀs", f"<code>{success_u}</code>"),
            ("ᴘɪɴɴᴇᴅ", f"<code>{pinned}</code>"),
            ("ғᴀɪʟᴇᴅ", f"<code>{failed}</code>"),
        ])
    )

    # Keep the same final Music Bot style. Rich API can edit only if we have
    # a real message object; otherwise send the completion card normally.
    if isinstance(pm, dict) and pm.get("ok") and isinstance(pm.get("result"), dict):
        message_id = pm["result"].get("message_id")
        if message_id:
            edited = await _bot_api(
                "editMessageText",
                {
                    "chat_id": message.chat.id,
                    "message_id": message_id,
                    "rich_message": {"html": completed},
                },
            )
            if edited.get("ok"):
                return

    if status_message is not None:
        await _rich_edit(status_message, completed)
    else:
        await _rich_send(message.chat.id, completed)
