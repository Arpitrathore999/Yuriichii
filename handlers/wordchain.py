# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/wordchain.py — 🔗 Word Chain Handlers (full)
#  - Timeout ALWAYS eliminates
#  - "ACCEPTED!" message + next player mention
#  - Dynamic timer (40→35→30→25→20→10) & word-length (3→4→5→6→7→8)
#  - Last player = winner
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from core.bot import app
from core.wordchain_engine import (
    ACTIVE_GAMES,
    MODE_BANNED,
    MODE_CHAOS,
    MODE_CHOSEN,
    MODE_CLASSIC,
    MODE_CONFIG,
    MODE_ELIMINATION,
    MODE_HARD,
    MODE_MIXED,
    MODE_RANDOM,
    MODE_REQUIRED,
    USER_ACTIVE,
    WordChainGame,
    _game_lock,
    compute_points,
    create_game,
    ensure_dictionary_loaded,
    ensure_stats,
    get_game,
    get_stats,
    get_user_game,
    persist_game,
    record_result,
    recover_active_games,
    remove_game,
    remove_persisted_game,
    top_players,
)

PREFIXES = ["/", "!", "."]

_BOT_TRIGGERS = {"elara"}
_PROCESSED_MSG_IDS: set = set()
_PROCESSED_LIMIT = 5000

MODE_ALIASES = {
    "classic": MODE_CLASSIC,
    "c": MODE_CLASSIC,
    "elimination": MODE_ELIMINATION,
    "elim": MODE_ELIMINATION,
    "e": MODE_ELIMINATION,
    "mixed": MODE_MIXED,
    "m": MODE_MIXED,
    "banned": MODE_BANNED,
    "b": MODE_BANNED,
    "chosen": MODE_CHOSEN,
    "ch": MODE_CHOSEN,
    "random": MODE_RANDOM,
    "r": MODE_RANDOM,
    "required": MODE_REQUIRED,
    "req": MODE_REQUIRED,
    "hard": MODE_HARD,
    "h": MODE_HARD,
    "chaos": MODE_CHAOS,
    "x": MODE_CHAOS,
}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mention(uid: int, name: str) -> str:
    return f'<a href="tg://user?id={int(uid)}">{_esc(name)}</a>'


def _user_display(user) -> str:
    return (
        getattr(user, "first_name", None)
        or getattr(user, "username", None)
        or str(getattr(user, "id", "User"))
    )


def _is_group(message: Message) -> bool:
    return message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _track(msg_id: int) -> bool:
    if msg_id in _PROCESSED_MSG_IDS:
        return False
    _PROCESSED_MSG_IDS.add(msg_id)
    if len(_PROCESSED_MSG_IDS) > _PROCESSED_LIMIT:
        for x in list(_PROCESSED_MSG_IDS)[:_PROCESSED_LIMIT // 2]:
            _PROCESSED_MSG_IDS.discard(x)
    return True


async def _safe_reply(message: Message, text: str, **kw):
    try:
        return await message.reply(text, **kw)
    except asyncio.TimeoutError:
        try:
            return await app.send_message(message.chat.id, text, **kw)
        except Exception:
            return None
    except Exception as e:
        if type(e).__name__ == "FloodWait":
            try:
                await asyncio.sleep(min(int(getattr(e, "value", 5)), 60))
                return await message.reply(text, **kw)
            except Exception:
                return None
        print(f"[WordChain safe_reply] {type(e).__name__}: {e}", flush=True)
        return None


async def _safe_send(chat_id: int, text: str, **kw):
    try:
        return await app.send_message(chat_id, text, **kw)
    except Exception as e:
        print(f"[WordChain safe_send] {type(e).__name__}: {e}", flush=True)
        return None


async def _safe_edit(chat_id: int, msg_id: int, text: str, **kw):
    try:
        return await app.edit_message_text(chat_id, msg_id, text, **kw)
    except Exception as e:
        err = type(e).__name__
        if err in ("MessageNotModified",):
            return None
        print(f"[WordChain safe_edit] {err}: {e}", flush=True)
        return None


async def _is_admin(chat_id: int, user_id: int) -> bool:
    try:
        m = await app.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  RENDERERS
# ══════════════════════════════════════════════════════════════════════════════
def _render_lobby(game: WordChainGame, seconds_left: int) -> str:
    cfg = game.cfg
    joined = "\n".join(
        f"{i}. {_mention(p['user_id'], p['name'])}"
        for i, p in enumerate(game.players, 1)
    ) or "<i>No players yet — be the first!</i>"

    status = "ᴡᴀɪᴛɪɴɢ ꜰᴏʀ ᴘʟᴀʏᴇʀꜱ"
    if game.can_start():
        status = "✅ ʀᴇᴀᴅʏ ᴛᴏ ꜱᴛᴀʀᴛ!"

    return (
        f"🔗 <b>ᴡᴏʀᴅ ᴄʜᴀɪɴ — ʟᴏʙʙʏ</b>\n\n"
        f"🎮 <b>ᴍᴏᴅᴇ:</b> {cfg['label']}\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b> <code>{len(game.players)}/{cfg['max_players']}</code>\n"
        f"🎯 <b>ᴍɪɴ ɴᴇᴇᴅᴇᴅ:</b> <code>{cfg['min_players']}</code>\n"
        f"⏳ <b>ꜱᴛᴀʀᴛɪɴɢ ɪɴ:</b> <code>{max(0, seconds_left)}s</code>\n"
        f"📊 <b>ꜱᴛᴀᴛᴜꜱ:</b> {status}\n\n"
        f"👤 <b>ᴘʟᴀʏᴇʀꜱ ᴊᴏɪɴᴇᴅ:</b>\n{joined}\n\n"
        f"👉 ᴛᴀᴘ <b>ᴊᴏɪɴ</b> ᴛᴏ ᴘᴀʀᴛɪᴄɪᴘᴀᴛᴇ!"
    )


def _lobby_kb(game: WordChainGame) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ ᴊᴏɪɴ ɢᴀᴍᴇ", callback_data=f"wc_join:{game.chat_id}"),
            InlineKeyboardButton("➖ ʟᴇᴀᴠᴇ", callback_data=f"wc_leave:{game.chat_id}"),
        ],
        [
            InlineKeyboardButton("ℹ️ ʀᴜʟᴇꜱ", callback_data=f"wc_rules:{game.chat_id}"),
        ],
    ])


