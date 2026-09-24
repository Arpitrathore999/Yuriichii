from pyrogram import filters
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action

COMMANDS = [
    "hug","kiss","bite","slap","kick","cuddle","pat","highfive",
    "flirt","love","crush","couple","propose","marriage","divorce"
]

@app.on_message(filters.command(COMMANDS))
async def social(_, message):
    command = (message.command or [""])[0].lower()

    if command in {"couple"}:
        return await message.reply("💞 `/couple` ko group mein use karke random couple feature add kar sakte hain.")

    target = get_reply_target(message)
    if not target:
        return await message.reply("❌ Kisi user ke message par **reply** karke command use karo.")

    if target.is_bot:
        return await message.reply("🤖 Bot ko target mat karo 😭")
    if target.id == message.from_user.id:
        return await message.reply("❌ Khud par ye command nahi chalegi 😭")

    try:
        text = await action(message, command, target)
        await message.reply(text, parse_mode="html")
    except Exception as e:
        await message.reply(f"❌ Social command error: `{e}`")
