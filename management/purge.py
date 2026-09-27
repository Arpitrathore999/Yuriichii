# --------------------------------------------------------------------------------
# Elara © 2026
# handlers/purge.py — GC message purge management
# --------------------------------------------------------------------------------

import asyncio

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import RPCError

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
MAX_PURGE = 1000


def _col(name):
    return db[name] if db is not None else None


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


async def _has_delete_right(message):
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
                return "delete" in set(doc.get("rights", []))
        privileges = getattr(member, "privileges", None)
        return bool(privileges and getattr(privileges, "can_delete_messages", False))
    except Exception:
        return False


async def _bot_can_delete(message):
    try:
        me = await app.get_chat_member(message.chat.id, "me")
        return me.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _guard(message):
    if not await _is_group(message):
        await message.reply("❌ <b>This command can only be used in groups.</b>")
        return False
    if not await _has_delete_right(message):
        await message.reply("❌ <b>You don't have permission to use this command.</b>")
        return False
    if not await _bot_can_delete(message):
        await message.reply("❌ <b>I need delete-message admin permission to purge messages.</b>")
        return False
    return True


async def _delete_ids(chat_id, ids):
    ids = [int(x) for x in ids if x]
    if not ids:
        return 0
    deleted = 0
    # Telegram/Pyrogram handles message deletion in batches; keep chunks small.
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            result = await app.delete_messages(chat_id, chunk)
            if isinstance(result, list):
                deleted += sum(bool(x) for x in result)
            else:
                deleted += len(chunk)
        except Exception:
            # Try one-by-one for partial failures (old/undeletable messages).
            for mid in chunk:
                try:
                    await app.delete_messages(chat_id, mid)
                    deleted += 1
                except Exception:
                    pass
    return deleted


async def _messages_between(chat_id, start_id, end_id=None, limit=MAX_PURGE):
    """Return message IDs newer than start_id and, if supplied, not newer than end_id."""
    if start_id is None:
        return []
    upper = int(end_id) if end_id is not None else None
    ids = []
    async for msg in app.get_chat_history(chat_id, limit=limit):
        if not msg or not msg.id:
            continue
        mid = int(msg.id)
        if mid <= int(start_id):
            break
        if upper is not None and mid > upper:
            continue
        ids.append(mid)
        if upper is not None and mid <= int(start_id):
            break
        if len(ids) >= limit:
            break
    return sorted(set(ids))


async def _get_marker(chat_id):
    col = _col("purge_markers")
    if col is None:
        return None
    doc = await col.find_one({"chat_id": int(chat_id)})
    return int(doc["message_id"]) if doc and doc.get("message_id") else None


async def _set_marker(chat_id, message_id, user_id):
    col = _col("purge_markers")
    if col is None:
        return False
    await col.update_one(
        {"chat_id": int(chat_id)},
        {"$set": {"chat_id": int(chat_id), "message_id": int(message_id), "set_by": int(user_id)}},
        upsert=True,
    )
    return True


async def _clear_marker(chat_id):
    col = _col("purge_markers")
    if col is not None:
        await col.delete_one({"chat_id": int(chat_id)})


async def _confirmation(message, count, silent=False):
    if silent:
        try:
            await message.delete()
        except Exception:
            pass
        return
    try:
        await message.delete()
    except Exception:
        pass
    if count:
        sent = await message.reply(f"🗑️ <b>Pᴜʀɢᴇᴅ {count} ᴍᴇssᴀɢᴇs.</b>")
        await asyncio.sleep(2)
        try:
            await sent.delete()
        except Exception:
            pass