def _render_turn(game: WordChainGame, seconds_left: int) -> str:
    current = game.current_player()
    if not current:
        return "⏹ ɢᴀᴍᴇ ɴᴏᴛ ᴀᴄᴛɪᴠᴇ."

    required = ""
    if game.last_word:
        required = game.last_word[-1].upper()
    elif game.chosen_first_letter:
        required = game.chosen_first_letter.upper()
    elif game.required_letter:
        required = game.required_letter.upper()
    else:
        required = "ᴀɴʏ"

    extras = []
    if game.banned_letters:
        extras.append(
            f"🚫 <b>ʙᴀɴɴᴇᴅ:</b> <code>"
            f"{', '.join(sorted(x.upper() for x in game.banned_letters))}</code>"
        )
    if game.required_letter_anywhere:
        extras.append(
            f"🔠 <b>ʀᴇQᴜɪʀᴇᴅ:</b> "
            f"<code>{game.required_letter_anywhere.upper()}</code>"
        )
    if game.chaos_events:
        for ev in game.chaos_events:
            extras.append(
                f"🌪 <b>{ev['name']}:</b> <code>{ev.get('desc', '')}</code>"
            )

    # ✅ Show dynamic min length
    min_len = game.current_min_len()
    extras.append(f"📏 <b>ᴍɪɴ ʟᴇɴɢᴛʜ:</b> <code>{min_len}</code> ʟᴇᴛᴛᴇʀꜱ")

    extra_text = ("\n" + "\n".join(extras)) if extras else ""

    last_word_display = game.last_word.upper() if game.last_word else "—"
    total_alive = len(game.alive_players())

    return (
        f"🔗 <b>ᴡᴏʀᴅ ᴄʜᴀɪɴ</b>\n\n"
        f"📝 <b>ʟᴀꜱᴛ ᴡᴏʀᴅ:</b> <code>{_esc(last_word_display)}</code>\n"
        f"🔤 <b>ʀᴇQᴜɪʀᴇᴅ ʟᴇᴛᴛᴇʀ:</b> <code>{required}</code>\n"
        f"👤 <b>ᴄᴜʀʀᴇɴᴛ ᴘʟᴀʏᴇʀ:</b> {_mention(current['user_id'], current['name'])}\n"
        f"👥 <b>ᴀʟɪᴠᴇ:</b> <code>{total_alive}</code>\n"
        f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{max(0, seconds_left)}s</code>"
        f"{extra_text}\n\n"
        f"💬 ᴛʏᴘᴇ ᴀ ᴡᴏʀᴅ ꜱᴛᴀʀᴛɪɴɢ ᴡɪᴛʜ <b>{required}</b>"
    )


