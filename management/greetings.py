# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/greetings.py — Welcome / Goodbye (Debug Version)
# --------------------------------------------------------------------------------

import asyncio
import html
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import ReplyParameters, ChatJoinRequest
from pyrogram.errors import ChatAdminRequired, UserNotParticipant

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
COLLECTION = "greetings"

DEFAULT_WELCOME = "👋 <b>Welcome {mention} to {chat}!</b>"
DEFAULT_GOODBYE = "👋 <b>{mention} has left {chat}.</b>"

CAPTION_LIMIT = 900


# ─── DB helpers ───────────────────────────────────────────────────────────────
def _col():
    return db[COLLECTION] if db is not None else None


def _name(user):
    name = (getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)).strip()
    return html.escape(name)


def _mention(user):
    return f'<a href="tg://user?id={int(user.id)}">{_name(user)}</a>'


def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _is_admin(message):
    if not _is_group(message) or not message.from_user:
        return False
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _permission(message):
    if not await _is_admin(message):
        await message.reply("❌ <b>You don't have permission to use this command.</b>")
        return False
    return True


async def _get(chat_id):
    c = _col()
    default = {
        "chat_id": int(chat_id), "welcome": True, "goodbye": True,
        "cleanwelcome": False, "autoapprove": False,
        "welcome_text": DEFAULT_WELCOME,
        "goodbye_text": DEFAULT_GOODBYE, "old_welcome_ids": [],
        "welcome_media": None, "goodbye_media": None,
    }
    if c is None:
        return default
    doc = await c.find_one({"chat_id": int(chat_id)})
    if not doc:
        await c.update_one({"chat_id": int(chat_id)}, {"$setOnInsert": default}, upsert=True)
        return default
    if "autoapprove" not in doc:
        doc["autoapprove"] = False
    return doc


async def _update(chat_id, **values):
    c = _col()
    if c is None:
        return
    await c.update_one({"chat_id": int(chat_id)}, {"$set": values}, upsert=True)
    print(f"[GREETINGS DEBUG] DB Updated for {chat_id}: {values}", flush=True)


