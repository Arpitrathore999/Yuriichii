# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/id.py — 🌐 ID INFO (Rich UI table)
# --------------------------------------------------------------------------------

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.bot import app
from utils.rich_ui import (
    rich_esc,
    rich_heading,
    rich_kv_table,
    rich_send,
)

PREFIXES = ["/", "!", "."]


def _bold(text: str) -> str:
    return f"<b>{text}</b>"


@app.on_message(filters.command("id", prefixes=PREFIXES))
async def id_handler(_, message: Message):
    if not message.from_user:
        return

    # ── Build rows ──
    rows = [
        (_bold("ᴍᴇssᴀɢᴇ ɪᴅ"), f"<code>{message.id}</code>"),
        (_bold("ʏᴏᴜʀ ɪᴅ"), f"<code>{message.from_user.id}</code>"),
        (_bold("ᴄʜᴀᴛ ɪᴅ"), f"<code>{message.chat.id}</code>"),
    ]

    # Optional fields — only if replied
    reply = message.reply_to_message
    if reply:
        rows.append((_bold("ʀᴇᴘʟɪᴇᴅ ᴍsɢ ɪᴅ"), f"<code>{reply.id}</code>"))
        if reply.from_user:
            rows.append((_bold("ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ"), f"<code>{reply.from_user.id}</code>"))

    text = (
        rich_heading("🌐 ɪᴅ ɪɴꜰᴏ", level=3)
        + "\n"
        + rich_kv_table(rows)
    )

    await rich_send(
        app,
        message.chat.id,
        text,
        reply_to_message_id=message.id,
    )
