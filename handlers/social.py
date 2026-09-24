from pyrogram import filters
from core.bot import app
from modules.social.actions import action

COMMANDS = [
    "hug", "kiss", "bite", "slap", "kick", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]


def _target_from_reply(message):
    reply = message.reply_to_message
    return reply.from_user if reply and reply.from_user else None


async def _target_from_argument(message):
    if not message.command or len(message.command) < 2:
        return None
    raw = message.command[1].strip()
    if raw.startswith("@"):
        raw = raw[1:]
    try:
        return await app.get_users(raw)
    except Exception:
        return None


@app.on_message(filters.group & filters.command(COMMANDS))
async def social(_, message):
    try:
        command = (message.command[0] if message.command else "").lower()

        if command == "couple":
            return await message.reply(
                "💞 Use /couple in a group to run the random couple feature."
            )

        target = _target_from_reply(message)
        if target is None:
            target = await _target_from_argument(message)

        if target is None:
            return await message.reply(
                "❌ Reply to a user's message or use a username, for example: /hug @username"
            )

        if target.is_bot:
            return await message.reply("🤖 You cannot target a bot.")

        if not message.from_user:
            return await message.reply("❌ I could not identify the sender of this command.")

        if target.id == message.from_user.id:
            return await message.reply("❌ You cannot use this command on yourself.")

        text = await action(message, command, target)
        return await message.reply(text, parse_mode="html")

    except Exception:
        return await message.reply(
            "❌ I couldn't process that social command right now. Please try again."
        )
