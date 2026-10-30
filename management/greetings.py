
# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/greetings.py — Welcome / Goodbye System
#  ChatMemberUpdated Support | Auto-Approve Removed
# --------------------------------------------------------------------------------

import asyncio
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode

from core.bot import app
from database.mongo import db


PREFIXES = ["/", "!", "."]
COLLECTION = "greetings"

DEFAULT_WELCOME = "👋 <b>Welcome {mention} to {chat}!</b>"
DEFAULT_GOODBYE = "👋 <b>{mention} has left {chat}.</b>"

CAPTION_LIMIT = 900


# ─── Database Helpers ─────────────────────────────────────────────────────────

def _col():
    return db[COLLECTION] if db is not None else None


def _name(user):
    name = (
        getattr(user, "first_name", None)
        or getattr(user, "username", None)
        or str(user.id)
    )
    return html.escape(name.strip())


def _mention(user):
    return f'<a href="tg://user?id={int(user.id)}">{_name(user)}</a>'


def _is_group_chat(chat):
    return bool(
        chat and chat.type in (
            ChatType.GROUP,
            ChatType.SUPERGROUP
        )
    )


def _is_inside_chat(member):
    if not member:
        return False

    status = member.status

    if status in (
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    ):
        return True

    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))

    return False


async def _is_admin(message):
    if not _is_group_chat(message.chat) or not message.from_user:
        return False

    try:
        member = await app.get_chat_member(
            message.chat.id,
            message.from_user.id
        )

        return member.status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR
        )

    except Exception as e:
        print(f"[GREETINGS] Admin check error: {e}", flush=True)
        return False


async def _permission(message):
    if not await _is_admin(message):
        await message.reply_text(
            "❌ <b>You don't have permission to use this command.</b>",
            parse_mode=ParseMode.HTML
        )
        return False

    return True


async def _get(chat_id):
    c = _col()

    default = {
        "chat_id": int(chat_id),
        "welcome": True,
        "goodbye": True,
        "cleanwelcome": False,
        "welcome_text": DEFAULT_WELCOME,
        "goodbye_text": DEFAULT_GOODBYE,
        "old_welcome_ids": [],
        "welcome_media": None,
        "goodbye_media": None,
    }

    if c is None:
        return default

    doc = await c.find_one({"chat_id": int(chat_id)})

    if not doc:
        await c.update_one(
            {"chat_id": int(chat_id)},
            {"$setOnInsert": default},
            upsert=True
        )
        return default

    return {**default, **doc}


async def _update(chat_id, **values):
    c = _col()

    if c is None:
        return

    await c.update_one(
        {"chat_id": int(chat_id)},
        {"$set": values},
        upsert=True
    )

    print(
        f"[GREETINGS DEBUG] DB Updated for {chat_id}: {values}",
        flush=True
    )


# ─── Text Helpers ─────────────────────────────────────────────────────────────

def _fill(text, user, chat):
    values = {
        "{name}": _name(user),
        "{mention}": _mention(user),
        "{id}": str(user.id),
        "{username}": (
            f"@{html.escape(user.username)}"
            if user.username else ""
        ),
        "{chat}": html.escape(
            getattr(chat, "title", None) or "Group"
        ),
        "{chat_id}": str(chat.id),
    }

    for key, value in values.items():
        text = text.replace(key, value)

    return text.replace("\r\n", "\n")


# ─── Media Extraction ─────────────────────────────────────────────────────────

def _extract_media(replied):
    if not replied:
        return None, None

    if replied.photo:
        return "photo", replied.photo.file_id

    if replied.video:
        return "video", replied.video.file_id

    if replied.animation:
        return "gif", replied.animation.file_id

    if replied.document:
        return "document", replied.document.file_id

    if replied.sticker:
        return "sticker", replied.sticker.file_id

    return None, None


# ─── Safe Message Sender ──────────────────────────────────────────────────────

async def _send_with_media(chat_id, reply_to_id, text, media):

    print(
        f"[GREETINGS DEBUG] Sending message in {chat_id}",
        flush=True
    )

    reply_args = {}

    if reply_to_id:
        reply_args["reply_to_message_id"] = int(reply_to_id)

    async def _safe_send(func, **kwargs):
        try:
            result = await func(**kwargs)

            print(
                "[GREETINGS DEBUG] Message sent successfully!",
                flush=True
            )

            return result

        except Exception as e:
            print(
                f"[GREETINGS DEBUG] Send failed: "
                f"{type(e).__name__}: {e}",
                flush=True
            )

            if "parse entities" in str(e).lower():
                kwargs.pop("parse_mode", None)

                for key in ("text", "caption"):
                    if key in kwargs and kwargs[key]:
                        clean = re.sub(
                            r"<[^>]+>",
                            "",
                            kwargs[key]
                        )
                        kwargs[key] = html.unescape(clean)

                try:
                    return await func(**kwargs)

                except Exception as e2:
                    print(
                        f"[GREETINGS DEBUG] Fallback failed: {e2}",
                        flush=True
                    )

            return None

    try:

        if not media:
            return await _safe_send(
                app.send_message,
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                **reply_args
            )

        mtype = media.get("type")
        fid = media.get("file_id")

        if not fid:
            return await _safe_send(
                app.send_message,
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                **reply_args
            )

        methods = {
            "photo": (app.send_photo, "photo"),
            "video": (app.send_video, "video"),
            "gif": (app.send_animation, "animation"),
            "document": (app.send_document, "document"),
            "sticker": (app.send_sticker, "sticker"),
        }

        if mtype not in methods:
            return await _safe_send(
                app.send_message,
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                **reply_args
            )

        func, argument = methods[mtype]

        media_args = {
            "chat_id": chat_id,
            argument: fid,
            **reply_args
        }

        if mtype == "sticker":
            await _safe_send(func, **media_args)

            return await _safe_send(
                app.send_message,
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                **reply_args
            )

        if len(text) > CAPTION_LIMIT:
            await _safe_send(func, **media_args)

            return await _safe_send(
                app.send_message,
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                **reply_args
            )

        media_args["caption"] = text
        media_args["parse_mode"] = ParseMode.HTML

        return await _safe_send(func, **media_args)

    except Exception as e:
        print(
            f"[GREETINGS DEBUG] Outer error: "
            f"{type(e).__name__}: {e}",
            flush=True
        )
        return None