def _render_help() -> str:
    return (
        "🔗 <b>ᴡᴏʀᴅ ᴄʜᴀɪɴ — ʜᴇʟᴘ</b>\n\n"
        "<b>🎮 ɢᴀᴍᴇ ᴍᴏᴅᴇꜱ:</b>\n"
        "• <code>/startchain</code> — 🎯 ᴄʟᴀꜱꜱɪᴄ\n"
        "• <code>/startchain elimination</code> — ⚔️ ᴇʟɪᴍɪɴᴀᴛɪᴏɴ\n"
        "• <code>/startchain mixed</code> — 🌀 ᴍɪxᴇᴅ\n"
        "• <code>/startchain banned</code> — 🚫 ʙᴀɴɴᴇᴅ ʟᴇᴛᴛᴇʀꜱ\n"
        "• <code>/startchain chosen</code> — ✍️ ᴄʜᴏꜱᴇɴ ꜰɪʀꜱᴛ ʟᴇᴛᴛᴇʀ\n"
        "• <code>/startchain random</code> — 🎲 ʀᴀɴᴅᴏᴍ ᴍᴏᴅᴇ\n"
        "• <code>/startchain required</code> — 🔠 ʀᴇQᴜɪʀᴇᴅ ʟᴇᴛᴛᴇʀ\n"
        "• <code>/startchain hard</code> — 🔥 ʜᴀʀᴅ ᴍᴏᴅᴇ\n"
        "• <code>/startchain chaos</code> — 🌪 ᴄʜᴀᴏꜱ ᴍᴏᴅᴇ\n\n"
        "<b>⏱ ᴛɪᴍᴇʀ ᴘʀᴏɢʀᴇꜱꜱɪᴏɴ:</b>\n"
        "• 0-4 ᴡᴏʀᴅꜱ → 40s, ᴍɪɴ 3 ʟᴇᴛᴛᴇʀꜱ\n"
        "• 5-9 ᴡᴏʀᴅꜱ → 35s, ᴍɪɴ 4 ʟᴇᴛᴛᴇʀꜱ\n"
        "• 10-14 → 30s, ᴍɪɴ 5 ʟᴇᴛᴛᴇʀꜱ\n"
        "• 15-19 → 25s, ᴍɪɴ 6 ʟᴇᴛᴛᴇʀꜱ\n"
        "• 20-24 → 20s, ᴍɪɴ 7 ʟᴇᴛᴛᴇʀꜱ\n"
        "• 25+ → 10s, ᴍɪɴ 8 ʟᴇᴛᴛᴇʀꜱ\n\n"
        "<b>📋 ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n"
        "• <code>/joinchain</code> — ᴊᴏɪɴ ʟᴏʙʙʏ\n"
        "• <code>/leavechain</code> — ʟᴇᴀᴠᴇ\n"
        "• <code>/forcestartchain</code> — ꜱᴛᴀʀᴛ ɴᴏᴡ\n"
        "• <code>/chaininfo</code> — ɢᴀᴍᴇ ɪɴꜰᴏ\n"
        "• <code>/chainstats</code> — ʏᴏᴜʀ ꜱᴛᴀᴛꜱ\n"
        "• <code>/chaintop</code> — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n"
        "• <code>/killchain</code> — ᴄᴀɴᴄᴇʟ ɢᴀᴍᴇ\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LOBBY TIMER
# ══════════════════════════════════════════════════════════════════════════════
async def _run_lobby_timer(chat_id: int, game: WordChainGame):
    try:
        cfg = game.cfg
        total = cfg["lobby_seconds"]
        elapsed = 0
        interval = 5

        while elapsed < total:
            if game.status != "lobby":
                return
            await asyncio.sleep(min(interval, total - elapsed))
            elapsed += interval

            if game.is_full():
                break

            seconds_left = max(0, total - elapsed)
            if game.lobby_message_id:
                await _safe_edit(
                    chat_id, game.lobby_message_id,
                    _render_lobby(game, seconds_left),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_lobby_kb(game),
                )

        if game.status != "lobby":
            return

        if not game.can_start():
            game.cancel()
            remove_game(chat_id)
            await remove_persisted_game(chat_id)
            await _safe_send(
                chat_id,
                "❌ <b>ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ — ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>\n"
                f"<i>ɴᴇᴇᴅᴇᴅ:</i> <code>{game.cfg['min_players']}</code>, "
                f"<i>ɢᴏᴛ:</i> <code>{len(game.players)}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        await _begin_game(chat_id, game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[WordChain lobby timer] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  BEGIN GAME
# ══════════════════════════════════════════════════════════════════════════════
async def _begin_game(chat_id: int, game: WordChainGame):
    game.status = "running"
    game.player_order = [p["user_id"] for p in game.players]
    random.shuffle(game.player_order)

    by_id = {p["user_id"]: p for p in game.players}
    game.players = [by_id[uid] for uid in game.player_order]
    game.turn_index = 0

    await _setup_mode_rules(game)

    order_mentions = "\n".join(
        f"{i}. {_mention(p['user_id'], p['name'])}"
        for i, p in enumerate(game.players, 1)
    )
    extra = ""
    if game.chosen_first_letter:
        extra += f"\n🎯 <b>ꜱᴛᴀʀᴛɪɴɢ ʟᴇᴛᴛᴇʀ:</b> <code>{game.chosen_first_letter.upper()}</code>"
    elif game.required_letter:
        extra += f"\n🎯 <b>ꜱᴛᴀʀᴛɪɴɢ ʟᴇᴛᴛᴇʀ:</b> <code>{game.required_letter.upper()}</code>"
    if game.banned_letters:
        extra += (
            f"\n🚫 <b>ʙᴀɴɴᴇᴅ:</b> <code>"
            f"{', '.join(sorted(x.upper() for x in game.banned_letters))}</code>"
        )
    if game.required_letter_anywhere:
        extra += f"\n🔠 <b>ʀᴇQᴜɪʀᴇᴅ ᴀɴʏᴡʜᴇʀᴇ:</b> <code>{game.required_letter_anywhere.upper()}</code>"

    text = (
        f"🔗 <b>ᴡᴏʀᴅ ᴄʜᴀɪɴ — ɢᴀᴍᴇ ꜱᴛᴀʀᴛᴇᴅ!</b>\n\n"
        f"🎮 <b>ᴍᴏᴅᴇ:</b> {game.cfg['label']}\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b> <code>{len(game.players)}</code>\n"
        f"⏱ <b>ᴛᴜʀɴ ᴛɪᴍᴇ:</b> <code>{game.current_turn_seconds()}s</code>\n"
        f"📏 <b>ᴡᴏʀᴅ ʟᴇɴɢᴛʜ:</b> <code>{game.current_min_len()}-{game.cfg['max_word_len']}</code>"
        f"{extra}\n\n"
        f"<b>ᴛᴜʀɴ ᴏʀᴅᴇʀ:</b>\n{order_mentions}"
    )
    await _safe_send(chat_id, text, parse_mode=ParseMode.HTML)

    await persist_game(game)
    await _start_turn(chat_id, game)


async def _setup_mode_rules(game: WordChainGame):
    if game.mode == MODE_BANNED:
        game.banned_letters = set(random.sample("abcdefghijklmnopqrstuvwxyz", 2))
    elif game.mode == MODE_REQUIRED:
        vowels = list("aeiou")
        cons = list("bcdfghjklmnprstvwyz")
        game.required_letter = random.choice(cons).upper()
        game.required_letter_anywhere = random.choice(vowels).upper()
    elif game.mode == MODE_RANDOM:
        game.required_letter = random.choice("abcdefghijklmnopqrstuvwxyz").upper()
    elif game.mode == MODE_CHOSEN:
        game.required_letter = random.choice("abcdefghijklmnopqrstuvwxyz").upper()
    elif game.mode == MODE_MIXED:
        game.banned_letters = set(random.sample("abcdefghijklmnopqrstuvwxyz", 1))
        game.required_letter_anywhere = random.choice("aeiou").upper()
    elif game.mode == MODE_CHAOS:
        await _roll_chaos_event(game)


async def _roll_chaos_event(game: WordChainGame):
    if not game.chaos_events:
        ev = random.choice([
            {"name": "🚫 ʙᴀɴɴᴇᴅ ʟᴇᴛᴛᴇʀ", "kind": "banned",
             "letter": random.choice("abcdefghijklmnopqrstuvwxyz").upper(),
             "desc": "ʟᴇᴛᴛᴇʀ ɴᴏᴛ ᴀʟʟᴏᴡᴇᴅ", "turns_left": 3},
            {"name": "🔠 ʀᴇQᴜɪʀᴇᴅ ʟᴇᴛᴛᴇʀ", "kind": "required",
             "letter": random.choice("aeiou").upper(),
             "desc": "ᴍᴜꜱᴛ ᴄᴏɴᴛᴀɪɴ ᴛʜɪꜱ ʟᴇᴛᴛᴇʀ", "turns_left": 3},
            {"name": "📏 ʟᴏɴɢᴇʀ ᴡᴏʀᴅꜱ", "kind": "min_len_up",
             "value": 6, "desc": "ᴍɪɴɪᴍᴜᴍ 6 ʟᴇᴛᴛᴇʀꜱ", "turns_left": 3},
            {"name": "⏱ ꜰᴀꜱᴛᴇʀ ᴛᴜʀɴꜱ", "kind": "timer_down",
             "value": 15, "desc": "15ꜱ ᴛᴜʀɴ", "turns_left": 3},
        ])
        game.chaos_events = [ev]
        return ev
    else:
        for ev in game.chaos_events:
            ev["turns_left"] = ev.get("turns_left", 0) - 1
        game.chaos_events = [e for e in game.chaos_events if e["turns_left"] > 0]
        if not game.chaos_events:
            return await _roll_chaos_event(game)
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  TURN MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
async def _start_turn(chat_id: int, game: WordChainGame):
    if game.status != "running":
        return

    current = game.current_player()
    if not current:
        await _finish_game(chat_id, game, reason="ɴᴏ ᴘʟᴀʏᴇʀꜱ ʟᴇꜰᴛ")
        return

    game.turn_started_by_player = current["user_id"]

    # ✅ Dynamic timer
    turn_secs = game.current_turn_seconds()

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    text = _render_turn(game, turn_secs)
    if game.board_message_id:
        edited = await _safe_edit(
            chat_id, game.board_message_id, text,
            parse_mode=ParseMode.HTML,
        )
        if not edited:
            sent = await _safe_send(chat_id, text, parse_mode=ParseMode.HTML)
            if sent:
                game.board_message_id = sent.id
    else:
        sent = await _safe_send(chat_id, text, parse_mode=ParseMode.HTML)
        if sent:
            game.board_message_id = sent.id

    game.turn_task = asyncio.create_task(
        _turn_timeout(chat_id, game, current["user_id"], turn_secs)
    )
    await persist_game(game)


async def _turn_timeout(chat_id: int, game: WordChainGame, expected_player: int, seconds: int):
    """✅ Timeout — eliminates player, advances to next alive player."""
    try:
        await asyncio.sleep(seconds)

        # ✅ Acquire lock for atomic check-and-eliminate
        lock = _game_lock(chat_id)
        async with lock:
            if game.status != "running":
                return
            if game.turn_started_by_player != expected_player:
                return
            current = game.current_player()
            if not current or current["user_id"] != expected_player:
                return

            game.eliminate(expected_player)
            p = game.get_player(expected_player) or {"name": "Player"}
            remaining = len(game.alive_players())

        # Send elimination message outside lock
        await _safe_send(
            chat_id,
            f"❌ <b>ᴘʟᴀʏᴇʀ ᴇʟɪᴍɪɴᴀᴛᴇᴅ</b>\n\n"
            f"👤 {_mention(expected_player, p['name'])}\n"
            f"⏰ <i>ʀᴇᴀꜱᴏɴ:</i> ᴛᴜʀɴ ᴛɪᴍᴇᴅ ᴏᴜᴛ\n"
            f"👥 <b>ʀᴇᴍᴀɪɴɪɴɢ:</b> <code>{remaining}</code>",
            parse_mode=ParseMode.HTML,
        )

        winner = game.check_winner()
        if winner:
            await _finish_game(chat_id, game, winner=winner)
            return
        if remaining == 0:
            await _finish_game(chat_id, game, reason="ᴀʟʟ ᴘʟᴀʏᴇʀꜱ ᴇʟɪᴍɪɴᴀᴛᴇᴅ")
            return

        # ✅ Advance to next alive player
        game.next_turn()
        await _start_turn(chat_id, game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[WordChain turn timeout] {type(e).__name__}: {e}", flush=True)


async def _finish_game(chat_id: int, game: WordChainGame, winner: dict = None, reason: str = ""):
    if game.status == "finished":
        return
    game.cancel_timers()

    if winner:
        game.finish(winner_id=winner["user_id"], winner_name=winner["name"])
    else:
        game.finish()

    total_words = len(game.used_words)
    longest = max(game.used_words, key=len) if game.used_words else ""

    for p in game.players:
        won = winner is not None and p["user_id"] == winner["user_id"]
        points = compute_points(
            game.mode,
            word_count=total_words if won else 0,
            longest_word_len=len(longest) if won else 0,
            won=won,
        ) if won else 0

        try:
            await record_result(
                user_id=p["user_id"],
                username="",
                first_name=p["name"],
                won=won,
                word_count=total_words if won else 0,
                longest_word=longest if won else "",
                points=points,
                mode=game.mode,
            )
        except Exception as e:
            print(f"[WordChain record] {type(e).__name__}: {e}", flush=True)

    if winner:
        # ✅ Longest word with size
        text = (
            f"🎉 <b>ᴡᴇ ʜᴀᴠᴇ ᴀ ᴡɪɴɴᴇʀ!</b> 🎉\n\n"
            f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {_mention(winner['user_id'], winner['name'])}\n"
            f"🎮 <b>ᴍᴏᴅᴇ:</b> {game.cfg['label']}\n"
            f"📝 <b>ᴛᴏᴛᴀʟ ᴡᴏʀᴅꜱ:</b> <code>{total_words}</code>\n"
            f"🔑 <b>ʟᴏɴɢᴇꜱᴛ ᴡᴏʀᴅ:</b> <code>{_esc(longest.upper())}</code> "
            f"<i>({len(longest)} ʟᴇᴛᴛᴇʀꜱ)</i>\n\n"
            f"👉 ᴘʟᴀʏ ᴀɢᴀɪɴ: <code>/startchain</code>"
        )
    else:
        text = (
            f"⏹ <b>ɢᴀᴍᴇ ᴏᴠᴇʀ</b>\n\n"
            f"<i>{_esc(reason) or 'ɴᴏ ᴡɪɴɴᴇʀ'}</i>\n\n"
            f"👉 ᴘʟᴀʏ ᴀɢᴀɪɴ: <code>/startchain</code>"
        )
    await _safe_send(chat_id, text, parse_mode=ParseMode.HTML)

    remove_game(chat_id)
    try:
        await remove_persisted_game(chat_id)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["startchain"], prefixes=PREFIXES) & filters.group)
async def cmd_startchain(_, message: Message):
    if not _is_group(message):
        return await _safe_reply(
            message,
            "❌ ᴡᴏʀᴅ ᴄʜᴀɪɴ ᴏɴʟʏ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ.",
            parse_mode=ParseMode.HTML,
        )
    if not message.from_user:
        return

    await ensure_dictionary_loaded()

    existing = get_game(message.chat.id)
    if existing and existing.status in ("lobby", "running"):
        return await _safe_reply(
            message,
            "⚠️ <b>ᴀ ɢᴀᴍᴇ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ɪɴ ᴛʜɪꜱ ᴄʜᴀᴛ!</b>\n"
            "<i>ᴜꜱᴇ</i> <code>/killchain</code> <i>ᴛᴏ ᴄᴀɴᴄᴇʟ ɪᴛ.</i>",
            parse_mode=ParseMode.HTML,
        )

    args = list(message.command or [])[1:]
    mode = MODE_CLASSIC
    if args:
        key = args[0].lower().strip()
        mode = MODE_ALIASES.get(key, MODE_CLASSIC)

    game = create_game(
        chat_id=message.chat.id,
        mode=mode,
        starter_id=message.from_user.id,
        starter_name=_user_display(message.from_user),
    )
    game.add_player(message.from_user.id, _user_display(message.from_user))
    USER_ACTIVE[message.from_user.id] = message.chat.id

    try:
        await ensure_stats(
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
        )
    except Exception:
        pass

    cfg = game.cfg
    sent = await _safe_send(
        message.chat.id,
        _render_lobby(game, cfg["lobby_seconds"]),
        parse_mode=ParseMode.HTML,
        reply_markup=_lobby_kb(game),
    )
    if sent:
        game.lobby_message_id = sent.id

    await persist_game(game)

    game.lobby_task = asyncio.create_task(_run_lobby_timer(message.chat.id, game))


@app.on_message(filters.command(["joinchain"], prefixes=PREFIXES) & filters.group)
async def cmd_joinchain(_, message: Message):
    await _join_game(_, message)


@app.on_message(filters.command(["leavechain", "fleechain"], prefixes=PREFIXES) & filters.group)
async def cmd_leavechain(_, message: Message):
    await _leave_game(_, message)


async def _join_game(_, message: Message):
    if not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game or game.status != "lobby":
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.", parse_mode=ParseMode.HTML)

    if game.has_player(message.from_user.id):
        return await _safe_reply(message, "⚠️ ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜᴇ ʟᴏʙʙʏ.", parse_mode=ParseMode.HTML)

    other = get_user_game(message.from_user.id)
    if other and other.chat_id != message.chat.id:
        return await _safe_reply(
            message,
            "⚠️ ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀɴᴏᴛʜᴇʀ ɢᴀᴍᴇ!",
            parse_mode=ParseMode.HTML,
        )

    if game.is_full():
        return await _safe_reply(message, "❌ ʟᴏʙʙʏ ɪꜱ ꜰᴜʟʟ.", parse_mode=ParseMode.HTML)

    if not game.add_player(message.from_user.id, _user_display(message.from_user)):
        return await _safe_reply(message, "❌ ᴄᴀɴ'ᴛ ᴊᴏɪɴ.", parse_mode=ParseMode.HTML)

    USER_ACTIVE[message.from_user.id] = message.chat.id
    try:
        await ensure_stats(
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
        )
    except Exception:
        pass

    if game.lobby_message_id:
        await _safe_edit(
            message.chat.id, game.lobby_message_id,
            _render_lobby(game, game.cfg["lobby_seconds"]),
            parse_mode=ParseMode.HTML,
            reply_markup=_lobby_kb(game),
        )
    try:
        await message.delete()
    except Exception:
        pass

    if game.is_full():
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _begin_game(message.chat.id, game)


async def _leave_game(_, message: Message):
    if not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)

    if game.status == "lobby":
        if not game.has_player(message.from_user.id):
            return await _safe_reply(message, "⚠️ ʏᴏᴜ'ʀᴇ ɴᴏᴛ ɪɴ ᴛʜᴇ ʟᴏʙʙʏ.", parse_mode=ParseMode.HTML)
        game.remove_player(message.from_user.id)
        USER_ACTIVE.pop(message.from_user.id, None)

        if game.lobby_message_id:
            await _safe_edit(
                message.chat.id, game.lobby_message_id,
                _render_lobby(game, game.cfg["lobby_seconds"]),
                parse_mode=ParseMode.HTML,
                reply_markup=_lobby_kb(game),
            )
        await _safe_reply(message, "👋 ʟᴇꜰᴛ ᴛʜᴇ ʟᴏʙʙʏ.", parse_mode=ParseMode.HTML)

    elif game.status == "running":
        game.eliminate(message.from_user.id)
        USER_ACTIVE.pop(message.from_user.id, None)
        await _safe_reply(message, "🏳️ ʏᴏᴜ ʟᴇꜰᴛ ᴛʜᴇ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)
        winner = game.check_winner()
        if winner:
            await _finish_game(message.chat.id, game, winner=winner)


@app.on_message(filters.command(["extendchain"], prefixes=PREFIXES) & filters.group)
async def cmd_extendchain(_, message: Message):
    game = get_game(message.chat.id)
    if not game or game.status != "lobby":
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.", parse_mode=ParseMode.HTML)
    if not message.from_user:
        return
    if message.from_user.id != game.starter_id and not await _is_admin(message.chat.id, message.from_user.id):
        return await _safe_reply(message, "❌ ᴏɴʟʏ ꜱᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴ.", parse_mode=ParseMode.HTML)
    await _safe_reply(message, "⏱ ʟᴏʙʙʏ ɴᴏᴛ ᴇxᴛᴇɴᴅᴇᴅ (ꜰᴇᴀᴛᴜʀᴇ ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀ).", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["forcestartchain"], prefixes=PREFIXES) & filters.group)
