from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from core.bot import app
import config
from modules.social.settings import COMMANDS, add_gif, add_caption, get_social_data, clear_gifs, clear_captions


def owner_only(message):
    return bool(
        message.from_user
        and config.OWNER_ID
        and message.from_user.id == config.OWNER_ID
    )


async def is_manager(message):
    """Owner can manage anywhere; Telegram group admins can manage in groups."""
    if owner_only(message):
        return True
    if not message.from_user or not message.chat:
        return False
    try:
        if str(message.chat.type).lower() in {"private", "chattype.private"}:
            return False
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        status = getattr(member, "status", None)
        return status in {
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
            "owner",
            "administrator",
        }
    except Exception as e:
        print(f"[ADMIN PERMISSION ERROR] {type(e).__name__}: {e}", flush=True)
        return False


async def can_manage_social(message):
    return await is_manager(message)


@app.on_message(filters.command("adminhelp"))
async def admin_help(_, message):
    if not await is_manager(message):
        return
    await message.reply(
        "🛠️ **Social Admin Panel**\n\n"
        "🎞️ `/addgif <command>` — reply to a GIF/animation to save it\n"
        "📝 `/addcaption <command> <caption>` — save a caption\n"
        "📊 `/socialgifs <command>` — show GIF/caption counts\n"
        "🗑️ `/clearsocialgifs <command>` — remove all GIFs\n"
        "🗑️ `/clearsocialcaptions <command>` — remove custom captions\n\n"
        "Example: reply to a GIF with `/addgif hug`\n"
        "Example: `/addcaption hug {a} hugged {b}! 🫂❤️`",
        parse_mode="html",
    )


@app.on_message(filters.command("stats"))
async def stats(_, message):
    if not owner_only(message):
        return
    await message.reply("📊 **Elara Stats**\n\nBot is online and modular.")


@app.on_message(filters.command("addgif"))
async def add_social_gif(_, message):
    if not await can_manage_social(message):
        return
    if not message.reply_to_message:
        return await message.reply("❌ Pehle GIF/animation send karo, phir uske reply me `/addgif hug`.")
    if len(message.command or []) < 2:
        return await message.reply("Usage: reply to a GIF with `/addgif <command>`\nExample: `/addgif hug`")

    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")

    replied = message.reply_to_message
    media = replied.animation or replied.video or replied.document
    if not media:
        return await message.reply("❌ Reply to a Telegram GIF/animation.")

    file_id = media.file_id
    if await add_gif(command, file_id):
        data = await get_social_data(command)
        await message.reply(f"✅ GIF added to `/{command}`\n🎞️ Total GIFs: {len(data['gifs'])}")
    else:
        await message.reply("❌ MongoDB is not configured/available.")


@app.on_message(filters.command("addcaption"))
async def add_social_caption(_, message):
    if not await can_manage_social(message):
        return
    if len(message.command or []) < 3:
        return await message.reply(
            "Usage:\n`/addcaption hug 🫂 <b>{a} hugged {b}!</b>`\n\n"
            "Placeholders: `{a}` = sender, `{b}` = target, `{pct}` = percentage."
        )

    command = message.command[1].lower().lstrip("/")
    caption = message.text.split(None, 2)[2].strip()
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    if not caption:
        return await message.reply("❌ Caption cannot be empty.")

    if await add_caption(command, caption):
        data = await get_social_data(command)
        await message.reply(f"✅ Caption added to `/{command}`\n📝 Total captions: {len(data['captions'])}")
    else:
        await message.reply("❌ MongoDB is not configured/available.")


@app.on_message(filters.command("socialgifs"))
async def social_gifs(_, message):
    if not await can_manage_social(message):
        return
    if len(message.command or []) < 2:
        return await message.reply("Usage: `/socialgifs hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    data = await get_social_data(command)
    await message.reply(f"🎞️ `/{command}` has **{len(data['gifs'])}** custom GIF(s).\n📝 Captions: **{len(data['captions'])}**")


@app.on_message(filters.command("clearsocialgifs"))
async def clear_social_gifs(_, message):
    if not await can_manage_social(message):
        return
    if len(message.command or []) < 2:
        return await message.reply("Usage: `/clearsocialgifs hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    await clear_gifs(command)
    await message.reply(f"🗑️ Custom GIFs cleared for `/{command}`.")


@app.on_message(filters.command("clearsocialcaptions"))
async def clear_social_captions(_, message):
    if not await can_manage_social(message):
        return
    if len(message.command or []) < 2:
        return await message.reply("Usage: `/clearsocialcaptions hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    await clear_captions(command)
    await message.reply(f"🗑️ Custom captions cleared for `/{command}`. Default caption will be used.")