# ─── Cleanup Helpers ──────────────────────────────────────────────────────────

async def _clean_old(chat_id, exclude=None):
    c = _col()

    if c is None:
        return

    doc = await c.find_one({"chat_id": int(chat_id)})

    ids = list(doc.get("old_welcome_ids", [])) if doc else []
    kept = []

    for mid in ids:

        if exclude is not None and int(mid) == int(exclude):
            kept.append(mid)
            continue

        try:
            await app.delete_messages(
                chat_id,
                int(mid)
            )

        except Exception:
            pass

    await c.update_one(
        {"chat_id": int(chat_id)},
        {"$set": {"old_welcome_ids": kept}},
        upsert=True
    )


async def _remember_welcome(chat_id, message_id):
    c = _col()

    if c is None:
        return

    await c.update_one(
        {"chat_id": int(chat_id)},
        {
            "$push": {
                "old_welcome_ids": {
                    "$each": [int(message_id)],
                    "$slice": -20
                }
            }
        },
        upsert=True
    )


async def _expire_welcome(chat_id, message_id):
    await asyncio.sleep(300)

    try:
        doc = await _get(chat_id)

        if not doc.get("cleanwelcome"):
            return

        await app.delete_messages(
            chat_id,
            int(message_id)
        )

        c = _col()

        if c is not None:
            await c.update_one(
                {"chat_id": int(chat_id)},
                {
                    "$pull": {
                        "old_welcome_ids": int(message_id)
                    }
                }
            )

    except Exception as e:
        print(
            f"[GREETINGS] Expiry error: {e}",
            flush=True
        )


# ─── Welcome Sender ───────────────────────────────────────────────────────────

async def _send_welcome(chat, user):

    doc = await _get(chat.id)

    if not doc.get("welcome", True):
        print(
            f"[GREETINGS] Welcome disabled in {chat.id}",
            flush=True
        )
        return

    if doc.get("cleanwelcome"):
        await _clean_old(chat.id)

    text = _fill(
        doc.get("welcome_text") or DEFAULT_WELCOME,
        user,
        chat
    )

    sent = await _send_with_media(
        chat.id,
        None,
        text,
        doc.get("welcome_media")
    )

    if sent:

        await _remember_welcome(
            chat.id,
            sent.id
        )

        if doc.get("cleanwelcome"):
            asyncio.create_task(
                _expire_welcome(
                    chat.id,
                    sent.id
                )
            )

        print(
            f"[GREETINGS DEBUG] WELCOME SUCCESS: {user.id}",
            flush=True
        )

    else:
        print(
            f"[GREETINGS DEBUG] WELCOME SEND FAILED: {user.id}",
            flush=True
        )


# ─── Welcome Handler (Chat Member Update) ─────────────────────────────────────

