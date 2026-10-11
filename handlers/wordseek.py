# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/wordseek.py — 🎯 WordSeek Game Handlers (crash-safe)
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random

from pyrogram import StopPropagation, filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import Message

from core.bot import app
from core.wordseek_engine import (
    HINT_PENALTY,
    MAX_ATTEMPTS,
    WordSeekGame,
    _game_lock,
    calculate_tiles,
    create_game,
    ensure_stats,
    get_game,
    get_stats,
    is_valid_word,
    persist_game,
    record_loss,
    record_win,
    remove_game,
    remove_persisted_game,
    top_players,
)

PREFIXES = ["/", "!", "."]

_BOT_TRIGGERS = {"elara"}
_PROCESSED_MSG_IDS: set = set()
_PROCESSED_LIMIT = 5000


# ══════════════════════════════════════════════════════════════════════════════
#  SAFE REPLY HELPERS — handles Telegram DC errors gracefully
# ══════════════════════════════════════════════════════════════════════════════
async def _safe_send(chat_id: int, text: str, **kwargs):
    """Send message with retry. Returns Message or None. Never raises."""
    try:
        return await app.send_message(chat_id, text, **kwargs)
    except asyncio.TimeoutError as e:
        print(f"[WordSeek safe_send] timeout: {e}", flush=True)
        return None
    except Exception as e:
        err = type(e).__name__
        if err == "FloodWait":
            try:
                wait = int(getattr(e, "value", 5))
                await asyncio.sleep(min(wait, 60))
                return await app.send_message(chat_id, text, **kwargs)
            except Exception:
                return None
        print(f"[WordSeek safe_send] {err}: {e}", flush=True)
        return None


async def _safe_reply(message: Message, text: str, **kwargs):
    """Reply to a message with error handling. Never raises."""
    try:
        return await message.reply(text, **kwargs)
    except asyncio.TimeoutError as e:
        print(f"[WordSeek safe_reply] timeout: {e}", flush=True)
        # Try sending to chat directly as fallback
        try:
            return await app.send_message(message.chat.id, text, **kwargs)
        except Exception:
            return None
    except Exception as e:
        err = type(e).__name__
        if err == "FloodWait":
            try:
                wait = int(getattr(e, "value", 5))
                await asyncio.sleep(min(wait, 60))
                return await message.reply(text, **kwargs)
            except Exception:
                return None
        print(f"[WordSeek safe_reply] {err}: {e}", flush=True)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{_esc(name)}</a>'


def _user_display(user) -> str:
    return (
        getattr(user, "first_name", None)
        or getattr(user, "username", None)
        or str(getattr(user, "id", "User"))
    )


