# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/logger.py — Handles bot being added/removed to/from groups
# --------------------------------------------------------------------------------

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from core.bot import app
from core.logger import log_group_join, log_group_leave
from database.mongo import db


@app.on_message(filters.new_chat_members, group=-10)
async def on_bot_added(_, message: Message):
    """Trigger when bot is added to a group."""
    if not message.new_chat_members:
        return

    # Check if bot itself was added
    try:
        me = await app.get_me()
    except Exception:
        return

    bot_was_added = any(
        m.id == me.id for m in message.new_chat_members if m
    )

    if not bot_was_added:
        return

    # Determine if it's a new group or re-join
    is_new = True
    col = db["bot_groups"] if db is not None else None
    if col is not None:
        existing = await col.find_one({"chat_id": int(message.chat.id)})
        if existing:
            is_new = False

    await log_group_join(
        message.chat,
        added_by=message.from_user,
        is_new=is_new,
    )


@app.on_message(filters.left_chat_member, group=-10)
async def on_bot_removed(_, message: Message):
    """Trigger when bot is removed from a group."""
    if not message.left_chat_member:
        return

    try:
        me = await app.get_me()
    except Exception:
        return

    if message.left_chat_member.id != me.id:
        return

    await log_group_leave(message.chat)