# ─── Text / media helpers ─────────────────────────────────────────────────────
def _fill(text, user, chat):
    values = {
        "{name}": _name(user),
        "{mention}": _mention(user),
        "{id}": str(user.id),
        "{username}": f"@{user.username}" if user.username else "",
        "{chat}": html.escape(getattr(chat, "title", "Group") or "Group"),
        "{chat_id}": str(chat.id),
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return text.replace("\r\n", "\n")


async def _send_with_media(chat_id, reply_to_id, text, media):
    print(f"[GREETINGS DEBUG] Attempting to send message in {chat_id}...", flush=True)
    try:
        reply_params = ReplyParameters(message_id=reply_to_id) if reply_to_id else None
    except Exception:
        reply_params = None

    async def _safe_send(func, **kwargs):
        try:
            res = await func(**kwargs)
            print(f"[GREETINGS DEBUG] ✅ Message sent successfully!", flush=True)
            return res
        except Exception as e:
            err = str(e).lower()
            print(f"[GREETINGS DEBUG] ❌ Send failed: {type(e).__name__}: {e}", flush=True)
            if "can't parse entities" in err or "bad request" in err:
                kwargs.pop("parse_mode", None)
                import re
                if "caption" in kwargs:
                    kwargs["caption"] = re.sub(r'<[^>]+>', '', kwargs["caption"])
                elif "text" in kwargs:
                    kwargs["text"] = re.sub(r'<[^>]+>', '', kwargs["text"])
                try:
                    return await func(**kwargs)
                except Exception as e2:
                    print(f"[GREETINGS DEBUG] ❌ Fallback failed: {type(e2).__name__}: {e2}", flush=True)
                    return None
            return None

    try:
        if not media:
            return await _safe_send(
                app.send_message,
                chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params
            )

        mtype = media.get("type")
        fid = media.get("file_id")
        long_text = len(text) > CAPTION_LIMIT

        if mtype == "photo":
            if long_text:
                await _safe_send(app.send_photo, chat_id=chat_id, photo=fid, reply_parameters=reply_params)
                return await _safe_send(app.send_message, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)
            return await _safe_send(app.send_photo, chat_id=chat_id, photo=fid, caption=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)

        if mtype == "video":
            if long_text:
                await _safe_send(app.send_video, chat_id=chat_id, video=fid, reply_parameters=reply_params)
                return await _safe_send(app.send_message, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)
            return await _safe_send(app.send_video, chat_id=chat_id, video=fid, caption=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)

        if mtype == "gif":
            if long_text:
                await _safe_send(app.send_animation, chat_id=chat_id, animation=fid, reply_parameters=reply_params)
                return await _safe_send(app.send_message, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)
            return await _safe_send(app.send_animation, chat_id=chat_id, animation=fid, caption=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)

        if mtype == "document":
            if long_text:
                await _safe_send(app.send_document, chat_id=chat_id, document=fid, reply_parameters=reply_params)
                return await _safe_send(app.send_message, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)
            return await _safe_send(app.send_document, chat_id=chat_id, document=fid, caption=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)

        if mtype == "sticker":
            await _safe_send(app.send_sticker, chat_id=chat_id, sticker=fid, reply_parameters=reply_params)
            return await _safe_send(app.send_message, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)

        return await _safe_send(app.send_message, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_parameters=reply_params)
    except Exception as e:
        print(f"[GREETINGS DEBUG] ❌ Outer error: {type(e).__name__}: {e}", flush=True)
        return None


# ─── Settings commands ────────────────────────────────────────────────────────
@app.on_message(
    filters.group & filters.incoming & filters.command(
        ["welcome", "goodbye", "setwelcome", "resetwelcome",
         "setgoodbye", "resetgoodbye", "cleanwelcome", "autoapprove"], PREFIXES,
    )
)
async def greetings_settings(_, message):
    if not await _permission(message): return

    command = (message.command[0] or "").lower()
    full = message.text or message.caption or ""
    parts = full.split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""

    print(f"[GREETINGS DEBUG] Command '{command}' received in {message.chat.id}. Args: {args}", flush=True)

    if command in ("welcome", "goodbye", "cleanwelcome", "autoapprove"):
        if not args:
            doc = await _get(message.chat.id)
            state = "ON" if doc.get(command) else "OFF"
            label = "Auto-Approve" if command == "autoapprove" else command.title()
            return await message.reply(f"✦ <b>{label}:</b> {state}")

        value = args.lower().strip()
        if value not in ("yes", "no", "on", "off"):
            return await message.reply("❌ Use <code>yes</code>, <code>no</code>, <code>on</code> or <code>off</code>.")

        enabled = value in ("yes", "on")
        await _update(message.chat.id, **{command: enabled})
        
        label = "Auto-Approve" if command == "autoapprove" else command.title()
        return await message.reply(f"✓ <b>{label} {'enabled' if enabled else 'disabled'}.</b>")

    # Baaki settings (setwelcome, setgoodbye) same rahenge...
    if command == "setwelcome":
        mtype, fid = _extract_media(message.reply_to_message)
        if mtype:
            caption = args if args else (message.reply_to_message.caption or DEFAULT_WELCOME)
            await _update(message.chat.id, welcome_text=caption, welcome_media={"type": mtype, "file_id": fid})
            return await message.reply(f"✓ <b>Welcome media set</b> ({mtype}).")
        if not args:
            return await message.reply("❌ <b>Uꜱᴀɢᴇ:</b>\n• <code>.setwelcome &lt;text&gt;</code>")
        await _update(message.chat.id, welcome_text=args, welcome_media=None)
        return await message.reply("✓ <b>Welcome message updated.</b>")

    if command == "resetwelcome":
        await _update(message.chat.id, welcome_text=DEFAULT_WELCOME, welcome_media=None)
        return await message.reply("✓ <b>Welcome message reset.</b>")

    if command == "setgoodbye":
        mtype, fid = _extract_media(message.reply_to_message)
        if mtype:
            caption = args if args else (message.reply_to_message.caption or DEFAULT_GOODBYE)
            await _update(message.chat.id, goodbye_text=caption, goodbye_media={"type": mtype, "file_id": fid})
            return await message.reply(f"✓ <b>Goodbye media set</b> ({mtype}).")
        if not args:
            return await message.reply("❌ <b>Uꜱᴀɢᴇ:</b>\n• <code>.setgoodbye &lt;text&gt;</code>")
        await _update(message.chat.id, goodbye_text=args, goodbye_media=None)
        return await message.reply("✓ <b>Goodbye message updated.</b>")

    if command == "resetgoodbye":
        await _update(message.chat.id, goodbye_text=DEFAULT_GOODBYE, goodbye_media=None)
        return await message.reply("✓ <b>Goodbye message reset.</b>")


# ─── Welcome Handler (Normal Join) ────────────────────────────────────────────
@app.on_message(filters.group & filters.new_chat_members, group=-5)
async def welcome_members(_, message):
    print(f"[GREETINGS DEBUG] 🚨 new_chat_members event in {message.chat.id}!", flush=True)
    try:
        doc = await _get(message.chat.id)
        print(f"[GREETINGS DEBUG] DB Welcome toggle: {doc.get('welcome')}", flush=True)
        
        if not doc.get("welcome", True):
            return

        if doc.get("cleanwelcome"):
            await _clean_old(message.chat.id)

        new_users = []
        if message.new_chat_members:
            for u in message.new_chat_members:
                if u and not getattr(u, "is_bot", False) and getattr(u, "id", None):
                    new_users.append(u)
        
        print(f"[GREETINGS DEBUG] Valid users found: {len(new_users)}", flush=True)
        if not new_users:
            return

        mentions = " , ".join(_mention(u) for u in new_users)
        text = _fill(doc.get("welcome_text") or DEFAULT_WELCOME, new_users[0], message.chat)
        
        if len(new_users) > 1:
            text = f"👋 Welcome {mentions} to <b>{html.escape(message.chat.title)}</b>!\n\n" + text

        media = doc.get("welcome_media")
        sent = await _send_with_media(message.chat.id, message.id, text, media)
        
        if sent:
            await _remember_welcome(message.chat.id, sent.id)
            if doc.get("cleanwelcome"):
                asyncio.create_task(_expire_welcome(message.chat.id, sent.id))
    except Exception as e:
        print(f"[GREETINGS DEBUG] ❌ Error in welcome_members: {type(e).__name__}: {e}", flush=True)


# ─── ✅ Join Request Handler (Approval System) ─────────────────────────────────
@app.on_chat_join_request(filters.group)
async def welcome_join_request(_, request: ChatJoinRequest):
    print(f"[GREETINGS DEBUG] 🚨 Join Request received for {request.from_user.id} in {request.chat.id}!", flush=True)
    try:
        doc = await _get(request.chat.id)
        autoapprove = doc.get("autoapprove", False)
        user = request.from_user

        if not user or getattr(user, "is_bot", False):
            return

        print(f"[GREETINGS DEBUG] Auto-approve setting is: {autoapprove}", flush=True)

        if autoapprove:
            try:
                await app.approve_chat_join_request(request.chat.id, user.id)
                print(f"[GREETINGS DEBUG] ✅ Auto-approved {user.id}", flush=True)
            except Exception as e:
                print(f"[GREETINGS DEBUG] ❌ Auto-approve failed: {type(e).__name__}: {e}", flush=True)
        else:
            print(f"[GREETINGS DEBUG] Auto-approve is OFF. Sending DM...", flush=True)
            try:
                await app.send_message(
                    user.id,
                    f"⏳ <b>Your join request for {html.escape(request.chat.title)} has been sent.</b>\n\n"
                    f"Please wait for an admin to approve it.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print(f"[GREETINGS DEBUG] ❌ Could not send DM to user (maybe blocked bot): {e}", flush=True)

    except Exception as e:
        print(f"[GREETINGS DEBUG] ❌ JOIN REQUEST ERROR: {type(e).__name__}: {e}", flush=True)


# ─── Cleanup ──────────────────────────────────────────────────────────────────
async def _clean_old(chat_id, exclude=None):
    c = _col()
    if c is None: return
    doc = await c.find_one({"chat_id": int(chat_id)})
    ids = list(doc.get("old_welcome_ids", [])) if doc else []
    kept = []
    for mid in ids:
        if exclude is not None and int(mid) == int(exclude):
            kept.append(mid)
            continue
        try:
            await app.delete_messages(chat_id, int(mid))
        except Exception:
            pass
    await c.update_one({"chat_id": int(chat_id)}, {"$set": {"old_welcome_ids": kept}})

async def _remember_welcome(chat_id, message_id):
    c = _col()
    if c is None: return
    await c.update_one(
        {"chat_id": int(chat_id)},
        {"$push": {"old_welcome_ids": {"$each": [int(message_id)], "$slice": -20}}},
        upsert=True,
    )

async def _expire_welcome(chat_id, message_id):
    await asyncio.sleep(300)
    try:
        doc = await _get(chat_id)
        if not doc.get("cleanwelcome"): return
        await app.delete_messages(chat_id, int(message_id))
        c = _col()
        if c is not None:
            await c.update_one({"chat_id": int(chat_id)}, {"$pull": {"old_welcome_ids": int(message_id)}})
    except Exception:
        pass