async def cmd_forcestartchain(_, message: Message):
    game = get_game(message.chat.id)
    if not game or game.status != "lobby":
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.", parse_mode=ParseMode.HTML)
    if not message.from_user:
        return
    if message.from_user.id != game.starter_id and not await _is_admin(message.chat.id, message.from_user.id):
        return await _safe_reply(message, "❌ ᴏɴʟʏ ꜱᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴ.", parse_mode=ParseMode.HTML)
    if not game.can_start():
        return await _safe_reply(
            message,
            f"❌ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀꜱᴛ <code>{game.cfg['min_players']}</code> ᴘʟᴀʏᴇʀꜱ.",
            parse_mode=ParseMode.HTML,
        )
    if game.lobby_task and not game.lobby_task.done():
        game.lobby_task.cancel()
    await _begin_game(message.chat.id, game)


@app.on_message(filters.command(["forcejoinchain"], prefixes=PREFIXES) & filters.group)
async def cmd_forcejoinchain(_, message: Message):
    game = get_game(message.chat.id)
    if not game or game.status != "lobby":
        return
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await _safe_reply(message, "❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ.", parse_mode=ParseMode.HTML)
    if game.has_player(target.id):
        return await _safe_reply(message, "⚠️ ᴀʟʀᴇᴀᴅʏ ɪɴ.", parse_mode=ParseMode.HTML)
    game.add_player(target.id, _user_display(target))
    USER_ACTIVE[target.id] = message.chat.id
    await _safe_reply(message, f"✅ {_mention(target.id, _user_display(target))} ꜰᴏʀᴄᴇ-ᴊᴏɪɴᴇᴅ.", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["forceleavechain"], prefixes=PREFIXES) & filters.group)
