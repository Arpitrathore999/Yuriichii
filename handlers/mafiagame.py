# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/mafiagame.py — 🎭 MAFIA Telegram handlers
#  ✅ FIXED: freeze bug, Doctor role, DM join deep-link
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pyrogram import StopPropagation, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from core.bot import app
from core.database import add_coins, add_xp, get_user, remove_coins
from core.mafia_engine import (
    ACTIVE_GAMES,
    DAY_SECONDS,
    ENTRY_MAX,
    ENTRY_MIN,
    GAME_FEE_PERCENT,
    LOBBY_SECONDS,
    LOSER_XP,
    MAX_PLAYERS,
    MIN_PLAYERS,
    NIGHT_SECONDS,
    ROLE_DETECTIVE,
    ROLE_DOCTOR,
    ROLE_EMOJI,
    ROLE_LABEL,
    ROLE_MAFIA,
    ROLE_VILLAGER,
    ROLE_WITCH,
    STATE_CANCELLED,
    STATE_DAY,
    STATE_FINISHED,
    STATE_LOBBY,
    STATE_NIGHT,
    STATE_VOTING,
    USER_ACTIVE,
    VOTE_SECONDS,
    WINNER_XP,
    MafiaGame,
    bump_detective_catches,
    bump_doctor_saves,
    bump_mafia_kills,
    create_game,
    ensure_stats,
    get_game,
    get_stats,
    get_user_game,
    persist_game,
    record_result,
    remove_game,
    remove_persisted_game,
    top_players,
)

PREFIXES = ["/", "!", "."]
ELARA_BOT_ID = 8899359004
BOT_USERNAME = (getattr(config, "BOT_USERNAME", "") or "ItzElaraBot").lstrip("@")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mention(uid: int, name: str) -> str:
    return f'<a href="tg://user?id={int(uid)}">{_esc(name)}</a>'


def _name(user) -> str:
    return (getattr(user, "first_name", None) or
            getattr(user, "username", None) or
            str(getattr(user, "id", "User")))


def _is_group(message: Message) -> bool:
    return message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def _safe_send(chat_id, text, **kw):
    try:
        return await app.send_message(chat_id, text, **kw)
    except Exception as e:
        if type(e).__name__ == "FloodWait":
            return None
        print(f"[Mafia send] {type(e).__name__}: {e}", flush=True)
        return None


async def _safe_reply(message: Message, text, **kw):
    try:
        return await message.reply(text, **kw)
    except Exception:
        return await _safe_send(message.chat.id, text, **kw)


async def _safe_edit(chat_id, msg_id, text, **kw):
    try:
        return await app.edit_message_text(chat_id, msg_id, text, **kw)
    except Exception as e:
        if type(e).__name__ in ("MessageNotModified", "FloodWait"):
            return None
        return None


async def _safe_dm(uid: int, text, **kw):
    try:
        return await app.send_message(int(uid), text, **kw)
    except Exception as e:
        print(f"[Mafia DM] {type(e).__name__}: {e}", flush=True)
        return None


async def _get_balance(uid: int) -> int:
    try:
        doc = await get_user(int(uid))
        if not doc:
            return 0
        return int(doc.get("coins", 0) or 0)
    except Exception:
        return 0


async def _ensure_user_record(uid: int, name: str = ""):
    try:
        from database.users import ensure_user
        class _U:
            id = int(uid)
            first_name = name or "User"
            username = None
            is_bot = False
            language_code = "en"
        await ensure_user(_U())
    except Exception as e:
        print(f"[Mafia ensure_user] {type(e).__name__}: {e}", flush=True)