@app.on_chat_member_updated()
async def welcome_members(_, update):

    try:

        chat = update.chat
        old_member = update.old_chat_member
        new_member = update.new_chat_member

        user = new_member.user if new_member else None

        print(
            f"[GREETINGS DEBUG] CHAT MEMBER UPDATE: "
            f"chat={chat.id}, "
            f"user={getattr(user, 'id', None)}, "
            f"old={getattr(old_member, 'status', None)}, "
            f"new={getattr(new_member, 'status', None)}",
            flush=True
        )

        if not _is_group_chat(chat):
            return

        # Ignore users who were already members.
        if _is_inside_chat(old_member):
            return

        # Process only actual membership transitions.
        if not _is_inside_chat(new_member):
            return

        if not user:
            return

        if getattr(user, "is_bot", False):
            return

        await _send_welcome(chat, user)

    except Exception as e:

        print(
            f"[GREETINGS DEBUG] CHAT MEMBER ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ─── Goodbye Handler (Chat Member Update) ─────────────────────────────────────

@app.on_chat_member_updated()
async def goodbye_members(_, update):

    try:

        chat = update.chat
        old_member = update.old_chat_member
        new_member = update.new_chat_member

        user = new_member.user if new_member else None

        if not _is_group_chat(chat):
            return

        # Ignore members who are still inside the group.
        if not _is_inside_chat(old_member):
            return

        if _is_inside_chat(new_member):
            return

        if not user:
            return

        if getattr(user, "is_bot", False):
            return

        doc = await _get(chat.id)

        if not doc.get("goodbye", True):
            return

        text = _fill(
            doc.get("goodbye_text") or DEFAULT_GOODBYE,
            user,
            chat
        )

        await _send_with_media(
            chat.id,
            None,
            text,
            doc.get("goodbye_media")
        )

        print(
            f"[GREETINGS DEBUG] GOODBYE SUCCESS: {user.id}",
            flush=True
        )

    except Exception as e:

        print(
            f"[GREETINGS DEBUG] GOODBYE ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ─── Settings Commands ────────────────────────────────────────────────────────

@app.on_message(
    filters.group
    & filters.incoming
    & filters.command(
        [
            "welcome",
            "goodbye",
            "setwelcome",
            "resetwelcome",
            "setgoodbye",
            "resetgoodbye",
            "cleanwelcome",
        ],
        PREFIXES
    )
)
async def greetings_settings(_, message):

    if not await _permission(message):
        return

    command = (message.command[0] or "").lower()

    full = message.text or message.caption or ""
    parts = full.split(maxsplit=1)

    args = parts[1].strip() if len(parts) > 1 else ""

    print(
        f"[GREETINGS DEBUG] Command '{command}' "
        f"received in {message.chat.id}. Args: {args}",
        flush=True
    )

    if command in (
        "welcome",
        "goodbye",
        "cleanwelcome"
    ):

        if not args:

            doc = await _get(message.chat.id)

            state = "ON" if doc.get(command) else "OFF"

            return await message.reply_text(
                f"✦ <b>{command.title()}:</b> {state}",
                parse_mode=ParseMode.HTML
            )

        value = args.lower().strip()

        if value not in ("yes", "no", "on", "off"):
            return await message.reply_text(
                "❌ Use <code>yes</code>, <code>no</code>, "
                "<code>on</code> or <code>off</code>.",
                parse_mode=ParseMode.HTML
            )

        enabled = value in ("yes", "on")

        await _update(
            message.chat.id,
            **{command: enabled}
        )

        return await message.reply_text(
            f"✓ <b>{command.title()} "
            f"{'enabled' if enabled else 'disabled'}.</b>",
            parse_mode=ParseMode.HTML
        )

    if command == "setwelcome":

        mtype, fid = _extract_media(
            message.reply_to_message
        )

        if mtype:

            caption = (
                args
                or message.reply_to_message.caption
                or DEFAULT_WELCOME
            )

            await _update(
                message.chat.id,
                welcome_text=caption,
                welcome_media={
                    "type": mtype,
                    "file_id": fid
                }
            )

            return await message.reply_text(
                f"✓ <b>Welcome media set ({mtype}).</b>",
                parse_mode=ParseMode.HTML
            )

        if not args:
            return await message.reply_text(
                "❌ <b>Usage:</b>\n"
                "<code>.setwelcome Hello {mention}</code>",
                parse_mode=ParseMode.HTML
            )

        await _update(
            message.chat.id,
            welcome_text=args,
            welcome_media=None
        )

        return await message.reply_text(
            "✓ <b>Welcome message updated.</b>",
            parse_mode=ParseMode.HTML
        )

    if command == "resetwelcome":

        await _update(
            message.chat.id,
            welcome_text=DEFAULT_WELCOME,
            welcome_media=None
        )

        return await message.reply_text(
            "✓ <b>Welcome message reset.</b>",
            parse_mode=ParseMode.HTML
        )

    if command == "setgoodbye":

        mtype, fid = _extract_media(
            message.reply_to_message
        )

        if mtype:

            caption = (
                args
                or message.reply_to_message.caption
                or DEFAULT_GOODBYE
            )

            await _update(
                message.chat.id,
                goodbye_text=caption,
                goodbye_media={
                    "type": mtype,
                    "file_id": fid
                }
            )

            return await message.reply_text(
                f"✓ <b>Goodbye media set ({mtype}).</b>",
                parse_mode=ParseMode.HTML
            )

        if not args:
            return await message.reply_text(
                "❌ <b>Usage:</b>\n"
                "<code>.setgoodbye Goodbye {mention}</code>",
                parse_mode=ParseMode.HTML
            )

        await _update(
            message.chat.id,
            goodbye_text=args,
            goodbye_media=None
        )

        return await message.reply_text(
            "✓ <b>Goodbye message updated.</b>",
            parse_mode=ParseMode.HTML
        )

    if command == "resetgoodbye":

        await _update(
            message.chat.id,
            goodbye_text=DEFAULT_GOODBYE,
            goodbye_media=None
        )

        return await message.reply_text(
            "✓ <b>Goodbye message reset.</b>",
            parse_mode=ParseMode.HTML
        )


print(
    "[GREETINGS] Welcome / Goodbye system loaded.",
    flush=True
)