async def cmd_forceleavechain(_, message: Message):
    game = get_game(message.chat.id)
    if not game:
        return
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await _safe_reply(message, "❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ.", parse_mode=ParseMode.HTML)
    if not game.has_player(target.id):
        return await _safe_reply(message, "⚠️ ɴᴏᴛ ɪɴ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)
    game.remove_player(target.id)
    USER_ACTIVE.pop(target.id, None)
    await _safe_reply(message, f"✅ ʀᴇᴍᴏᴠᴇᴅ {_mention(target.id, _user_display(target))}.", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["forceskipchain"], prefixes=PREFIXES) & filters.group)
async def cmd_forceskipchain(_, message: Message):
    game = get_game(message.chat.id)
    if not game or game.status != "running":
        return
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return
    game.next_turn()
    await _safe_reply(message, "⏭ ꜱᴋɪᴘᴘᴇᴅ.", parse_mode=ParseMode.HTML)
    await _start_turn(message.chat.id, game)


@app.on_message(filters.command(["killchain"], prefixes=PREFIXES) & filters.group)
async def cmd_killchain(_, message: Message):
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)
    if not message.from_user:
        return
    if message.from_user.id != game.starter_id and not await _is_admin(message.chat.id, message.from_user.id):
        return await _safe_reply(message, "❌ ᴏɴʟʏ ꜱᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴ.", parse_mode=ParseMode.HTML)

    game.cancel()
    game.cancel_timers()
    remove_game(message.chat.id)
    await remove_persisted_game(message.chat.id)
    await _safe_reply(message, "🚫 <b>ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["chaininfo"], prefixes=PREFIXES) & filters.group)
async def cmd_chaininfo(_, message: Message):
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)
    if game.status == "lobby":
        await _safe_reply(
            message,
            _render_lobby(game, game.cfg["lobby_seconds"]),
            parse_mode=ParseMode.HTML,
        )
    else:
        await _safe_reply(
            message,
            _render_turn(game, game.current_turn_seconds()),
            parse_mode=ParseMode.HTML,
        )


