# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/tagall.py — Tag All Members
# --------------------------------------------------------------------------------

import asyncio
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import RPCError

import config
from core.bot import app

PREFIXES = ["/", "!", "."]

# Per-chat cancel flags
spam_chats = set()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _is_admin(message):
    if not _is_group(message) or not message.from_user:
        return False
    if int(message.from_user.id) == int(config.OWNER_ID):
        return True
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


# ─── /all | /call | /tagall ──────────────────────────────────────────────────
@app.on_message(filters.command(["all", "call", "tagall"], prefixes=PREFIXES) & filters.group)
async def tag_all(_, message):
    chat_id = message.chat.id

    if not await _is_admin(message):
        return await message.reply("❌ ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")

    # Get args (support newlines)
    full = message.text or ""
    parts = full.split(maxsplit=1)
    arg_text = parts[1].strip() if len(parts) > 1 else None

    if arg_text and message.reply_to_message:
        return await message.reply("❌ ɢɪᴠᴇ ᴍᴇ ᴏɴʟʏ ᴏɴᴇ ᴀʀɢᴜᴍᴇɴᴛ!")

    if arg_text:
        mode = "text_on_cmd"
        msg = arg_text
    elif message.reply_to_message:
        mode = "text_on_reply"
        msg = message.reply_to_message
    else:
        return await message.reply(
            "❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴏʀ ɢɪᴠᴇ ᴍᴇ ꜱᴏᴍᴇ ᴛᴇxᴛ ᴛᴏ ᴍᴇɴᴛɪᴏɴ ᴏᴛʜᴇʀꜱ."
        )

    spam_chats.add(chat_id)

    usrnum = 0
    usrtxt = ""
    try:
        async for usr in app.get_chat_members(chat_id):
            if chat_id not in spam_chats:
                break
            if usr.user.is_bot or usr.user.is_deleted:
                continue

            usrnum += 1
            usrtxt += f"[{usr.user.first_name}](tg://user?id={usr.user.id}) "

            if usrnum == 5:
                try:
                    if mode == "text_on_cmd":
                        await app.send_message(chat_id, f"{msg}\n\n{usrtxt}")
                    elif mode == "text_on_reply":
                        await msg.reply(usrtxt)
                except RPCError as e:
                    print(f"[TAGALL] {type(e).__name__}: {e}", flush=True)

                await asyncio.sleep(2)
                usrnum = 0
                usrtxt = ""
    except Exception as e:
        print(f"[TAGALL LOOP] {type(e).__name__}: {e}", flush=True)
    finally:
        spam_chats.discard(chat_id)


# ─── /cancel | /stop ─────────────────────────────────────────────────────────
@app.on_message(filters.command(["cancel", "stop"], prefixes=PREFIXES) & filters.group)
async def cancel_tag(_, message):
    chat_id = message.chat.id
    if chat_id not in spam_chats:
        return await message.reply("❌ ᴛʜᴇʀᴇ ɪꜱ ɴᴏ ᴘʀᴏᴄᴇꜱꜱ ᴏɴɢᴏɪɴɢ.")

    spam_chats.discard(chat_id)
    return await message.reply("🛑 ꜱᴛᴏᴘᴘᴇᴅ.")