async def _credit_elara(amount: int) -> bool:
    if amount <= 0:
        return False
    try:
        from database.mongo import users as users_col
        col = users_col()
        if col is None:
            return False
        await col.update_one(
            {"_id": int(ELARA_BOT_ID)},
            {"$inc": {"coins": int(amount)},
             "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[Mafia tax] {type(e).__name__}: {e}", flush=True)
        return False


async def _payout_winner(uid: int, amount: int) -> bool:
    if amount <= 0:
        return False
    try:
        ok = await add_coins(int(uid), int(amount))
        if ok:
            return True
    except Exception as e:
        print(f"[Mafia payout] add_coins {type(e).__name__}: {e}", flush=True)

    try:
        from database.mongo import users as users_col
        col = users_col()
        if col is None:
            return False
        r = await col.update_one(
            {"_id": int(uid)},
            {"$inc": {"coins": int(amount)},
             "$set": {"updated_at": datetime.now(timezone.utc)},
             "$setOnInsert": {"_id": int(uid), "first_name": "", "username": ""}},
            upsert=True,
        )
        return r.modified_count == 1 or r.upserted_id is not None
    except Exception as e:
        print(f"[Mafia payout fallback] {type(e).__name__}: {e}", flush=True)
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  RENDERERS
# ══════════════════════════════════════════════════════════════════════════════
def _render_help() -> str:
    return (
        "🎭 <b>MAFIA — The Social Deduction Game</b>\n\n"
        "One Mafia hides among the Villagers and kills one player each night.\n"
        "The Villagers must vote to find the Mafia! 🔪\n\n"
        "<b>🎮 QUICK START:</b>\n"
        "• <code>/mafia free</code> — start a free game\n"
        "• <code>/mafia 500</code> — start a paid game (500 coins entry)\n"
        "• <code>/joinmafia</code> — join the lobby\n\n"
        "📖 Full rules & commands: <code>/mafiahelp</code>\n"
    )


def _render_mafia_help() -> str:
    return (
        "🎭 <b>MAFIA — HOW TO PLAY & COMMANDS</b> 🎭\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📖 <b>HOW TO PLAY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "<b>1️⃣ LOBBY</b>\n"
        "• A player starts a game with <code>/mafia free</code> or <code>/mafia 500</code>\n"
        "• Others join with <code>/joinmafia</code> or the <b>JOIN</b> button\n"
        "• 4–12 players required (60s to fill)\n\n"

        "<b>2️⃣ ROLES ARE SENT VIA DM</b>\n"
        "• Each player gets a secret role privately\n"
        "• 🔪 <b>Mafia</b> picks a target to kill each night\n"
        "• 🕵️ <b>Detective</b> investigates 1 player each night\n"
        "• 👨‍⚕️ <b>Doctor</b> protects 1 player from being killed\n"
        "• 🧙 <b>Witch</b> (6+ players) — heals or kills once\n"
        "• 👥 <b>Villagers</b> have no night action\n\n"

        "<b>3️⃣ NIGHT PHASE</b> 🌙 (30s)\n"
        "• Mafia kills · Detective checks · Doctor saves\n\n"

        "<b>4️⃣ DAY PHASE</b> ☀️ (45s)\n"
        "• Bot announces the kill (or save!)\n"
        "• Everyone discusses who might be Mafia\n\n"

        "<b>5️⃣ VOTING PHASE</b> 🗳️ (30s)\n"
        "• All alive players vote via buttons\n"
        "• Highest voted player is lynched (tie = no lynch)\n\n"

        "<b>6️⃣ REPEAT</b> 🔁\n"
        "• Night → Day → Vote until one side wins\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎭 <b>ROLES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔪 <b>Mafia</b> — Kills one player each night\n"
        "🕵️ <b>Detective</b> — Learns one player's role each night\n"
        "👨‍⚕️ <b>Doctor</b> — Protects one player each night (can self-protect)\n"
        "🧙 <b>Witch</b> — Has 1 heal + 1 kill potion (6+ players)\n"
        "👥 <b>Villager</b> — Discusses and votes\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>WIN CONDITIONS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ <b>Villagers win</b> — Mafia is lynched or killed\n"
        "✅ <b>Mafia wins</b> — Only 1 non-mafia left alive\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>MODES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎮 <b>Free mode</b> — No entry, only XP\n"
        f"💰 <b>Paid mode</b> — {ENTRY_MIN}–{ENTRY_MAX} coins\n"
        "🏆 Winners split the net pool (10% tax)\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>COMMANDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🎮 <b>Game</b>\n"
        "• <code>/mafia free</code> — start free game\n"
        "• <code>/mafia &lt;amount&gt;</code> — start paid game\n"
        "• <code>/joinmafia</code> — join the lobby\n"
        "• <code>/mafiainfo</code> — show status\n"
        "• <code>/mafiacancel</code> — cancel (host only, lobby phase)\n\n"

        "📊 <b>Stats</b>\n"
        "• <code>/mafiastats</code> — your profile\n"
        "• <code>/mafiatop</code> — leaderboard\n\n"

        "📖 <b>Help</b>\n"
        "• <code>/mafiahelp</code> — this message\n\n"

        "💡 <i>Tip: Click the JOIN button in the group — it opens the bot DM to confirm.</i>"
    )


def _render_lobby(game: MafiaGame, secs_left: int) -> str:
    mode = f"💰 PAID — <code>{game.entry_fee}</code> coins/player" if game.is_paid else "🎮 FREE MODE"
    lines = "\n".join(
        f"{i}. {p['mention']}" for i, p in enumerate(game.players, 1)
    ) or "<i>No players yet — be the first!</i>"
    return (
        "🎭 <b>MAFIA — LOBBY OPEN!</b> 🎭\n\n"
        f"🎮 <b>Mode:</b> {mode}\n"
        f"👥 <b>Players:</b> <code>{len(game.players)}/{MAX_PLAYERS}</code> "
        f"<i>(min {MIN_PLAYERS})</i>\n"
        f"⏳ <b>Join time:</b> <code>{max(0, secs_left)}s</code>\n\n"
        f"👤 <b>Players:</b>\n{lines}\n\n"
        "👉 <b>Tap JOIN below</b> (opens DM) or use <code>/joinmafia</code>"
    )


def _lobby_kb(game: MafiaGame) -> InlineKeyboardMarkup:
    """✅ Join button opens bot DM with deep link payload."""
    join_label = (f"➕ JOIN GAME ({game.entry_fee} coins)"
                  if game.is_paid else "➕ JOIN GAME (Free)")
    dm_link = f"https://t.me/{BOT_USERNAME}?start=mafia_join_{game.chat_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(join_label, url=dm_link)],
        [InlineKeyboardButton(
            "❓ How to Play",
            url=f"https://t.me/{BOT_USERNAME}?start=mafia_help",
        )],
    ])


def _render_night_intro(game: MafiaGame) -> str:
    return (
        f"🌙 <b>NIGHT {game.day_no} BEGINS</b>\n\n"
        "The Mafia is hunting...\n"
        "The Detective is investigating...\n"
        "The Doctor is protecting...\n\n"
        "😴 Villagers, sleep tight..."
    )


def _render_day_announce(game: MafiaGame, killed_uid: int | None, was_saved: bool) -> str:
    if was_saved:
        death = ("🩺 <b>THE DOCTOR SAVED A LIFE LAST NIGHT!</b>\n"
                 "<i>The Mafia's attack was blocked.</i>")
    elif killed_uid is None:
        death = "😮 <b>NO ONE DIED LAST NIGHT!</b>"
    else:
        p = game.get_player(killed_uid)
        name = p["mention"] if p else f"<code>{killed_uid}</code>"
        death = f"💀 <b>{name}</b> was killed last night!"

    alive_list = "\n".join(f"• {p['mention']}" for p in game.alive_players())
    return (
        f"☀️ <b>DAY {game.day_no}</b>\n\n"
        f"{death}\n\n"
        f"👥 <b>Alive ({game.alive_count()}):</b>\n{alive_list}\n\n"
        f"🗣 <b>DISCUSSION:</b> Who is the Mafia? 🤔\n"
        f"⏱ <code>{DAY_SECONDS}s</code> to discuss, then voting starts!"
    )