@app.on_message(filters.command(["chainstats"], prefixes=PREFIXES))
async def cmd_chainstats(_, message: Message):
    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return
    try:
        doc = await get_stats(target.id)
    except Exception:
        doc = None
    name = target.first_name or target.username or str(target.id)
    if not doc:
        return await _safe_reply(
            message,
            f"📊 <b>{_esc(name)}'ꜱ ᴡᴏʀᴅ ᴄʜᴀɪɴ ꜱᴛᴀᴛꜱ</b>\n\n❌ ɴᴏ ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )
    text = (
        f"📊 <b>{_esc(name)}'ꜱ ᴡᴏʀᴅ ᴄʜᴀɪɴ ꜱᴛᴀᴛꜱ</b>\n\n"
        f"🎮 <b>ɢᴀᴍᴇꜱ:</b> <code>{int(doc.get('games_played', 0))}</code>\n"
        f"🏆 <b>ᴡᴏɴ:</b> <code>{int(doc.get('games_won', 0))}</code>\n"
        f"❌ <b>ʟᴏꜱᴛ:</b> <code>{int(doc.get('games_lost', 0))}</code>\n"
        f"📝 <b>ᴡᴏʀᴅꜱ ꜱᴜʙᴍɪᴛᴛᴇᴅ:</b> <code>{int(doc.get('words_submitted', 0))}</code>\n"
        f"🔑 <b>ʟᴏɴɢᴇꜱᴛ ᴡᴏʀᴅ:</b> <code>{_esc(str(doc.get('longest_word', '') or '—').upper())}</code>\n"
        f"⭐ <b>ᴘᴏɪɴᴛꜱ:</b> <code>{int(doc.get('points', 0))}</code>\n"
        f"🔥 <b>ꜱᴛʀᴇᴀᴋ:</b> <code>{int(doc.get('win_streak', 0))}</code>\n"
        f"🏅 <b>ʙᴇꜱᴛ ꜱᴛʀᴇᴀᴋ:</b> <code>{int(doc.get('best_streak', 0))}</code>"
    )
    await _safe_reply(message, text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["chaintop", "chainleaderboard"], prefixes=PREFIXES))
