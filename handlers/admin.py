from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from core.bot import app
import config
from modules.social.settings import (
    COMMANDS, add_gif, add_caption, get_social_data, clear_gifs, clear_captions
)

def _is_owner(message):
    try:
        return bool(message.from_user and int(config.OWNER_ID or 0) == int(message.from_user.id))
    except Exception:
        return False

async def _is_social_admin(message):
    if _is_owner(message):
        return True
    if not message.from_user or not message.chat or message.chat.type == ChatType.PRIVATE:
        return False
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        status = getattr(m, "status", None)
        return status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
            "owner",
            "administrator",
        )
    except Exception as e:
        print(f"[SOCIAL ADMIN PERMISSION] {type(e).__name__}: {e}", flush=True)
        return False

async def _guard(message):
    if await _is_social_admin(message):
        return True
    await message.reply_text("❌ You must be the group owner/admin to use this command.")
    return False

def _cmd(message, index=1):
    parts = message.text.split() if message.text else []
    return parts[index].lower().lstrip("/") if len(parts) > index else None

@app.on_message(filters.command("adminhelp"))
async def admin_help(_, message):
    if not await _guard(message): return
    actions = ", ".join(f"/{x}" for x in COMMANDS)
    await message.reply_text(
        "🛠️ **Social Admin Panel**\\n\\n"
        "🎞️ **GIF**\\n"
        "Reply to a GIF/animation and send: `/addgif hug`\\n"
        "`/socialgifs hug` — counts\\n"
        "`/clearsocialgifs hug` — clear GIFs\\n\\n"
        "📝 **Caption**\\n"
        "`/addcaption hug {a} hugged {b}! 🫂`\\n"
        "`/socialcaptions hug` — count\\n"
        "`/clearsocialcaptions hug` — clear captions\\n\\n"
        f"Available social commands:\\n{actions}"
    )

@app.on_message(filters.command("addgif"))
async def add_social_gif(_, message):
    if not await _guard(message): return
    command = _cmd(message)
    if not command:
        return await message.reply_text("❌ Usage: reply to a GIF with `/addgif hug`")
    if command not in COMMANDS:
        return await message.reply_text("❌ Invalid action. Use `/adminhelp`.")
    reply = message.reply_to_message
    if not reply:
        return await message.reply_text("❌ Reply to the GIF/animation you want to save.")
    media = getattr(reply, "animation", None) or getattr(reply, "video", None) or getattr(reply, "document", None)
    if not media or not getattr(media, "file_id", None):
        return await message.reply_text("❌ Reply to a Telegram GIF/animation, video, or document.")
    if not await add_gif(command, media.file_id):
        return await message.reply_text("❌ Could not save GIF. Check `MONGO_URI`.")
    data = await get_social_data(command)
    await message.reply_text(f"✅ Added GIF to `/{command}`\\n🎞️ Total: **{len(data.get('gifs', []))}**")

@app.on_message(filters.command("addcaption"))
async def add_social_caption(_, message):
    if not await _guard(message): return
    parts = message.text.split(None, 2) if message.text else []
    if len(parts) < 3:
        return await message.reply_text("❌ Usage: `/addcaption hug {a} hugged {b}! 🫂`")
    command = parts[1].lower().lstrip("/")
    caption = parts[2].strip()
    if command not in COMMANDS:
        return await message.reply_text("❌ Invalid action. Use `/adminhelp`.")
    if not await add_caption(command, caption):
        return await message.reply_text("❌ Could not save caption. Check `MONGO_URI`.")
    data = await get_social_data(command)
    await message.reply_text(f"✅ Added caption to `/{command}`\\n📝 Total: **{len(data.get('captions', []))}**")

@app.on_message(filters.command("socialgifs"))
async def social_gifs(_, message):
    if not await _guard(message): return
    command = _cmd(message)
    if not command or command not in COMMANDS:
        return await message.reply_text("❌ Usage: `/socialgifs hug`")
    data = await get_social_data(command)
    await message.reply_text(f"🎞️ `/{command}` GIFs: **{len(data.get('gifs', []))}**\\n📝 Captions: **{len(data.get('captions', []))}**")

@app.on_message(filters.command("socialcaptions"))
async def social_captions(_, message):
    if not await _guard(message): return
    command = _cmd(message)
    if not command or command not in COMMANDS:
        return await message.reply_text("❌ Usage: `/socialcaptions hug`")
    data = await get_social_data(command)
    await message.reply_text(f"📝 `/{command}` custom captions: **{len(data.get('captions', []))}**")

@app.on_message(filters.command("clearsocialgifs"))
async def clear_social_gifs(_, message):
    if not await _guard(message): return
    command = _cmd(message)
    if not command or command not in COMMANDS:
        return await message.reply_text("❌ Usage: `/clearsocialgifs hug`")
    if not await clear_gifs(command):
        return await message.reply_text("❌ Could not update database. Check `MONGO_URI`.")
    await message.reply_text(f"🗑️ Cleared custom GIFs for `/{command}`.")

@app.on_message(filters.command("clearsocialcaptions"))
async def clear_social_captions(_, message):
    if not await _guard(message): return
    command = _cmd(message)
    if not command or command not in COMMANDS:
        return await message.reply_text("❌ Usage: `/clearsocialcaptions hug`")
    if not await clear_captions(command):
        return await message.reply_text("❌ Could not update database. Check `MONGO_URI`.")
    await message.reply_text(f"🗑️ Cleared custom captions for `/{command}`.")