def _vote_kb(game: MafiaGame) -> InlineKeyboardMarkup:
    rows = []
    alive = game.alive_players()
    row = []
    for p in alive:
        row.append(InlineKeyboardButton(
            p["name"],
            callback_data=f"mafia_vote:{game.chat_id}:{p['user_id']}",
        ))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(
        "⏭️ SKIP VOTE",
        callback_data=f"mafia_vote:{game.chat_id}:-1",
    )])
    return InlineKeyboardMarkup(rows)


def _render_voting(game: MafiaGame) -> str:
    return (
        f"🗳️ <b>VOTING TIME — DAY {game.day_no}</b>\n\n"
        "Who should be lynched?\n"
        f"⏱ <code>{VOTE_SECONDS}s</code>\n\n"
        "👇 Vote below! (One vote per player)"
    )


def _render_vote_result(game: MafiaGame, lynched: int | None, counts: dict) -> str:
    if not counts:
        return "🗳️ <b>VOTE RESULT</b>\n\n😮 No votes were cast. Nobody eliminated."

    lines = []
    for uid, c in sorted(counts.items(), key=lambda x: -x[1]):
        p = game.get_player(uid)
        nm = p["name"] if p else str(uid)
        lines.append(f"• <b>{_esc(nm)}</b> — <code>{c}</code> votes")

    header = f"🗳️ <b>VOTE RESULT — DAY {game.day_no}</b>\n\n" + "\n".join(lines)

    if lynched is None:
        return header + "\n\n🤝 <b>TIE!</b> No one was lynched."

    p = game.get_player(lynched)
    nm = p["name"] if p else str(lynched)
    role = game.roles.get(lynched, "?")
    role_emoji = ROLE_EMOJI.get(role, "❔")
    role_label = ROLE_LABEL.get(role, role.upper())

    return (
        header + "\n\n"
        f"💀 <b>{_esc(nm)}</b> was lynched!\n"
        f"🎭 Role: {role_emoji} <b>{role_label}</b>"
    )


def _render_win(game: MafiaGame) -> str:
    if game.winner_side == "villagers":
        return (
            "🎉 <b>VILLAGERS WIN!</b> 🎉\n\n"
            "🔪 The Mafia has been eliminated!\n"
            "👥 The village is safe again."
        )
    return (
        "🔪 <b>MAFIA WINS!</b> 🔪\n\n"
        "💀 The Mafia has taken over the village!\n"
        "😈 No one can stop them now..."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  DEEP-LINK HANDLER  (DM: /start mafia_join_<chat_id> | mafia_help)
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("start", prefixes=PREFIXES) & filters.private, group=-1)
async def mafia_deeplink(_, message: Message):
    if not message.command or len(message.command) < 2:
        return   # let other handlers process

    payload = message.command[1].strip()

    # ── Help deep link ──
    if payload == "mafia_help":
        await _safe_reply(message, _render_mafia_help(), parse_mode=ParseMode.HTML)
        raise StopPropagation

    # ── Join deep link ──
    if not payload.startswith("mafia_join_"):
        return

    try:
        chat_id = int(payload[len("mafia_join_"):])
    except ValueError:
        await _safe_reply(message, "❌ Invalid join link.", parse_mode=ParseMode.HTML)
        raise StopPropagation

    game = get_game(chat_id)
    user = message.from_user

    if not game:
        await _safe_reply(
            message,
            "❌ <b>No active Mafia lobby in that group.</b>\n"
            "<i>The lobby may have closed or been cancelled.</i>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    if game.state != STATE_LOBBY:
        await _safe_reply(
            message,
            "❌ <b>The lobby has already closed.</b>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    if game.has_player(user.id):
        await _safe_reply(
            message,
            "⚠️ <b>Hey, you're already in the game!</b>\n"
            "<i>Wait for the lobby to close and roles to be assigned.</i>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    ok, reason = await _process_join(
        game, user.id,
        _name(user),
        _mention(user.id, _name(user)),
    )

    if not ok:
        await _safe_reply(
            message,
            f"❌ <b>Could not join:</b> {_esc(reason)}",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    # ✅ Success → confirm in DM
    await _safe_reply(
        message,
        f"✅ <b>You joined the Mafia game!</b>\n\n"
        f"📍 Group: <code>{chat_id}</code>\n"
        f"👥 Players: <code>{len(game.players)}/{MAX_PLAYERS}</code>\n\n"
        "🎭 Your role will be sent here once the lobby closes.\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.HTML,
    )

    # ✅ Also announce in group
    await _safe_send(
        game.chat_id,
        f"🔥 {_mention(user.id, _name(user))} joined the game!",
        parse_mode=ParseMode.HTML,
    )

    # Update lobby message in group
    if game.lobby_message_id:
        await _safe_edit(
            game.chat_id, game.lobby_message_id,
            _render_lobby(game, LOBBY_SECONDS),
            parse_mode=ParseMode.HTML, reply_markup=_lobby_kb(game),
        )

    if game.is_full():
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _begin_match(game)

    raise StopPropagation


# ══════════════════════════════════════════════════════════════════════════════
#  /mafiahelp  /mhelp
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["mafiahelp", "mhelp"], prefixes=PREFIXES))
async def mafia_help_cmd(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await _safe_reply(message, _render_mafia_help(), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  /mafia  /mafia <amount>  /mafia free
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["mafia"], prefixes=PREFIXES) & filters.group)
async def mafia_cmd(_, message: Message):
    if not _is_group(message) or not message.from_user:
        return

    args = list(message.command or [])[1:]
    if not args:
        return await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)

    is_paid = True
    entry_fee = 0
    first = args[0].lower().strip()

    if first in ("free", "f", "0"):
        is_paid = False
        entry_fee = 0
    else:
        try:
            entry_fee = int(first)
        except ValueError:
            return await _safe_reply(
                message,
                "❌ <b>Invalid amount.</b>\n"
                "Use <code>/mafia free</code> or <code>/mafia 500</code>.",
                parse_mode=ParseMode.HTML,
            )
        if entry_fee < ENTRY_MIN or entry_fee > ENTRY_MAX:
            return await _safe_reply(
                message,
                f"❌ Entry must be between <code>{ENTRY_MIN}</code> and <code>{ENTRY_MAX}</code>.",
                parse_mode=ParseMode.HTML,
            )

    existing = get_game(message.chat.id)
    if existing and not existing.is_terminal():
        return await _safe_reply(
            message,
            "⚠️ <b>A Mafia game is already running in this chat.</b>",
            parse_mode=ParseMode.HTML,
        )

    user_game = get_user_game(message.from_user.id)
    if user_game and user_game.chat_id != message.chat.id:
        return await _safe_reply(
            message,
            "⚠️ <b>You are in another Mafia game.</b>",
            parse_mode=ParseMode.HTML,
        )

    await _ensure_user_record(message.from_user.id, _name(message.from_user))

    if is_paid:
        bal = await _get_balance(message.from_user.id)
        if bal < entry_fee:
            return await _safe_reply(
                message,
                f"⚡ <b>Insufficient balance.</b>\n"
                f"You have <code>{bal}</code>, need <code>{entry_fee}</code>.",
                parse_mode=ParseMode.HTML,
            )
        ok = await remove_coins(message.from_user.id, entry_fee)
        if not ok:
            return await _safe_reply(message, "❌ Deduct failed.", parse_mode=ParseMode.HTML)

    game = create_game(
        chat_id=message.chat.id,
        host_id=message.from_user.id,
        host_name=_name(message.from_user),
        host_mention=_mention(message.from_user.id, _name(message.from_user)),
        entry_fee=entry_fee,
        is_paid=is_paid,
    )
    game.state = STATE_LOBBY

    game.add_player(message.from_user.id, _name(message.from_user),
                    _mention(message.from_user.id, _name(message.from_user)))
    p = game.get_player(message.from_user.id)
    if p:
        p["paid"] = True
    try:
        await ensure_stats(message.from_user.id, _name(message.from_user))
    except Exception:
        pass

    sent = await _safe_send(
        message.chat.id,
        _render_lobby(game, LOBBY_SECONDS),
        parse_mode=ParseMode.HTML,
        reply_markup=_lobby_kb(game),
    )
    if sent:
        game.lobby_message_id = sent.id
    await persist_game(game)

    game.lobby_task = asyncio.create_task(_lobby_timer(game))


