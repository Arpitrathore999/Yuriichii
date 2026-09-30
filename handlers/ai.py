import re
from pyrogram import filters
from pyrogram.enums import ChatAction
from core.bot import app
from database.users import ensure_user
from modules.ai.companion import chat

PREFIXES = ["/", "!", "."]

SOCIAL_COMMANDS = [
    "hug", "kiss", "bite", "slap", "punch", "cuddle", "pat", "highfive",
    "flirt", "love", "crush", "couple", "propose", "marriage", "divorce"
]

ALL_COMMANDS = SOCIAL_COMMANDS + [
    # Handlers
    "start", "ai", "ping", "speedtest", "spt",
    "broadcast", "gcast", "adminpanel", "adminuser",
    "cancelbroadcast", "adminhelp", "stats",
    "addgif", "addcaption", "socialgifs", "socialcaptions",
    "clearsocialgifs", "clearsocialcaptions", "banbot", "botunban",
    # Bans
    "ban", "unban", "kick", "mute", "tmute", "unmute",
    "sban", "tban", "dban", "smute", "dmute", "skick", "dkick",
    # Warnings
    "warn", "dwarn", "swarn", "warns", "warnings",
    "rmwarn", "resetwarn", "resetallwarns",
    "warnmode", "warnlimit", "warntime",
    # Filters (renamed stop)
    "filter", "filters", "stopfilter", "stopf", "stopall",
    # Greetings
    "welcome", "goodbye", "setwelcome", "setgoodbye",
    "resetwelcome", "resetgoodbye", "cleanwelcome",
    # Locks
    "lock", "unlock", "locks", "lockwarns", "locktypes",
    # Pins
    "pin", "unpin", "pinned", "unpinall",
    # Purge
    "purge", "spurge", "purgefrom", "purgeto",
    "del", "d", "delete",
    # Reports
    "report", "reports", "admin",
    # Control
    "promote", "demote", "adminlist", "add", "remove",
    # Tagall
    "all", "call", "tagall", "cancel", "stop",

    # Economy
    "bal", "balance", "daily", "kill", "rob", "give",
    "wallet", "protect", "check", "toprich", "topkillers",
    "shop", "buy", "gift", "setemoji", "revive", "open", "close"

    # Economy admin/shop management
    "shopadd", "shopedit", "shopmedia", "shopremove",
    "shopstock", "shoptoggle", "shopgift", "addcoins", "removecoins",
]


@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(ALL_COMMANDS, prefixes=PREFIXES)
)
async def private_chat(_, message):
    if not message.from_user or not message.text:
        return
    await ensure_user(message.from_user)
    await message.reply_chat_action(ChatAction.TYPING)
    await message.reply(await chat(message.from_user.id, message.text))


@app.on_message(filters.command("ai", prefixes=PREFIXES))
async def ai_command(_, message):
    if not message.from_user:
        return
    await ensure_user(message.from_user)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("🤖 Use /ai <message> to chat with Elara.")
    await message.reply_chat_action(ChatAction.TYPING)
    await message.reply(await chat(message.from_user.id, parts[1]))


@app.on_message(
    filters.group
    & filters.text
    & ~filters.command(ALL_COMMANDS, prefixes=PREFIXES)
)
async def group_chat(_, message):
    if not message.from_user or not message.text:
        return

    # Extra safety — skip any slash-prefixed message
    try:
        if message.text and message.text[0] in PREFIXES:
            return
    except Exception:
        return

    me = await app.get_me()
    raw = message.text.strip()
    triggered = re.match(r"^elara(?:\s+|$)", raw, re.I)
    mentioned = me.username and re.search(
        rf"@{re.escape(me.username)}(?:\s|$|[.,!?])", raw, re.I
    )
    replied = (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == me.id
    )

    if not (triggered or mentioned or replied):
        return

    if replied:
        prompt = raw
    elif triggered:
        prompt = re.sub(r"^elara(?:\s+|$)", "", raw, count=1, flags=re.I).strip()
    else:
        prompt = re.sub(
            rf"@{re.escape(me.username)}(?:\s+|$)", "", raw, count=1, flags=re.I
        ).strip()

    if not prompt:
        prompt = "Hey Elara, say something fun."

    await ensure_user(message.from_user)
    await message.reply_chat_action(ChatAction.TYPING)
    await message.reply(await chat(message.from_user.id, prompt))
