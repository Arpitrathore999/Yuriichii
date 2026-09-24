from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from core.bot import app
import config
from modules.social.settings import (
    COMMANDS,
    add_gif,
    add_caption,
    get_social_data,
    clear_gifs,
    clear_captions,
)


def owner_only(message):
    return bool(message.from_user and config.OWNER_ID and message.from_user.id == config.OWNER_ID)


async def can_manage_social(message):
    if owner_only(message):
        return True
    if not message.from_user or not message.chat:
        return False
    if message.chat.type == ChatType.PRIVATE:
        return False
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception as e:
        print(f"[SOCIAL ADMIN PERMISSION] {type(e).__name__}: {e}", flush=True)
        return False


async def deny(message):
    await message.reply("❌ You must be the group owner/admin to use this command.")


@app.on_message(filters.command("adminhelp"))
async def admin_help(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "🛠️ **Social Admin Commands**\n\n"
        "🎞️ **GIFs**\n"
        "• Reply to a GIF → `/addgif hug`\n"
        "• `/socialgifs hug` — count GIFs/captions\n"
        "• `/clearsocialgifs hug` — clear all GIFs\n\n"
        "📝 **Captions**\n"
        "• `/addcaption hug Your caption {a} {b}`\n"
        "• `/socialcaptions hug` — show caption count\n"
        "• `/clearsocialcaptions hug` — clear custom captions\n\n"
        "Available actions: " + ", ".join(f"`/{x}`" for x in COMMANDS)
    )


@app.on_message(filters.command("stats"))
async def stats(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply("📊 **Elara Stats**\n\nBot is online and modular.")


@app.on_message(filters.command("addgif"))
async def add_social_gif(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a GIF/animation with `/addgif hug`.")
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: reply to a GIF with `/addgif <command>`")

    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command. Use `/adminhelp` to see actions.")

    replied = message.reply_to_message
    media = replied.animation or replied.video or replied.document
    if not media:
        return await message.reply("❌ The replied message must contain a GIF/animation/video/document.")

    if await add_gif(command, media.file_id):
        data = await get_social_data(command)
        await message.reply(f"✅ GIF added to `/{command}`\n🎞️ Total GIFs: **{len(data['gifs'])}**")
    else:
        await message.reply("❌ MongoDB is unavailable. Check `MONGO_URI`.")


@app.on_message(filters.command("addcaption"))
async def add_social_caption(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 3:
        return await message.reply("❌ Usage: `/addcaption hug {a} hugged {b}! ❤️`")

    command = message.command[1].lower().lstrip("/")
    caption = message.text.split(None, 2)[2].strip()
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command. Use `/adminhelp`.")

    if await add_caption(command, caption):
        data = await get_social_data(command)
        await message.reply(f"✅ Caption added to `/{command}`\n📝 Total captions: **{len(data['captions'])}**")
    else:
        await message.reply("❌ MongoDB is unavailable. Check `MONGO_URI`.")


@app.on_message(filters.command("socialgifs"))
async def social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/socialgifs hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    data = await get_social_data(command)
    await message.reply(f"🎞️ `/{command}` GIFs: **{len(data['gifs'])}**\n📝 Captions: **{len(data['captions'])}**")


@app.on_message(filters.command("socialcaptions"))
async def social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/socialcaptions hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    data = await get_social_data(command)
    await message.reply(f"📝 `/{command}` has **{len(data['captions'])}** caption(s).")


@app.on_message(filters.command("clearsocialgifs"))
async def clear_social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/clearsocialgifs hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    ok = await clear_gifs(command)
    await message.reply("🗑️ Custom GIFs cleared." if ok else "❌ MongoDB is unavailable.")


@app.on_message(filters.command("clearsocialcaptions"))
async def clear_social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/clearsocialcaptions hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    ok = await clear_captions(command)
    await message.reply("🗑️ Custom captions cleared." if ok else "❌ MongoDB is unavailable.")