# ══════════════════════════════════════════════════════════════════════════════
#  JOIN (command in group)
# ══════════════════════════════════════════════════════════════════════════════
async def _process_join(game: MafiaGame, uid: int, name: str, mention: str) -> tuple[bool, str]:
    if game.state != STATE_LOBBY:
        return False, "Lobby closed."
    if game.has_player(uid):
        return False, "Already in game."
    if game.is_full():
        return False, "Game is full."

    other = get_user_game(uid)
    if other and other.chat_id != game.chat_id:
        return False, "You are in another Mafia game."

    await _ensure_user_record(uid, name)

    if game.is_paid:
        bal = await _get_balance(uid)
        if bal < game.entry_fee:
            return False, f"Insufficient balance ({bal} < {game.entry_fee})."
        ok = await remove_coins(uid, game.entry_fee)
        if not ok:
            return False, "Payment failed."

    if not game.add_player(uid, name, mention):
        if game.is_paid:
            try:
                await add_coins(uid, game.entry_fee)
            except Exception:
                pass
        return False, "Could not join."

    p = game.get_player(uid)
    if p:
        p["paid"] = True
    USER_ACTIVE[int(uid)] = game.chat_id
    try:
        await ensure_stats(uid, name)
    except Exception:
        pass
    await persist_game(game)
    return True, "ok"


@app.on_message(filters.command(["joinmafia"], prefixes=PREFIXES) & filters.group)
async def mafia_join_cmd(_, message: Message):
    if not _is_group(message) or not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game or game.state != STATE_LOBBY:
        return await _safe_reply(message, "❌ <b>No active lobby.</b>", parse_mode=ParseMode.HTML)

    ok, reason = await _process_join(
        game, message.from_user.id,
        _name(message.from_user),
        _mention(message.from_user.id, _name(message.from_user)),
    )
    if not ok:
        return await _safe_reply(message, f"❌ {_esc(reason)}", parse_mode=ParseMode.HTML)

    if game.lobby_message_id:
        await _safe_edit(
            game.chat_id, game.lobby_message_id,
            _render_lobby(game, LOBBY_SECONDS),
            parse_mode=ParseMode.HTML, reply_markup=_lobby_kb(game),
        )
    await _safe_send(
        game.chat_id,
        f"🔥 {_mention(message.from_user.id, _name(message.from_user))} joined the game!",
        parse_mode=ParseMode.HTML,
    )
    try:
        await message.delete()
    except Exception:
        pass

    if game.is_full():
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _begin_match(game)


# ══════════════════════════════════════════════════════════════════════════════
#  LOBBY TIMER
# ══════════════════════════════════════════════════════════════════════════════
async def _lobby_timer(game: MafiaGame):
    try:
        await asyncio.sleep(LOBBY_SECONDS)
        if game.state != STATE_LOBBY:
            return
        if not game.can_start():
            await _cancel_and_refund(game, reason=f"Not enough players (min {MIN_PLAYERS})")
            return
        await _begin_match(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Mafia lobby] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MATCH FLOW