async def _purge(_, message):
    if not await _guard(message):
        return
    reply = message.reply_to_message
    if not reply:
        return await message.reply("❌ <b>Reply to the first message you want to purge from.</b>")

    args = message.command or []
    count_arg = None
    if len(args) >= 2:
        try:
            count_arg = int(args[1])
        except ValueError:
            return await message.reply("❌ <b>Usage:</b> <code>/purge</code> or <code>/purge 50</code>")
        if count_arg <= 0 or count_arg > MAX_PURGE:
            return await message.reply(f"❌ <b>Choose a number between 1 and {MAX_PURGE}.</b>")

    if count_arg is not None:
        # X messages after the replied-to message.
        ids = await _messages_between(message.chat.id, reply.id, limit=count_arg)
        ids = ids[:count_arg]
    else:
        # Everything after the replied-to message up to the current command.
        ids = await _messages_between(message.chat.id, reply.id, end_id=message.id, limit=MAX_PURGE)

    # Include the command itself in the deletion, but never delete the marker message.
    if message.id not in ids:
        ids.append(message.id)
    deleted = await _delete_ids(message.chat.id, ids)

    try:
        if deleted:
            sent = await message.reply(f"🗑️ <b>Pᴜʀɢᴇᴅ {max(deleted - 1, 0)} ᴍᴇssᴀɢᴇs.</b>")
            await asyncio.sleep(2)
            await sent.delete()
    except Exception:
        pass


async def _spurge(_, message):
    if not await _guard(message):
        return
    reply = message.reply_to_message
    if not reply:
        return await message.reply("❌ <b>Reply to the first message you want to purge from.</b>")
    args = message.command or []
    if len(args) >= 2:
        try:
            count = int(args[1])
        except ValueError:
            return await message.reply("❌ <b>Usage:</b> <code>/spurge</code> or <code>/spurge 50</code>")
        if count <= 0 or count > MAX_PURGE:
            return await message.reply(f"❌ <b>Choose a number between 1 and {MAX_PURGE}.</b>")
        ids = (await _messages_between(message.chat.id, reply.id, limit=count))[:count]
    else:
        ids = await _messages_between(message.chat.id, reply.id, end_id=message.id, limit=MAX_PURGE)
    if message.id not in ids:
        ids.append(message.id)
    await _delete_ids(message.chat.id, ids)


async def _delete_reply(_, message):
    if not await _guard(message):
        return
    if not message.reply_to_message:
        return await message.reply("❌ <b>Reply to the message you want to delete.</b>")
    try:
        await message.reply_to_message.delete()
        await message.delete()
    except Exception:
        pass


async def _purgefrom(_, message):
    if not await _guard(message):
        return
    if not message.reply_to_message:
        return await message.reply("❌ <b>Reply to a message to mark the purge starting point.</b>")
    if await _set_marker(message.chat.id, message.reply_to_message.id, message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        sent = await app.send_message(message.chat.id, "📌 <b>Pᴜʀɢᴇ sᴛᴀʀᴛ mᴀʀᴋᴇᴅ.</b>")
        await asyncio.sleep(2)
        try:
            await sent.delete()
        except Exception:
            pass
    else:
        await message.reply("❌ <b>Could not save the purge marker.</b>")


async def _purgeto(_, message):
    if not await _guard(message):
        return
    if not message.reply_to_message:
        return await message.reply("❌ <b>Reply to the message to mark the purge ending point.</b>")
    start_id = await _get_marker(message.chat.id)
    if not start_id:
        return await message.reply("❌ <b>No purge start is marked.</b> Use <code>/purgefrom</code> first.")
    end_id = message.reply_to_message.id
    if end_id < start_id:
        start_id, end_id = end_id, start_id
    ids = await _messages_between(message.chat.id, start_id, end_id=end_id, limit=MAX_PURGE)
    # Include both boundaries, as the user asked for all messages between the two markers.
    ids.extend([start_id, end_id, message.id])
    deleted = await _delete_ids(message.chat.id, sorted(set(ids)))
    await _clear_marker(message.chat.id)
    # The command itself may already have been deleted; no extra confirmation is required.
    return deleted


@app.on_message(filters.command(["purge"], prefixes=PREFIXES))
async def purge_handler(client, message):
    return await _purge(client, message)


@app.on_message(filters.command(["spurge"], prefixes=PREFIXES))
async def spurge_handler(client, message):
    return await _spurge(client, message)


@app.on_message(filters.command(["del", "d", "delete"], prefixes=PREFIXES))
async def delete_handler(client, message):
    return await _delete_reply(client, message)


@app.on_message(filters.command(["purgefrom"], prefixes=PREFIXES))
async def purgefrom_handler(client, message):
    return await _purgefrom(client, message)


@app.on_message(filters.command(["purgeto"], prefixes=PREFIXES))
async def purgeto_handler(client, message):
    return await _purgeto(client, message)
