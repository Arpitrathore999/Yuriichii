# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/ai.py — AI Chat Handlers (with anti-spam + cached get_me)
# --------------------------------------------------------------------------------

import re
import time
from collections import defaultdict

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
    "shop", "buy", "gift", "setemoji", "revive", "open", "close",
    "inventory", "setgifttext", "sell", "inv", "items", "cleargifttext",

    # Economy admin/shop management
    "shopadd", "shopedit", "shopmedia", "shopremove",
    "shopstock", "shoptoggle", "shopgift", "addcoins", "removecoins",
    # cardGame
    "bet", "flip", "card", "leaders",
    # hackGame
    "hack", "register", "end", "guess",
    # TTT
    "ttt", "leaderboard",
    # Quote
    "q", "qhelp", "quotehelp",
    # ID
    "id",
]


# ══════════════════════════════════════════════════════════════════════════════
#  🛡️ ANTI-SPAM STATE
# ══════════════════════════════════════════════════════════════════════════════

# Cache get_me() result → avoid FloodWait
_ME_CACHE: dict = {"me": None}

# Recent message timestamps per user: {user_id: [ts, ts, ts]}
_RECENT_MSGS: dict[int, list] = defaultdict(list)

# Blocked users: {user_id: unblock_timestamp}
_BLOCKED_USERS: dict[int, float] = {}

# Users already warned about their current block: {user_id: True}
# → so we notify ONCE, then silently ignore
_BLOCK_NOTIFIED: set = set()

# Config
SPAM_WINDOW_SECONDS = 5
SPAM_MSG_LIMIT = 3
BLOCK_DURATION_SECONDS = 30 * 60  # 30 minutes


async def _get_me():
    """Get bot's own user info (cached)."""
    if _ME_CACHE["me"] is None:
        try:
            _ME_CACHE["me"] = await app.get_me()
        except Exception as e:
            print(f"[AI get_me] {type(e).__name__}: {e}", flush=True)
            return None
    return _ME_CACHE["me"]


def _format_remaining(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} sᴇᴄᴏɴᴅs"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} ᴍɪɴᴜᴛᴇs"
    hours = minutes // 60
    return f"{hours} ʜᴏᴜʀs"


def _check_spam(user_id: int) -> tuple[bool, str, int]:
    """Return (allowed, reason, remaining_seconds).

    Rules:
    - If 3 messages within 5 seconds → block for 30 minutes.
    - Once blocked, only the FIRST blocked attempt gets a message.
    - All subsequent attempts are silently ignored (reason="blocked_silent").
    """
    now = time.time()

    # ── Currently blocked? ──
    blocked_until = _BLOCKED_USERS.get(user_id, 0)
    if blocked_until > now:
        remaining = int(blocked_until - now)
        if user_id in _BLOCK_NOTIFIED:
            return False, "blocked_silent", remaining
        # First time seeing them while blocked → notify
        _BLOCK_NOTIFIED.add(user_id)
        return False, "blocked_notify", remaining

    # ── Block expired → clean up ──
    if blocked_until and blocked_until <= now:
        _BLOCKED_USERS.pop(user_id, None)
        _BLOCK_NOTIFIED.discard(user_id)
        _RECENT_MSGS[user_id] = []

    # ── Track messages within window ──
    recent = [t for t in _RECENT_MSGS.get(user_id, []) if now - t < SPAM_WINDOW_SECONDS]
    recent.append(now)
    _RECENT_MSGS[user_id] = recent

    # ── Spam detected: 3 msgs in 5 sec ──
    if len(recent) >= SPAM_MSG_LIMIT:
        _BLOCKED_USERS[user_id] = now + BLOCK_DURATION_SECONDS
        _BLOCK_NOTIFIED.add(user_id)  # Mark as notified (this reply is the notification)
        _RECENT_MSGS[user_id] = []
        return False, "blocked_notify", BLOCK_DURATION_SECONDS

    return True, "ok", 0


async def _handle_block(message, reason: str, remaining: int):
    """Reply only if this is the first block notification. Otherwise silent."""
    if reason == "blocked_silent":
        return
    if reason == "blocked_notify":
        try:
            await message.reply(
                f"🚫 <b>sᴘᴀᴍ ᴅᴇᴛᴇᴄᴛᴇᴅ — ʙʟᴏᴄᴋᴇᴅ!</b>\n\n"
                f"<i>ʏᴏᴜ ᴀʀᴇ ʙʟᴏᴄᴋᴇᴅ ꜰᴏʀ</i> "
                f"<code>{_format_remaining(remaining)}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(ALL_COMMANDS, prefixes=PREFIXES)
)
async def private_chat(_, message):
    if not message.from_user or not message.text:
        return

    allowed, reason, remaining = _check_spam(message.from_user.id)
    if not allowed:
        await _handle_block(message, reason, remaining)
        return

    await ensure_user(message.from_user)
    await message.reply_chat_action(ChatAction.TYPING)
    try:
        await message.reply(await chat(message.from_user.id, message.text))
    except Exception as e:
        print(f"[AI private] {type(e).__name__}: {e}", flush=True)


@app.on_message(filters.command("ai", prefixes=PREFIXES))
async def ai_command(_, message):
    if not message.from_user:
        return

    allowed, reason, remaining = _check_spam(message.from_user.id)
    if not allowed:
        await _handle_block(message, reason, remaining)
        return

    await ensure_user(message.from_user)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("🤖 Use /ai <message> to chat with Elara.")
    await message.reply_chat_action(ChatAction.TYPING)
    try:
        await message.reply(await chat(message.from_user.id, parts[1]))
    except Exception as e:
        print(f"[AI cmd] {type(e).__name__}: {e}", flush=True)


@app.on_message(
    filters.group
    & filters.text
    & ~filters.command(ALL_COMMANDS, prefixes=PREFIXES)
)
async def group_chat(_, message):
    if not message.from_user or not message.text:
        return

    # Safety — skip slash-prefixed
    try:
        if message.text and message.text[0] in PREFIXES:
            return
    except Exception:
        return

    # ✅ Cached get_me() — no more FloodWait
    me = await _get_me()
    if me is None:
        return

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

    # 🛡️ Spam check — sirf trigger hone pe
    allowed, reason, remaining = _check_spam(message.from_user.id)
    if not allowed:
        await _handle_block(message, reason, remaining)
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
    try:
        await message.reply(await chat(message.from_user.id, prompt))
    except Exception as e:
        print(f"[AI group] {type(e).__name__}: {e}", flush=True)