# ══════════════════════════════════════════════════════════════════════════════
async def _begin_match(game: MafiaGame):
    if game.state != STATE_LOBBY:
        return
    if not game.can_start():
        return await _cancel_and_refund(game, reason="Not enough players")

    game.assign_roles()

    if game.is_paid:
        game.gross_pool = game.entry_fee * len(game.players)
        game.tax_amount = int(game.gross_pool * GAME_FEE_PERCENT)
        game.net_prize  = game.gross_pool - game.tax_amount

    game.day_no = 0
    game.state = STATE_NIGHT
    await persist_game(game)

    await _safe_send(
        game.chat_id,
        "🎭 <b>GAME STARTING!</b>\n\n"
        f"👥 Players: <code>{len(game.players)}</code>\n"
        "📩 Roles are being sent via DM...\n"
        "⏱ Please check your DM!",
        parse_mode=ParseMode.HTML,
    )

    failed_dms = []
    for p in game.players:
        uid = p["user_id"]
        role = game.roles.get(uid)
        if not role:
            continue
        success = await _send_role_dm(game, uid, role)
        if not success:
            failed_dms.append(p)

    if failed_dms:
        names = ", ".join(p["mention"] for p in failed_dms)
        for p in failed_dms:
            game.players = [x for x in game.players if x["user_id"] != p["user_id"]]
            game.roles.pop(p["user_id"], None)
            if p["user_id"] in game.alive:
                game.alive.remove(p["user_id"])
        await _safe_send(
            game.chat_id,
            f"⚠️ Could not DM: {names}\n<i>They were removed.</i>",
            parse_mode=ParseMode.HTML,
        )

    if not game.can_start():
        return await _cancel_and_refund(game, reason="Not enough players after DM check")

    await asyncio.sleep(2)
    await _start_night(game)


