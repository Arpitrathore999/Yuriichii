# --------------------------------------------------------------------------------
# Elara © 2026
# handlers/pin.py — GC pin management
# --------------------------------------------------------------------------------

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import RPCError

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]


async def _is_group(message):
    return bool(
        message.chat
        and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    )


async def _is_admin(message):
    if not message.from_user or not await _is_group(message):
        return False
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
        )
    except Exception:
        return False


async def _has_pin_right(message):
    """Owner always has it; otherwise honor Elara's custom pin right first,
    then fall back to Telegram's actual can_pin_messages privilege."""
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
                rights = set(doc.get("rights", []))
                return "pin" in rights

        privileges = getattr(member, "privileges", None)
        return bool(privileges and getattr(privileges, "can_pin_messages", False))
    except Exception:
        return False


async def _bot_can_pin(message):
    try:
        member = await app.get_chat_member(message.chat.id, "me")
        if member.status == ChatMemberStatus.OWNER:
            return True
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False
        privileges = getattr(member, "privileges", None)
        return bool(privileges and getattr(privileges, "can_pin_messages", False))
    except Exception:
        return False


async def _guard(message):
    if not await _is_group(message):
        await message.reply("❌ <b>Tʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ɢʀᴏᴜᴘs.</b>")
        return False
    if not await _has_pin_right(message):
        await message.reply("❌ <b>Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴛʜᴇ ᴘɪɴ ʀɪɢʜᴛ.</b>")
        return False
    if not await _bot_can_pin(message):
        await message.reply("❌ <b>I ɴᴇᴇᴅ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴘɪɴ ᴍᴇssᴀɢᴇs.</b>")
        return False
    return True


def _mention(user):
    if not user:
        return "Uɴᴋɴᴏᴡɴ"
    name = (user.first_name or "Uɴᴋɴᴏᴡɴ").strip()
    return f'<a href="tg://user?id={user.id}">{name}</a>'


@app.on_message(filters.command("pinned", prefixes=PREFIXES) & filters.group)
async def pinned(_, message):
    try:
        chat = await app.get_chat(message.chat.id)
        pinned_message = getattr(chat, "pinned_message", None)
        if not pinned_message:
            return await message.reply("📌 <b>Nᴏ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ ғᴏᴜɴᴅ.</b>")

        link = getattr(pinned_message, "link", None)
        if link:
            return await message.reply(
                f'📌 <b>Cᴜʀʀᴇɴᴛ Pɪɴɴᴇᴅ Mᴇssᴀɢᴇ</b>\n\n<a href="{link}">Oᴘᴇɴ Mᴇssᴀɢᴇ</a>'
            )
        return await message.reply(
            f"📌 <b>Cᴜʀʀᴇɴᴛ Pɪɴɴᴇᴅ Mᴇssᴀɢᴇ:</b> <code>{pinned_message.id}</code>"
        )
    except Exception as e:
        print(f"[PINNED] {type(e).__name__}: {e}", flush=True)
        await message.reply("❌ <b>Fᴀɪʟᴇᴅ ᴛᴏ ɢᴇᴛ ᴛʜᴇ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ.</b>")


@app.on_message(filters.command("pin", prefixes=PREFIXES) & filters.group)
async def pin(_, message):
    if not await _guard(message):
        return

    reply = message.reply_to_message
    if not reply:
        return await message.reply("❌ <b>Rᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴍᴇssᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴘɪɴ.</b>")

    args = [str(x).lower() for x in (message.command or [])[1:]]
    notify = any(x in {"loud", "notify"} for x in args)

    try:
        await app.pin_chat_message(
            message.chat.id,
            reply.id,
            disable_notification=not notify,
        )
        suffix = " 🔔" if notify else ""
        await message.reply(f"📌 <b>Pɪɴɴᴇᴅ{suffix}.</b>")
    except RPCError as e:
        print(f"[PIN] {type(e).__name__}: {e}", flush=True)
        await message.reply("❌ <b>Fᴀɪʟᴇᴅ ᴛᴏ ᴘɪɴ ᴛʜɪs ᴍᴇssᴀɢᴇ.</b>")


@app.on_message(filters.command("unpin", prefixes=PREFIXES) & filters.group)
async def unpin(_, message):
    if not await _guard(message):
        return

    try:
        if message.reply_to_message:
            await app.unpin_chat_message(message.chat.id, message.reply_to_message.id)
        else:
            await app.unpin_chat_message(message.chat.id)
        await message.reply("📌 <b>Uɴᴘɪɴɴᴇᴅ.</b>")
    except RPCError as e:
        print(f"[UNPIN] {type(e).__name__}: {e}", flush=True)
        await message.reply("❌ <b>Nᴏ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ ᴄᴏᴜʟᴅ ʙᴇ ᴜɴᴘɪɴɴᴇᴅ.</b>")


@app.on_message(filters.command("unpinall", prefixes=PREFIXES) & filters.group)
async def unpin_all(_, message):
    if not await _guard(message):
        return

    try:
        await app.unpin_all_chat_messages(message.chat.id)
        await message.reply("📌 <b>Aʟʟ Pɪɴɴᴇᴅ Mᴇssᴀɢᴇs Uɴᴘɪɴɴᴇᴅ.</b>")
    except RPCError as e:
        print(f"[UNPINALL] {type(e).__name__}: {e}", flush=True)
        await message.reply("❌ <b>Fᴀɪʟᴇᴅ ᴛᴏ ᴜɴᴘɪɴ ᴛʜᴇ ᴍᴇssᴀɢᴇs.</b>")