async def cmd_chaintop(_, message: Message):
    try:
        rows = await top_players(10)
    except Exception:
        rows = []
    if not rows:
        return await _safe_reply(
            message,
            "🏆 <b>ᴡᴏʀᴅ ᴄʜᴀɪɴ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n❌ ɴᴏ ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>ᴡᴏʀᴅ ᴄʜᴀɪɴ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        name = row.get("first_name") or row.get("username") or str(row["_id"])
        pts = int(row.get("points", 0))
        wins = int(row.get("games_won", 0))
        lines.append(f"{rank} <b>{_esc(name)}</b> — <code>{pts}</code> ᴘᴛꜱ • <code>{wins}</code> ᴡɪɴꜱ")
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["chainhelp", "wordchainhelp"], prefixes=PREFIXES))
async def cmd_chainhelp(_, message: Message):
    await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["playingchains"], prefixes=PREFIXES))
async def cmd_playingchains(_, message: Message):
    if not message.from_user:
        return
    import config
    if int(message.from_user.id) != int(getattr(config, "OWNER_ID", 0)):
        return
    if not ACTIVE_GAMES:
        return await _safe_reply(message, "📭 ɴᴏ ᴀᴄᴛɪᴠᴇ ᴡᴏʀᴅ ᴄʜᴀɪɴ ɢᴀᴍᴇꜱ.", parse_mode=ParseMode.HTML)
    lines = ["🎮 <b>ᴀᴄᴛɪᴠᴇ ᴡᴏʀᴅ ᴄʜᴀɪɴ ɢᴀᴍᴇꜱ</b>\n"]
    for cid, g in ACTIVE_GAMES.items():
        lines.append(
            f"• <code>{cid}</code> — {g.cfg['label']} — "
            f"<code>{g.status}</code> — <code>{len(g.players)}</code> ᴘʟᴀʏᴇʀꜱ"
        )
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^wc_"))
async def wordchain_cb(_, query: CallbackQuery):
    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) != 2:
        return
    action = parts[0]
    try:
        chat_id = int(parts[1])
    except ValueError:
        return

    game = get_game(chat_id)
    if not game:
        return await query.answer("❌ ɢᴀᴍᴇ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴄᴛɪᴠᴇ.", show_alert=True)

    if action == "wc_join":
        if game.status != "lobby":
            return await query.answer("❌ ʟᴏʙʙʏ ᴄʟᴏꜱᴇᴅ.", show_alert=True)
        if game.has_player(query.from_user.id):
            return await query.answer("⚠️ ᴀʟʀᴇᴀᴅʏ ɪɴ!", show_alert=True)
        if game.is_full():
            return await query.answer("❌ ʟᴏʙʙʏ ꜰᴜʟʟ.", show_alert=True)

        other = get_user_game(query.from_user.id)
        if other and other.chat_id != chat_id:
            return await query.answer("⚠️ ʏᴏᴜ'ʀᴇ ɪɴ ᴀɴᴏᴛʜᴇʀ ɢᴀᴍᴇ!", show_alert=True)

        game.add_player(query.from_user.id, _user_display(query.from_user))
        USER_ACTIVE[query.from_user.id] = chat_id
        try:
            await ensure_stats(
                query.from_user.id,
                query.from_user.username or "",
                query.from_user.first_name or "",
            )
        except Exception:
            pass
        await query.answer("✅ ᴊᴏɪɴᴇᴅ!")

        if game.lobby_message_id:
            await _safe_edit(
                chat_id, game.lobby_message_id,
                _render_lobby(game, game.cfg["lobby_seconds"]),
                parse_mode=ParseMode.HTML,
                reply_markup=_lobby_kb(game),
            )

        if game.is_full():
            if game.lobby_task and not game.lobby_task.done():
                game.lobby_task.cancel()
            await _begin_game(chat_id, game)
        return

    if action == "wc_leave":
        if game.status != "lobby":
            return await query.answer("❌ ᴄᴀɴ'ᴛ ʟᴇᴀᴠᴇ ɴᴏᴡ.", show_alert=True)
        if not game.has_player(query.from_user.id):
            return await query.answer("⚠️ ɴᴏᴛ ɪɴ ʟᴏʙʙʏ.", show_alert=True)
        game.remove_player(query.from_user.id)
        USER_ACTIVE.pop(query.from_user.id, None)
        await query.answer("👋 ʟᴇꜰᴛ.")
        if game.lobby_message_id:
            await _safe_edit(
                chat_id, game.lobby_message_id,
                _render_lobby(game, game.cfg["lobby_seconds"]),
                parse_mode=ParseMode.HTML,
                reply_markup=_lobby_kb(game),
            )
        return

    if action == "wc_rules":
        return await query.answer(
            "🔗 Word Chain: each word must start with the last letter of the previous word. "
            "Type words in the group when it's your turn. "
            "Invalid words don't count. Timeout = eliminated!",
            show_alert=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GUESS LISTENER
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.group & filters.text, group=20)
async def wordchain_guess(_, message: Message):
    if not message.from_user or not message.text:
        return
    text = message.text.strip()
    if not text or text[0] in PREFIXES:
        return
    if message.from_user.is_bot:
        return

    game = get_game(message.chat.id)
    if not game or game.status != "running":
        return

    if " " in text:
        return
    word = text.strip()
    if not word.isalpha():
        return

    current = game.current_player()
    if not current or current["user_id"] != message.from_user.id:
        return

    if not _track(message.id):
        return

    lock = _game_lock(message.chat.id)
    async with lock:
        game = get_game(message.chat.id)
        if not game or game.status != "running":
            return
        current = game.current_player()
        if not current or current["user_id"] != message.from_user.id:
            return

        # ✅ CRITICAL: Cancel timer immediately on player input
        if game.turn_task and not game.turn_task.done():
            game.turn_task.cancel()
            game.turn_task = None

        ok, reason = game.validate_word(word, message.from_user.id)
        if not ok:
            if reason.startswith("must_start_with:"):
                req = reason.split(":", 1)[1]
                msg = f"❌ ᴡᴏʀᴅ ᴍᴜꜱᴛ ꜱᴛᴀʀᴛ ᴡɪᴛʜ <code>{req}</code>"
            elif reason.startswith("banned_letter:"):
                ltr = reason.split(":", 1)[1]
                msg = f"🚫 ʟᴇᴛᴛᴇʀ <code>{ltr}</code> ɪꜱ ʙᴀɴɴᴇᴅ"
            elif reason.startswith("required_letter:"):
                ltr = reason.split(":", 1)[1]
                msg = f"🔠 ᴡᴏʀᴅ ᴍᴜꜱᴛ ᴄᴏɴᴛᴀɪɴ <code>{ltr}</code>"
            elif reason.startswith("too_short"):
                msg = f"❌ ᴡᴏʀᴅ ᴛᴏᴏ ꜱʜᴏʀᴛ ({reason})"
            elif reason.startswith("too_long"):
                msg = f"❌ ᴡᴏʀᴅ ᴛᴏᴏ ʟᴏɴɢ ({reason})"
            elif reason == "already_used":
                msg = "⚠️ ᴛʜɪꜱ ᴡᴏʀᴅ ᴡᴀꜱ ᴀʟʀᴇᴀᴅʏ ᴜꜱᴇᴅ"
            elif reason == "not_in_dictionary":
                msg = f"❌ <code>{_esc(word.upper())}</code> ɴᴏᴛ ɪɴ ᴅɪᴄᴛɪᴏɴᴀʀʏ"
            else:
                msg = f"❌ ɪɴᴠᴀʟɪᴅ ᴡᴏʀᴅ ({reason})"
            await _safe_reply(message, msg, parse_mode=ParseMode.HTML)

            # ✅ Restart timer with current turn seconds
            restart_secs = game.current_turn_seconds()
            game.turn_task = asyncio.create_task(
                _turn_timeout(message.chat.id, game, message.from_user.id, restart_secs)
            )
            return

        # Valid!
        game.apply_word(word, message.from_user.id)
        game.round_no += 1

        # Chaos: reroll periodically
        if game.mode == MODE_CHAOS and game.round_no % 3 == 0:
            new_ev = await _roll_chaos_event(game)
            if new_ev:
                await _safe_send(
                    message.chat.id,
                    f"🌪 <b>ᴄʜᴀᴏꜱ ᴇᴠᴇɴᴛ:</b> {new_ev['name']}\n"
                    f"<i>{new_ev.get('desc', '')}</i>",
                    parse_mode=ParseMode.HTML,
                )

        # Advance turn
        game.next_turn()
        next_player = game.current_player()

        if next_player:
            next_player_line = (
                f"➡️ <b>ɴᴇxᴛ ᴘʟᴀʏᴇʀ:</b> "
                f"{_mention(next_player['user_id'], next_player['name'])}"
            )
        else:
            next_player_line = "➡️ <b>ɴᴇxᴛ ᴘʟᴀʏᴇʀ:</b> <i>—</i>"

        next_letter = word[-1].upper()

        # ✅ ACCEPTED message with next player + progression info
        new_min = game.current_min_len()
        new_time = game.current_turn_seconds()
        await _safe_reply(
            message,
            f"✅ <b>ᴀᴄᴄᴇᴘᴛᴇᴅ!</b>\n\n"
            f"👤 <b>ᴘʟᴀʏᴇʀ:</b> {_mention(message.from_user.id, _user_display(message.from_user))}\n"
            f"📝 <b>ᴡᴏʀᴅ:</b> <code>{_esc(word.upper())}</code>\n"
            f"🔤 <b>ɴᴇxᴛ ʟᴇᴛᴛᴇʀ:</b> <code>{next_letter}</code>\n"
            f"{next_player_line}\n"
            f"📏 <b>ᴍɪɴ ʟᴇɴɢᴛʜ:</b> <code>{new_min}</code> • "
            f"⏱ <b>ᴛɪᴍᴇʀ:</b> <code>{new_time}s</code>",
            parse_mode=ParseMode.HTML,
        )

        # Continue next turn
        await _start_turn(message.chat.id, game)