async def _send_role_dm(game: MafiaGame, uid: int, role: str) -> bool:
    emoji = ROLE_EMOJI.get(role, "❔")
    label = ROLE_LABEL.get(role, role.upper())

    text = f"🎭 <b>YOUR ROLE: {emoji} {label}</b>\n\n"
    kb = None

    if role == ROLE_MAFIA:
        text += (
            "🔪 You are the <b>MAFIA</b>!\n\n"
            "Each night, choose one player to kill.\n"
            "During the day, pretend to be a Villager!\n\n"
            "👇 Choose your target:"
        )
        kb = _target_kb(game, uid, "mafia_nk")

    elif role == ROLE_DETECTIVE:
        text += (
            "🕵️ You are the <b>DETECTIVE</b>!\n\n"
            "Each night, choose one player to investigate.\n"
            "The bot will tell you their role privately.\n\n"
            "👇 Choose your target:"
        )
        kb = _target_kb(game, uid, "mafia_nc")

    elif role == ROLE_DOCTOR:
        text += (
            "👨‍⚕️ You are the <b>DOCTOR</b>!\n\n"
            "Each night, choose one player to protect.\n"
            "If the Mafia targets them, they will be saved!\n"
            "You CAN protect yourself.\n\n"
            "👇 Choose your target:"
        )
        kb = _target_kb(game, uid, "mafia_nd", include_self=True)

    elif role == ROLE_WITCH:
        text += (
            "🧙 You are the <b>WITCH</b>!\n\n"
            "You have TWO potions (each usable once):\n"
            "• 💚 Heal — revive/protect a player\n"
            "• ☠️ Kill — instantly kill a player\n\n"
            "<i>Witch potions are not active in this version — you play as a Villager.</i>"
        )

    else:
        text += (
            "👥 You are a <b>VILLAGER</b>!\n\n"
            "You have no night action.\n"
            "During the day, discuss and vote to find the Mafia!"
        )

    sent = await _safe_dm(uid, text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return sent is not None


def _target_kb(game: MafiaGame, actor_uid: int, prefix: str,
               include_self: bool = False) -> InlineKeyboardMarkup:
    rows, row = [], []
    for p in game.players:
        if not include_self and p["user_id"] == actor_uid:
            continue
        row.append(InlineKeyboardButton(
            p["name"],
            callback_data=f"{prefix}:{game.chat_id}:{p['user_id']}",
        ))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else None


async def _start_night(game: MafiaGame):
    """✅ FIXED: allow transition from VOTING/DAY/LOBBY."""
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return

    game.day_no += 1
    game.reset_night_actions()
    game.state = STATE_NIGHT
    await persist_game(game)

    await _safe_send(game.chat_id, _render_night_intro(game), parse_mode=ParseMode.HTML)

    # Re-send night action DMs for surviving special roles
    if game.day_no > 1:
        mafia_uid = game.get_mafia()
        det_uid = game.get_detective()
        doc_uid = game.get_doctor()
        if mafia_uid and mafia_uid in game.alive:
            await _send_action_dm(game, mafia_uid, "mafia_nk",
                                  "🔪 Choose who to kill", "🔪 NIGHT — CHOOSE KILL TARGET")
        if det_uid and det_uid in game.alive:
            await _send_action_dm(game, det_uid, "mafia_nc",
                                  "Choose who to investigate", "🕵️ NIGHT — CHOOSE TARGET")
        if doc_uid and doc_uid in game.alive:
            await _send_action_dm(game, doc_uid, "mafia_nd",
                                  "Choose who to protect", "👨‍⚕️ NIGHT — CHOOSE PROTECT",
                                  include_self=True)

    game.phase_task = asyncio.create_task(_night_timer(game, game.day_no))


async def _send_action_dm(game: MafiaGame, uid: int, prefix: str,
                          desc: str, title: str, include_self: bool = False):
    kb = _target_kb(game, uid, prefix, include_self=include_self)
    await _safe_dm(
        uid,
        f"{title}\n\n{desc}:\n\n👇",
        parse_mode=ParseMode.HTML, reply_markup=kb,
    )


async def _night_timer(game: MafiaGame, day_no: int):
    try:
        await asyncio.sleep(NIGHT_SECONDS)
        if game.state != STATE_NIGHT or game.day_no != day_no:
            return
        await _resolve_night(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Mafia night timer] {type(e).__name__}: {e}", flush=True)


async def _maybe_advance_from_night(game: MafiaGame):
    if game.state != STATE_NIGHT:
        return
    mafia_uid = game.get_mafia()
    det_uid = game.get_detective()
    doc_uid = game.get_doctor()

    mafia_alive = mafia_uid in game.alive if mafia_uid else False
    det_alive = det_uid in game.alive if det_uid else False
    doc_alive = doc_uid in game.alive if doc_uid else False

    mafia_ready = (not mafia_alive) or game.night_kill_done
    det_ready = (not det_alive) or game.night_check_done
    doc_ready = (not doc_alive) or game.night_save_done

    if mafia_ready and det_ready and doc_ready:
        if game.phase_task and not game.phase_task.done():
            game.phase_task.cancel()
        await _resolve_night(game)


async def _resolve_night(game: MafiaGame):
    if game.state != STATE_NIGHT:
        return

    killed_uid, was_saved = game.resolve_night()

    # Mafia kill stat
    if game.night_kill_done and game.get_mafia():
        try:
            await bump_mafia_kills(game.get_mafia())
        except Exception:
            pass

    # Doctor save stat
    if was_saved and game.get_doctor():
        try:
            await bump_doctor_saves(game.get_doctor())
        except Exception:
            pass
        try:
            await _safe_dm(
                game.get_doctor(),
                "🩺 <b>YOUR SAVE WORKED!</b>\n\n"
                "The Mafia attacked your target, but you saved them! ✅",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # Detective result
    if game.night_check_done and game.get_detective():
        target_uid = game.night_check
        target_role = game.roles.get(target_uid, "?")
        target_p = game.get_player(target_uid)
        target_name = target_p["name"] if target_p else str(target_uid)
        is_mafia = (target_role == ROLE_MAFIA)
        try:
            await _safe_dm(
                game.get_detective(),
                f"🕵️ <b>INVESTIGATION RESULT</b>\n\n"
                f"Target: <b>{_esc(target_name)}</b>\n"
                f"Result: {'🔪 <b>MAFIA!</b>' if is_mafia else '👥 <b>Innocent</b>'}",
                parse_mode=ParseMode.HTML,
            )
            if is_mafia:
                try:
                    await bump_detective_catches(game.get_detective())
                except Exception:
                    pass
        except Exception:
            pass

    game.state = STATE_DAY
    await persist_game(game)

    winner = game.check_winner()
    if winner:
        return await _finish_game(game, winner)

    await _safe_send(
        game.chat_id,
        _render_day_announce(game, killed_uid, was_saved),
        parse_mode=ParseMode.HTML,
    )

    game.phase_task = asyncio.create_task(_day_timer(game, game.day_no))


async def _day_timer(game: MafiaGame, day_no: int):
    try:
        await asyncio.sleep(DAY_SECONDS)
        if game.state != STATE_DAY or game.day_no != day_no:
            return
        await _start_voting(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Mafia day timer] {type(e).__name__}: {e}", flush=True)


async def _start_voting(game: MafiaGame):
    if game.state not in (STATE_DAY,):
        return

    winner = game.check_winner()
    if winner:
        return await _finish_game(game, winner)

    game.state = STATE_VOTING
    game.votes = {}
    await persist_game(game)

    sent = await _safe_send(
        game.chat_id, _render_voting(game),
        parse_mode=ParseMode.HTML, reply_markup=_vote_kb(game),
    )
    if sent:
        game.phase_message_id = sent.id

    game.phase_task = asyncio.create_task(_vote_timer(game, game.day_no))


async def _vote_timer(game: MafiaGame, day_no: int):
    try:
        await asyncio.sleep(VOTE_SECONDS)
        if game.state != STATE_VOTING or game.day_no != day_no:
            return
        await _resolve_voting(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Mafia vote timer] {type(e).__name__}: {e}", flush=True)


async def _maybe_resolve_voting_early(game: MafiaGame):
    if game.state != STATE_VOTING:
        return
    if all(uid in game.votes for uid in game.alive):
        if game.phase_task and not game.phase_task.done():
            game.phase_task.cancel()
        await _resolve_voting(game)


async def _resolve_voting(game: MafiaGame):
    """✅ FIXED: properly transitions to next night."""
    if game.state != STATE_VOTING:
        return

    lynched, counts = game.tally_votes()

    if lynched is not None:
        game.eliminate(lynched)

    if game.phase_message_id:
        await _safe_edit(
            game.chat_id, game.phase_message_id,
            _render_vote_result(game, lynched, counts),
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
    else:
        await _safe_send(
            game.chat_id,
            _render_vote_result(game, lynched, counts),
            parse_mode=ParseMode.HTML,
        )

    await persist_game(game)

    winner = game.check_winner()
    if winner:
        return await _finish_game(game, winner)

    # ✅ Now we safely transition: state → NIGHT via _start_night
    await asyncio.sleep(2)
    await _start_night(game)


# ══════════════════════════════════════════════════════════════════════════════
#  NIGHT ACTION CALLBACKS (DM)
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^mafia_nk:"))
async def mafia_nk_cb(_, q: CallbackQuery):
    try:
        _, cid_str, target_str = q.data.split(":", 2)
        chat_id = int(cid_str); target_uid = int(target_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_NIGHT:
        return await q.answer("Not night phase.", show_alert=True)
    if int(q.from_user.id) != game.get_mafia():
        return await q.answer("Not your action.", show_alert=True)

    ok, reason = game.submit_night_kill(target_uid)
    if not ok:
        msg = {"already_done": "Already chosen!", "self_target": "Can't target yourself!",
               "not_alive": "Target is dead."}.get(reason, reason)
        return await q.answer(msg, show_alert=True)

    target_p = game.get_player(target_uid)
    target_name = target_p["name"] if target_p else str(target_uid)
    await q.answer(f"✅ Target locked: {target_name}", show_alert=True)

    try:
        await q.message.edit_text(
            f"🔪 <b>Target locked:</b> {_esc(target_name)}\n\n"
            "Wait for the night to end...",
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
    except Exception:
        pass

    await _maybe_advance_from_night(game)


@app.on_callback_query(filters.regex(r"^mafia_nc:"))
async def mafia_nc_cb(_, q: CallbackQuery):
    try:
        _, cid_str, target_str = q.data.split(":", 2)
        chat_id = int(cid_str); target_uid = int(target_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_NIGHT:
        return await q.answer("Not night phase.", show_alert=True)
    if int(q.from_user.id) != game.get_detective():
        return await q.answer("Not your action.", show_alert=True)

    ok, reason = game.submit_night_check(target_uid)
    if not ok:
        return await q.answer(reason, show_alert=True)

    target_p = game.get_player(target_uid)
    target_name = target_p["name"] if target_p else str(target_uid)
    await q.answer(f"✅ Investigating {target_name}...", show_alert=True)

    try:
        await q.message.edit_text(
            f"🕵️ <b>Investigating:</b> {_esc(target_name)}\n\n"
            "Result will be sent after night ends...",
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
    except Exception:
        pass

    await _maybe_advance_from_night(game)


@app.on_callback_query(filters.regex(r"^mafia_nd:"))
async def mafia_nd_cb(_, q: CallbackQuery):
    try:
        _, cid_str, target_str = q.data.split(":", 2)
        chat_id = int(cid_str); target_uid = int(target_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_NIGHT:
        return await q.answer("Not night phase.", show_alert=True)
    if int(q.from_user.id) != game.get_doctor():
        return await q.answer("Not your action.", show_alert=True)

    ok, reason = game.submit_night_save(target_uid)
    if not ok:
        return await q.answer(reason, show_alert=True)

    target_p = game.get_player(target_uid)
    target_name = target_p["name"] if target_p else str(target_uid)
    await q.answer(f"✅ Protecting {target_name}...", show_alert=True)

    try:
        await q.message.edit_text(
            f"👨‍⚕️ <b>Protecting:</b> {_esc(target_name)}\n\n"
            "Wait for the night to end...",
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
    except Exception:
        pass

    await _maybe_advance_from_night(game)


# ══════════════════════════════════════════════════════════════════════════════
#  VOTE CALLBACK (Group)
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^mafia_vote:"))
async def mafia_vote_cb(_, q: CallbackQuery):
    try:
        _, cid_str, target_str = q.data.split(":", 2)
        chat_id = int(cid_str); target_uid = int(target_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_VOTING:
        return await q.answer("Voting closed.", show_alert=True)

    ok, reason = game.submit_vote(q.from_user.id, target_uid)
    if not ok:
        msg = {"not_alive": "You are dead.", "target_not_alive": "Target already dead.",
               "self_vote": "Can't vote for yourself."}.get(reason, reason)
        return await q.answer(msg, show_alert=True)

    await q.answer("✅ Vote recorded!")

    counts: dict[int, int] = {}
    for t in game.votes.values():
        if t == -1:
            continue
        counts[t] = counts.get(t, 0) + 1

    lines = ["🗳️ <b>VOTING — LIVE TALLY</b>\n"]
    for p in game.alive_players():
        c = counts.get(p["user_id"], 0)
        lines.append(f"• <b>{_esc(p['name'])}</b> — <code>{c}</code>")
    skips = sum(1 for t in game.votes.values() if t == -1)
    if skips:
        lines.append(f"• ⏭️ SKIP — <code>{skips}</code>")
    lines.append(f"\n👥 Voted: <code>{len(game.votes)}/{game.alive_count()}</code>")

    try:
        await q.message.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=_vote_kb(game),
        )
    except Exception:
        pass

    await _maybe_resolve_voting_early(game)


# ══════════════════════════════════════════════════════════════════════════════
#  FINISH  /  CANCEL
# ══════════════════════════════════════════════════════════════════════════════
async def _finish_game(game: MafiaGame, winner_side: str):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.payout_done:
        return

    game.state = STATE_FINISHED
    game.winner_side = winner_side
    game.finished_at = datetime.now(timezone.utc)
    game.cancel_timers()

    await _safe_send(game.chat_id, _render_win(game), parse_mode=ParseMode.HTML)

    # Reveal all roles
    role_lines = []
    for p in game.players:
        r = game.roles.get(p["user_id"], "?")
        e = ROLE_EMOJI.get(r, "❔")
        l = ROLE_LABEL.get(r, r.upper())
        tag = " ☠️" if p["user_id"] in game.dead else " ✅"
        role_lines.append(f"• {p['mention']} — {e} <b>{l}</b>{tag}")

    await _safe_send(
        game.chat_id,
        "🎭 <b>ROLE REVEAL:</b>\n" + "\n".join(role_lines),
        parse_mode=ParseMode.HTML,
    )

    if game.is_paid and game.net_prize > 0:
        await _payout_paid_game(game, winner_side)
    else:
        await _award_xp_only(game, winner_side)

    for p in game.players:
        role = game.roles.get(p["user_id"], ROLE_VILLAGER)
        won = False
        if winner_side == "villagers" and role != ROLE_MAFIA:
            won = True
        elif winner_side == "mafia" and role == ROLE_MAFIA:
            won = True
        try:
            await record_result(
                p["user_id"], p["name"], role=role, won=won,
                wagered=(game.entry_fee if game.is_paid else 0),
                gross_won=(game.net_prize if (won and game.is_paid) else 0),
                tax_paid=(game.tax_amount if won else 0),
            )
        except Exception:
            pass

    game.payout_done = True
    await persist_game(game)

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


async def _payout_paid_game(game: MafiaGame, winner_side: str):
    pool = game.net_prize
    if pool <= 0:
        return

    recipients: list[int] = []
    if winner_side == "mafia":
        mafia_uid = game.get_mafia()
        if mafia_uid:
            recipients = [mafia_uid]
    else:
        recipients = [p["user_id"] for p in game.alive_players()
                      if game.roles.get(p["user_id"]) != ROLE_MAFIA]

    if not recipients:
        recipients = [p["user_id"] for p in game.players
                      if game.roles.get(p["user_id"]) != ROLE_MAFIA]

    if not recipients:
        return

    share = pool // len(recipients)
    if share <= 0:
        return

    payout_lines = []
    for uid in recipients:
        await _ensure_user_record(uid)
        ok = await _payout_winner(uid, share)
        p = game.get_player(uid)
        nm = p["name"] if p else str(uid)
        payout_lines.append(f"• {_esc(nm)} — <code>+{share}</code> {'✅' if ok else '❌'}")

    await _credit_elara(game.tax_amount)

    await _safe_send(
        game.chat_id,
        "💰 <b>PAYOUT</b>\n\n"
        f"🏆 Winners: {len(recipients)}\n"
        f"💰 Pool: <code>{game.gross_pool}</code> → Net <code>{pool}</code>\n"
        f"⚡ Tax: <code>{game.tax_amount}</code>\n\n"
        + "\n".join(payout_lines),
        parse_mode=ParseMode.HTML,
    )


async def _award_xp_only(game: MafiaGame, winner_side: str):
    for p in game.players:
        role = game.roles.get(p["user_id"], ROLE_VILLAGER)
        won = False
        if winner_side == "villagers" and role != ROLE_MAFIA:
            won = True
        elif winner_side == "mafia" and role == ROLE_MAFIA:
            won = True
        try:
            await add_xp(p["user_id"], WINNER_XP if won else LOSER_XP)
        except Exception:
            pass


async def _cancel_and_refund(game: MafiaGame, reason: str):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.refund_done:
        return

    game.state = STATE_CANCELLED
    game.cancel_timers()

    refunded = 0
    if game.is_paid and game.entry_fee > 0:
        for p in game.players:
            if not p.get("paid"):
                continue
            try:
                ok = await add_coins(p["user_id"], game.entry_fee)
                if ok:
                    refunded += 1
            except Exception:
                pass

    game.refund_done = True
    game.finished_at = datetime.now(timezone.utc)

    await _safe_send(
        game.chat_id,
        f"🚫 <b>MAFIA CANCELLED</b>\n\n"
        f"<i>{_esc(reason)}</i>\n"
        + (f"💰 Refunded: <code>{refunded}</code> player(s)" if game.is_paid else ""),
        parse_mode=ParseMode.HTML,
    )

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  /mafiacancel  /mafiainfo  /mafiastats  /mafiatop
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["mafiacancel"], prefixes=PREFIXES) & filters.group)
async def mafia_cancel(_, message: Message):
    if not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ No active game.", parse_mode=ParseMode.HTML)
    if int(message.from_user.id) != int(game.host_id):
        return await _safe_reply(message, "❌ Only the host can cancel.", parse_mode=ParseMode.HTML)
    if game.state != STATE_LOBBY:
        return await _safe_reply(message, "⚠️ Game already started. Can't cancel.", parse_mode=ParseMode.HTML)
    await _cancel_and_refund(game, reason="Cancelled by host")


@app.on_message(filters.command(["mafiainfo"], prefixes=PREFIXES) & filters.group)
async def mafia_info(_, message: Message):
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ No active game.", parse_mode=ParseMode.HTML)
    if game.state == STATE_LOBBY:
        await _safe_reply(message, _render_lobby(game, LOBBY_SECONDS), parse_mode=ParseMode.HTML)
    else:
        alive_lines = "\n".join(f"• {p['mention']}" for p in game.alive_players())
        await _safe_reply(
            message,
            f"🎭 <b>MAFIA — {game.state}</b>\n"
            f"Day: <code>{game.day_no}</code>\n"
            f"Alive: <code>{game.alive_count()}</code>\n"
            f"Dead: <code>{len(game.dead)}</code>\n\n"
            f"<b>Alive players:</b>\n{alive_lines}",
            parse_mode=ParseMode.HTML,
        )


@app.on_message(filters.command(["mafiastats"], prefixes=PREFIXES))
async def mafia_stats_cmd(_, message: Message):
    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return

    try:
        doc = await get_stats(target.id)
    except Exception:
        doc = None

    name = _name(target)
    if not doc:
        return await _safe_reply(
            message,
            f"📊 <b>{_esc(name)}'s Mafia stats</b>\n\n❌ No games played yet.",
            parse_mode=ParseMode.HTML,
        )

    played = int(doc.get("games_played", 0))
    wins = (int(doc.get("villager_wins", 0)) + int(doc.get("mafia_wins", 0)) +
            int(doc.get("detective_wins", 0)) + int(doc.get("doctor_wins", 0)))
    wr = (wins / played * 100) if played else 0.0

    await _safe_reply(
        message,
        f"📊 <b>{_esc(name)}'s Mafia stats</b>\n\n"
        f"🎮 Games: <code>{played}</code>\n"
        f"🏆 Total wins: <code>{wins}</code> ({wr:.1f}%)\n"
        f"👥 Villager wins: <code>{int(doc.get('villager_wins', 0))}</code>\n"
        f"🔪 Mafia wins: <code>{int(doc.get('mafia_wins', 0))}</code>\n"
        f"🕵️ Detective wins: <code>{int(doc.get('detective_wins', 0))}</code>\n"
        f"👨‍⚕️ Doctor wins: <code>{int(doc.get('doctor_wins', 0))}</code>\n"
        f"❌ Losses: <code>{int(doc.get('losses', 0))}</code>\n"
        f"🔪 Kills: <code>{int(doc.get('mafia_kills', 0))}</code>\n"
        f"🕵️ Catches: <code>{int(doc.get('detective_catches', 0))}</code>\n"
        f"🩺 Saves: <code>{int(doc.get('doctor_saves', 0))}</code>\n"
        f"💰 Wagered: <code>{int(doc.get('coins_wagered', 0))}</code>\n"
        f"📊 Net: <code>{int(doc.get('net_coins', 0)):+d}</code>",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command(["mafiatop", "mafialeaderboard"], prefixes=PREFIXES))
async def mafia_top(_, message: Message):
    try:
        rows = await top_players(10)
    except Exception:
        rows = []

    if not rows:
        return await _safe_reply(
            message, "🏆 <b>Mafia Leaderboard</b>\n\n❌ No games yet.",
            parse_mode=ParseMode.HTML,
        )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>Mafia Leaderboard</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        nm = row.get("name") or str(row["_id"])
        net = int(row.get("net_coins", 0))
        wins = (int(row.get("villager_wins", 0)) + int(row.get("mafia_wins", 0)) +
                int(row.get("detective_wins", 0)) + int(row.get("doctor_wins", 0)))
        lines.append(f"{rank} <b>{_esc(nm)}</b> — 🏆 <code>{wins}</code> • 📊 <code>{net:+d}</code>")
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)