def _is_group(message: Message) -> bool:
    return message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _track_msg(msg_id: int) -> bool:
    if msg_id in _PROCESSED_MSG_IDS:
        return False
    _PROCESSED_MSG_IDS.add(msg_id)
    if len(_PROCESSED_MSG_IDS) > _PROCESSED_LIMIT:
        for x in list(_PROCESSED_MSG_IDS)[:_PROCESSED_LIMIT // 2]:
            _PROCESSED_MSG_IDS.discard(x)
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  RENDERERS
# ══════════════════════════════════════════════════════════════════════════════
def _render_board(game: WordSeekGame) -> str:
    lines = [
        "🟦 <b>ᴡᴏʀᴅꜱᴇᴇᴋ</b>",
        "",
        f"<b>{game.length}-ʟᴇᴛᴛᴇʀ ᴍᴏᴅᴇ</b> · <code>{game.attempts}/{game.max_attempts}</code>",
        "",
    ]
    for g in game.guesses:
        tiles = " ".join(g["tiles"])
        lines.append(f"{tiles} <code>{_esc(g['word'].upper())}</code>")
    if game.hints_used and game.hint_letters:
        lines.append("")
        lines.append("💡 <b>ʜɪɴᴛꜱ:</b> " + " ".join(
            sorted(game.hint_letters, key=lambda x: int(x.split(":")[0]))
        ))
    return "\n".join(lines)


def _render_help() -> str:
    return (
        "📖 <b>ᴡᴏʀᴅꜱᴇᴇᴋ ʜᴇʟᴘ</b>\n\n"
        "<b>🎮 ꜱᴛᴀʀᴛ ᴀ ɢᴀᴍᴇ:</b>\n"
        "• <code>/new4</code> — 4-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ\n"
        "• <code>/new5</code> — 5-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ\n"
        "• <code>/new6</code> — 6-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ\n\n"
        "<b>🎯 ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:</b>\n"
        "• ꜱᴇɴᴅ ᴡᴏʀᴅꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴛᴏ ɢᴜᴇꜱꜱ\n"
        f"• ᴍᴀx <b>{MAX_ATTEMPTS}</b> ᴀᴛᴛᴇᴍᴘᴛꜱ ᴘᴇʀ ɢᴀᴍᴇ\n\n"
        "<b>🎨 ᴛɪʟᴇ ᴍᴇᴀɴɪɴɢꜱ:</b>\n"
        "🟩 ᴄᴏʀʀᴇᴄᴛ ʟᴇᴛᴛᴇʀ, ᴄᴏʀʀᴇᴄᴛ ᴘᴏꜱɪᴛɪᴏɴ\n"
        "🟨 ᴄᴏʀʀᴇᴄᴛ ʟᴇᴛᴛᴇʀ, ᴡʀᴏɴɢ ᴘᴏꜱɪᴛɪᴏɴ\n"
        "🟥 ʟᴇᴛᴛᴇʀ ɴᴏᴛ ɪɴ ᴡᴏʀᴅ\n\n"
        "<b>📊 ᴏᴛʜᴇʀ ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n"
        "• <code>/wordtop</code> — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n"
        "• <code>/wordstats</code> — ʏᴏᴜʀ ꜱᴛᴀᴛꜱ\n"
        "• <code>/wordhint</code> — ɢᴇᴛ ᴀ ʜɪɴᴛ (-5 ᴘᴛꜱ)\n"
        "• <code>/wordcancel</code> — ᴄᴀɴᴄᴇʟ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  START GAME
# ══════════════════════════════════════════════════════════════════════════════
async def _start_game(_, message: Message, length: int):
    if not _is_group(message):
        await _safe_reply(
            message,
            "❌ <b>ᴡᴏʀᴅꜱᴇᴇᴋ ᴏɴʟʏ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ.</b>\n"
            "<i>ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴀ ɢʀᴏᴜᴘ ᴛᴏ ᴘʟᴀʏ!</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    if not message.from_user:
        return

    existing = get_game(message.chat.id)
    if existing and existing.is_active():
        await _safe_reply(
            message,
            f"⚠️ <b>ᴀ ɢᴀᴍᴇ ɪꜱ ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!</b>\n"
            f"<i>ᴜꜱᴇ</i> <code>/wordcancel</code> <i>ᴛᴏ ᴄᴀɴᴄᴇʟ ɪᴛ.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    game = create_game(
        chat_id=message.chat.id,
        length=length,
        starter_id=message.from_user.id,
        starter_name=_user_display(message.from_user),
    )

    if not game.secret:
        remove_game(message.chat.id)
        await _safe_reply(
            message,
            "❌ <b>ᴅɪᴄᴛɪᴏɴᴀʀʏ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ ꜰᴏʀ ᴛʜɪꜱ ʟᴇɴɢᴛʜ.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        await ensure_stats(
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
        )
        await persist_game(game)
    except Exception as e:
        print(f"[WordSeek start persist] {type(e).__name__}: {e}", flush=True)

    text = (
        f"🎯 <b>ᴡᴏʀᴅꜱᴇᴇᴋ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
        f"📏 <b>{length}-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ</b>\n"
        f"🎯 <b>ᴍᴀx ᴀᴛᴛᴇᴍᴘᴛꜱ:</b> <code>{MAX_ATTEMPTS}</code>\n"
        f"👤 <b>sᴛᴀʀᴛᴇᴅ ʙʏ:</b> {_mention(message.from_user.id, _user_display(message.from_user))}\n\n"
        f"💬 <i>sᴇɴᴅ ᴀ {length}-ʟᴇᴛᴛᴇʀ ᴡᴏʀᴅ ᴛᴏ ɢᴜᴇꜱꜱ!</i>"
    )
    await _safe_reply(message, text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command("new4", prefixes=PREFIXES) & filters.group)
async def cmd_new4(_, message: Message):
    await _start_game(_, message, 4)


@app.on_message(filters.command("new5", prefixes=PREFIXES) & filters.group)
async def cmd_new5(_, message: Message):
    await _start_game(_, message, 5)


@app.on_message(filters.command("new6", prefixes=PREFIXES) & filters.group)
async def cmd_new6(_, message: Message):
    await _start_game(_, message, 6)


# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["wordhelp", "wordseekhelp"], prefixes=PREFIXES))
async def cmd_wordhelp(_, message: Message):
    await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  CANCEL
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordcancel", prefixes=PREFIXES) & filters.group)
async def cmd_wordcancel(_, message: Message):
    if not _is_group(message):
        return

    game = get_game(message.chat.id)
    if not game or not game.is_active():
        await _safe_reply(message, "❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>", parse_mode=ParseMode.HTML)
        return

    is_starter = message.from_user and message.from_user.id == game.starter_id
    is_admin = False
    if message.from_user:
        try:
            member = await app.get_chat_member(message.chat.id, message.from_user.id)
            is_admin = member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
        except Exception:
            pass

    if not (is_starter or is_admin):
        await _safe_reply(
            message,
            "❌ <b>ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ sᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴs ᴄᴀɴ ᴄᴀɴᴄᴇʟ ɪᴛ.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    secret = game.secret
    game.finish_cancelled()
    remove_game(message.chat.id)
    await remove_persisted_game(message.chat.id)

    await _safe_reply(
        message,
        f"🚫 <b>ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
        f"🔑 ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀꜱ: <code>{_esc(secret.upper())}</code>",
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  HINT
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("wordhint", prefixes=PREFIXES) & filters.group)
async def cmd_wordhint(_, message: Message):
    if not _is_group(message):
        return

    game = get_game(message.chat.id)
    if not game or not game.is_active():
        await _safe_reply(message, "❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)
        return

    secret = game.secret
    revealed = {int(x.split(":")[0]) for x in game.hint_letters if ":" in x}
    available = [i for i in range(len(secret)) if i not in revealed]

    if not available:
        await _safe_reply(message, "💡 <b>ᴀʟʟ ʜɪɴᴛꜱ ᴀʟʀᴇᴀᴅʏ ʀᴇᴠᴇᴀʟᴇᴅ!</b>", parse_mode=ParseMode.HTML)
        return

    pos = random.choice(available)
    letter = secret[pos].upper()
    game.hint_letters.append(f"{pos}:{letter}")
    game.hints_used += 1
    try:
        await persist_game(game)
    except Exception:
        pass

    display = []
    for i in range(len(secret)):
        match = next((h for h in game.hint_letters if h.startswith(f"{i}:")), None)
        display.append(match.split(":")[1] if match else "⬜")

    await _safe_reply(
        message,
        f"💡 <b>ʜɪɴᴛ #{game.hints_used}</b>\n\n"
        f"<code>{' '.join(display)}</code>\n\n"
        f"<i>⚠️ ᴇᴀᴄʜ ʜɪɴᴛ ᴄᴏꜱᴛꜱ {HINT_PENALTY} ᴘᴏɪɴᴛꜱ ꜰʀᴏᴍ ᴛʜᴇ ᴡɪɴ ꜱᴄᴏʀᴇ.</i>",
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LEADERBOARD
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["wordtop", "wordleaderboard"], prefixes=PREFIXES))
async def cmd_wordtop(_, message: Message):
    try:
        rows = await top_players(10)
    except Exception as e:
        print(f"[WordSeek wordtop] {type(e).__name__}: {e}", flush=True)
        rows = []

    if not rows:
        await _safe_reply(
            message,
            "🏆 <b>ᴡᴏʀᴅꜱᴇᴇᴋ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n❌ ɴᴏ ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )
        return

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>ᴡᴏʀᴅꜱᴇᴇᴋ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        name = row.get("first_name") or row.get("username") or str(row["_id"])
        points = int(row.get("points", 0))
        wins = int(row.get("games_won", 0))
        avg = float(row.get("avg_guesses_per_win", 0.0))
        lines.append(
            f"{rank} <b>{_esc(name)}</b> — <code>{points}</code> ᴘᴛꜱ • "
            f"<code>{wins}</code> ᴡɪɴꜱ • ᴀᴠɢ <code>{avg:.1f}</code>"
        )
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["wordstats", "mystats"], prefixes=PREFIXES))
async def cmd_wordstats(_, message: Message):
    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user

    if not target:
        return

    try:
        doc = await get_stats(target.id)
    except Exception as e:
        print(f"[WordSeek stats] {type(e).__name__}: {e}", flush=True)
        doc = None

    name = target.first_name or target.username or str(target.id)

    if not doc:
        await _safe_reply(
            message,
            f"📊 <b>{_esc(name)}'ꜱ ᴡᴏʀᴅꜱᴇᴇᴋ ꜱᴛᴀᴛꜱ</b>\n\n❌ ɴᴏ ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )
        return

    text = (
        f"📊 <b>{_esc(name)}'ꜱ ᴡᴏʀᴅꜱᴇᴇᴋ ꜱᴛᴀᴛꜱ</b>\n\n"
        f"🎮 <b>ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ:</b> <code>{int(doc.get('games_played', 0))}</code>\n"
        f"🏆 <b>ᴡᴏɴ:</b> <code>{int(doc.get('games_won', 0))}</code>\n"
        f"❌ <b>ʟᴏꜱᴛ:</b> <code>{int(doc.get('games_lost', 0))}</code>\n"
        f"💬 <b>ᴛᴏᴛᴀʟ ɢᴜᴇꜱꜱᴇꜱ:</b> <code>{int(doc.get('total_guesses', 0))}</code>\n"
        f"⭐ <b>ᴘᴏɪɴᴛꜱ:</b> <code>{int(doc.get('points', 0))}</code>\n"
        f"🔥 <b>ᴄᴜʀʀᴇɴᴛ ꜱᴛʀᴇᴀᴋ:</b> <code>{int(doc.get('win_streak', 0))}</code>\n"
        f"🏅 <b>ʙᴇꜱᴛ ꜱᴛʀᴇᴀᴋ:</b> <code>{int(doc.get('best_streak', 0))}</code>\n"
        f"📈 <b>ᴀᴠɢ ɢᴜᴇꜱꜱᴇꜱ/ᴡɪɴ:</b> <code>{float(doc.get('avg_guesses_per_win', 0.0)):.1f}</code>"
    )
    await _safe_reply(message, text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  GUESS HANDLER
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.group & filters.text, group=10)
async def wordseek_guess_handler(_, message: Message):
    if not message.from_user or not message.text:
        return

    text_raw = message.text.strip()
    if not text_raw or text_raw[0] in PREFIXES:
        return
    if message.from_user.is_bot:
        return

    game = get_game(message.chat.id)
    if not game or not game.is_active():
        return

    first_word = text_raw.split()[0].lower() if text_raw.split() else ""
    if first_word in _BOT_TRIGGERS:
        return

    word = text_raw.lower().strip()
    if " " in word:
        return
    if not word.isalpha():
        return
    if len(word) != game.length:
        return
    if not _track_msg(message.id):
        return

    lock = _game_lock(message.chat.id)
    async with lock:
        game = get_game(message.chat.id)
        if not game or not game.is_active():
            return

        if not is_valid_word(word, game.length):
            await _safe_reply(
                message,
                f"❌ <b>ɴᴏᴛ ɪɴ ᴡᴏʀᴅ ʟɪꜱᴛ:</b> <code>{_esc(word.upper())}</code>\n"
                "<i>ᴛʀʏ ᴀ ᴅɪꜰꜰᴇʀᴇɴᴛ ᴡᴏʀᴅ.</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        tiles = calculate_tiles(game.secret, word)
        game.add_guess(
            user_id=message.from_user.id,
            user_name=_user_display(message.from_user),
            word=word,
            tiles=tiles,
        )

        # ── WIN ──
        if game.check_win(word):
            game.finish_win(message.from_user.id, _user_display(message.from_user))

            base_points = game.calculate_score()
            hint_penalty = game.hints_used * HINT_PENALTY
            points = max(0, base_points - hint_penalty)

            try:
                await record_win(
                    user_id=message.from_user.id,
                    username=message.from_user.username or "",
                    first_name=message.from_user.first_name or "",
                    points=points,
                    guesses_used=game.attempts,
                )
            except Exception as e:
                print(f"[WordSeek win record] {type(e).__name__}: {e}", flush=True)

            board_text = _render_board(game)
            await _safe_reply(
                message,
                f"{board_text}\n\n"
                f"🎉 <b>ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ!</b>\n\n"
                f"🏆 <b>ᴘʟᴀʏᴇʀ:</b> {_mention(message.from_user.id, _user_display(message.from_user))}\n"
                f"✅ ʏᴏᴜ ɢᴜᴇꜱꜱᴇᴅ ᴛʜᴇ ᴡᴏʀᴅ ᴄᴏʀʀᴇᴄᴛʟʏ!\n"
                f"🔑 <b>ᴄᴏʀʀᴇᴄᴛ ᴡᴏʀᴅ:</b> <code>{_esc(game.secret.upper())}</code>\n"
                f"⭐ ᴀᴅᴅᴇᴅ <code>{points}</code> ᴘᴏɪɴᴛꜱ ᴛᴏ ᴛʜᴇ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ.\n\n"
                f"🔄 ᴛʏᴘᴇ <code>/new{game.length}</code> ꜰᴏʀ ᴀɴᴏᴛʜᴇʀ ɢᴀᴍᴇ!",
                parse_mode=ParseMode.HTML,
            )

            remove_game(message.chat.id)
            try:
                await remove_persisted_game(message.chat.id)
            except Exception:
                pass
            return

        # ── LOSS ──
        if game.attempts >= game.max_attempts:
            game.finish_lost()
            try:
                await record_loss(
                    user_id=message.from_user.id,
                    username=message.from_user.username or "",
                    first_name=message.from_user.first_name or "",
                    guesses_used=1,
                )
            except Exception:
                pass

            board_text = _render_board(game)
            await _safe_reply(
                message,
                f"{board_text}\n\n"
                f"❌ <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
                f"🔑 <b>ᴄᴏʀʀᴇᴄᴛ ᴡᴏʀᴅ:</b> <code>{_esc(game.secret.upper())}</code>\n\n"
                f"ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ!",
                parse_mode=ParseMode.HTML,
            )

            remove_game(message.chat.id)
            try:
                await remove_persisted_game(message.chat.id)
            except Exception:
                pass
            return

        # ── Continue ──
        try:
            await persist_game(game)
        except Exception:
            pass
        await _safe_reply(message, _render_board(game), parse_mode=ParseMode.HTML)
