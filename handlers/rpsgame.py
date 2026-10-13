# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/rpsgame.py — 🪨📄✂️ RPS Arena Telegram handlers
#  ✅ FIXED: freeze_pool() at game start + robust winner payout
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from core.bot import app
from core.database import add_coins, add_xp, get_user, remove_coins
from core.rps_engine import (
    ACTIVE_GAMES,
    DEFAULT_MAX_PLAYERS,
    DEFAULT_MIN_PLAYERS,
    ENTRY_MAX,
    ENTRY_MIN,
    GAME_FEE_PERCENT,
    LOBBY_SECONDS,
    LOSER_XP,
    MOVE_EMOJI,
    MOVE_LABEL,
    MOVE_PAPER,
    MOVE_ROCK,
    MOVE_SCISSORS,
    ROUND_SECONDS,
    STATE_ACTIVE,
    STATE_CANCELLED,
    STATE_COLLECTING,
    STATE_CREATED,
    STATE_FINISHED,
    STATE_SETTLING,
    TIMEOUT_RANDOM,
    USER_ACTIVE,
    VALID_MOVES,
    WINNER_XP,
    RPSGame,
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


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{_esc(name)}</a>'


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
            print("[RPS safe_send] FloodWait — skip", flush=True)
            return None
        print(f"[RPS safe_send] {type(e).__name__}: {e}", flush=True)
        return None


async def _safe_reply(message: Message, text, **kw):
    try:
        return await message.reply(text, **kw)
    except Exception as e:
        if type(e).__name__ == "FloodWait":
            return None
        return await _safe_send(message.chat.id, text, **kw)


async def _safe_edit(chat_id, msg_id, text, **kw):
    try:
        return await app.edit_message_text(chat_id, msg_id, text, **kw)
    except Exception as e:
        err = type(e).__name__
        if err in ("MessageNotModified", "FloodWait"):
            return None
        print(f"[RPS safe_edit] {err}: {e}", flush=True)
        return None


async def _is_admin(chat_id: int, uid: int) -> bool:
    try:
        m = await app.get_chat_member(chat_id, uid)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _get_balance(uid: int) -> int:
    try:
        doc = await get_user(int(uid))
        if not doc:
            return 0
        return int(doc.get("coins", 0) or 0)
    except Exception:
        return 0


async def _ensure_user_record(uid: int, name: str = ""):
    """Ensure user record exists so add_coins won't silently fail."""
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
        print(f"[RPS ensure_user] {type(e).__name__}: {e}", flush=True)


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
        print(f"[RPS tax] {type(e).__name__}: {e}", flush=True)
        return False


async def _payout_winner(uid: int, amount: int) -> bool:
    """Robust winner payout with 2 fallbacks.

    Order:
      1. add_coins (standard Elara API)
      2. Direct users collection $inc with upsert=True
    """
    if amount <= 0:
        return False

    # ── Try 1: standard add_coins ──
    try:
        ok = await add_coins(int(uid), int(amount))
        if ok:
            print(f"[RPS payout] ✅ add_coins ok: +{amount} → {uid}", flush=True)
            return True
        print(f"[RPS payout] ⚠️ add_coins returned False for {uid}", flush=True)
    except Exception as e:
        print(f"[RPS payout] ❌ add_coins raised {type(e).__name__}: {e}", flush=True)

    # ── Try 2: direct MongoDB upsert ──
    try:
        from database.mongo import users as users_col
        col = users_col()
        if col is None:
            print("[RPS payout] users collection is None", flush=True)
            return False

        result = await col.update_one(
            {"_id": int(uid)},
            {
                "$inc": {"coins": int(amount)},
                "$set": {"updated_at": datetime.now(timezone.utc)},
                "$setOnInsert": {
                    "_id": int(uid),
                    "first_name": "",
                    "username": "",
                    "created_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )
        if result.modified_count == 1 or result.upserted_id is not None:
            print(f"[RPS payout] ✅ fallback direct DB ok: +{amount} → {uid}", flush=True)
            return True
        print(f"[RPS payout] ⚠️ fallback update result: {result.raw_result}", flush=True)
    except Exception as e:
        print(f"[RPS payout] ❌ fallback failed {type(e).__name__}: {e}", flush=True)

    return False


# ══════════════════════════════════════════════════════════════════════════════
#  RENDERERS
# ══════════════════════════════════════════════════════════════════════════════
def _render_help() -> str:
    return (
        "🪨📄✂️ <b>ʀᴘꜱ ᴀʀᴇɴᴀ</b> ✂️📄🪨\n\n"
        "ᴍᴜʟᴛɪ-ᴘʟᴀʏᴇʀ ʀᴏᴄᴋ ᴘᴀᴘᴇʀ ꜱᴄɪꜱꜱᴏʀꜱ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ.\n\n"
        "<b>ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n"
        "• <code>/rps &lt;amount&gt;</code> — ꜱᴛᴀʀᴛ ᴀʀᴇɴᴀ\n"
        "• <code>/joinrps</code> — ᴊᴏɪɴ ᴛʜᴇ ᴀʀᴇɴᴀ\n"
        "• <code>/rpsinfo</code> — ʟᴏʙʙʏ ꜱᴛᴀᴛᴜꜱ\n"
        "• <code>/rpscancel</code> — ᴄᴀɴᴄᴇʟ (ʜᴏꜱᴛ/ᴀᴅᴍɪɴ)\n"
        "• <code>/rpsstats</code> — ʏᴏᴜʀ ꜱᴛᴀᴛꜱ\n"
        "• <code>/rpstop</code> — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n\n"
        f"💰 ᴇɴᴛʀʏ: <code>{ENTRY_MIN}</code> — <code>{ENTRY_MAX}</code> ᴄᴏɪɴꜱ\n"
        f"👥 ᴘʟᴀʏᴇʀꜱ: <code>{DEFAULT_MIN_PLAYERS}–{DEFAULT_MAX_PLAYERS}</code>\n"
        f"⏳ ʟᴏʙʙʏ: <code>{LOBBY_SECONDS}s</code> • ᴛᴜʀɴ: <code>{ROUND_SECONDS}s</code>\n"
        f"⚡ ᴛᴀx: <code>{int(GAME_FEE_PERCENT*100)}%</code>\n\n"
        "🎮 <b>ʀᴜʟᴇꜱ:</b>\n"
        "• 🪨 Rock beats ✂️ Scissors\n"
        "• ✂️ Scissors beats 📄 Paper\n"
        "• 📄 Paper beats 🪨 Rock\n"
        "• ᴅʀᴀᴡ = ɴᴏ ᴇʟɪᴍɪɴᴀᴛɪᴏɴ • ɴᴇxᴛ ʀᴏᴜɴᴅ\n"
    )


def _render_lobby(game: RPSGame, secs_left: int) -> str:
    lines = "\n".join(
        f"{i}. {p['mention']}" for i, p in enumerate(game.players, 1)
    ) or "<i>No players yet — be the first!</i>"
    gross, tax, net = game.calculate_pool()
    return (
        "🪨📄✂️ <b>ʀᴘꜱ ᴀʀᴇɴᴀ ᴏᴘᴇɴ!</b> ✂️📄🪨\n\n"
        f"💰 <b>ʙᴇᴛ ᴘᴇʀ ᴘʟᴀʏᴇʀ:</b> <code>{game.entry_fee}</code> ᴄᴏɪɴꜱ\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b> <code>{len(game.players)}/{game.max_players}</code> "
        f"<i>(min {game.min_players})</i>\n"
        f"⏳ <b>ᴊᴏɪɴ ᴛɪᴍᴇ:</b> <code>{max(0, secs_left)}s</code>\n"
        f"🏆 <b>ᴘʀɪᴢᴇ ᴘᴏᴏʟ:</b> <code>{gross}</code> "
        f"<i>({int(GAME_FEE_PERCENT*100)}% tax)</i>\n\n"
        f"👤 <b>ᴘʟᴀʏᴇʀꜱ:</b>\n{lines}\n\n"
        "👉 ᴛᴀᴘ <b>ᴊᴏɪɴ</b> ʙᴇʟᴏᴡ ᴏʀ ᴜꜱᴇ <code>/joinrps</code>!"
    )


def _lobby_kb(game: RPSGame) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"➕ ᴊᴏɪɴ ᴀʀᴇɴᴀ ({game.entry_fee} ᴄᴏɪɴꜱ)",
            callback_data=f"rps_join:{game.chat_id}",
        )],
    ])


def _render_round_start(game: RPSGame) -> str:
    pool, tax, net = game.calculate_pool()
    return (
        "⚔️ <b>ɢʟᴏᴠᴇꜱ ᴏɴ, ᴄᴜᴛɪᴇꜱ!</b>\n\n"
        "ᴛʜᴇ ꜰɪɢʜᴛ ɪꜱ ᴀʙᴏᴜᴛ ᴛᴏ ʙᴇɢɪɴ!\n\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b> <code>{game.initial_player_count}</code>\n"
        f"🏆 <b>ᴘᴏᴏʟ:</b> <code>{pool}</code> → ɴᴇᴛ <code>{net}</code>\n"
        f"⚡ <b>ᴛᴀx:</b> <code>{tax}</code>"
    )


def _render_round_prompt(game: RPSGame, secs_left: int) -> str:
    return (
        f"🎮 <b>ɴᴇᴡ ʀᴏᴜɴᴅ #{game.round_no}, ᴄᴜᴛɪᴇꜱ!</b>\n\n"
        f"ᴄʜᴏᴏꜱᴇ ʏᴏᴜʀ ᴍᴏᴠᴇ ᴡɪꜱᴇʟʏ!\n"
        f"⏱ <code>{max(0, secs_left)}s</code> ᴛᴏ ᴄʜᴏᴏꜱᴇ!\n\n"
        f"👥 ᴀʟɪᴠᴇ: <code>{len(game.players)}</code>"
    )


def _round_kb(game: RPSGame) -> InlineKeyboardMarkup:
    rid = game.round_id or ""
    cid = game.chat_id
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🪨 Rock",     callback_data=f"rps_move:{cid}:{rid}:rock"),
            InlineKeyboardButton("📄 Paper",    callback_data=f"rps_move:{cid}:{rid}:paper"),
            InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_move:{cid}:{rid}:scissors"),
        ],
    ])


def _render_reveal(game: RPSGame, survivors: set[int], eliminated: set[int],
                   reason: str, auto_filled: set[int]) -> str:
    all_seen = game.players + game.eliminated
    by_id = {p["user_id"]: p for p in all_seen}
    order = [p["user_id"] for p in game.players] + [p["user_id"] for p in game.eliminated]

    lines = []
    for uid in order:
        p = by_id.get(uid)
        if not p:
            continue
        mv = game.round_moves.get(uid)
        if mv is None:
            continue
        emoji = MOVE_EMOJI.get(mv, "❔")
        label = MOVE_LABEL.get(mv, mv.title())
        tag = " <i>(auto)</i>" if uid in auto_filled else ""
        lines.append(f"• {p['mention']}\n   ➡️ {emoji} <b>{label}</b>{tag}")

    head = "💞 <b>ᴍᴏᴠᴇꜱ ʀᴇᴠᴇᴀʟᴇᴅ!</b>\n\n"
    body = "\n".join(lines) if lines else "<i>No moves.</i>"

    if reason == "draw_single":
        tail = "\n\n🤝 <b>ᴅʀᴀᴡ!</b> ᴇᴠᴇʀʏᴏɴᴇ ᴘɪᴄᴋᴇᴅ ᴛʜᴇ ꜱᴀᴍᴇ ᴍᴏᴠᴇ. ɴᴏ ᴇʟɪᴍɪɴᴀᴛɪᴏɴꜱ."
    elif reason == "draw_all_three":
        tail = "\n\n🤝 <b>ᴅʀᴀᴡ!</b> ᴀʟʟ 3 ᴍᴏᴠᴇꜱ ᴘʀᴇꜱᴇɴᴛ. ɴᴏ ᴇʟɪᴍɪɴᴀᴛɪᴏɴꜱ."
    else:
        tail = f"\n\n💀 <b>{len(eliminated)}</b> ᴄᴜᴛɪᴇ(ꜱ) ᴇʟɪᴍɪɴᴀᴛᴇᴅ."

    return head + body + tail


def _render_winner(game: RPSGame) -> str:
    winner = next((p for p in game.players if p["user_id"] == game.winner_id), None)
    if not winner:
        return "🏆 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ</b>"
    return (
        "🏆 <b>ᴡᴇ ʜᴀᴠᴇ ᴀ ᴡɪɴɴᴇʀ!</b> 🏆\n\n"
        f"👑 {winner['mention']} <b>ᴅᴏᴍɪɴᴀᴛᴇᴅ ᴛʜᴇ ᴀʀᴇɴᴀ!</b>\n\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴘʟᴀʏᴇʀꜱ:</b> <code>{game.initial_player_count}</code>\n"
        f"💰 <b>ɢʀᴏꜱꜱ ᴘᴏᴏʟ:</b> <code>{game.gross_pool}</code>\n"
        f"⚡ <b>ᴛᴀx:</b> <code>{game.tax_amount}</code>\n"
        f"🏆 <b>ᴛᴏᴛᴀʟ ᴘʀɪᴢᴇ:</b> <code>{game.net_prize}</code> ᴄᴏɪɴꜱ\n"
        f"⚡ <b>xᴘ:</b> <code>+{WINNER_XP}</code>\n\n"
        "🎉 <b>ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ!</b>"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  /rps   /rps <amount>
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["rps"], prefixes=PREFIXES) & filters.group)
async def rps_create_or_help(_, message: Message):
    if not _is_group(message):
        return await _safe_reply(message, "❌ ʀᴘꜱ ᴏɴʟʏ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ.", parse_mode=ParseMode.HTML)
    if not message.from_user:
        return

    args = list(message.command or [])[1:]
    if not args:
        return await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)

    try:
        amount = int(args[0])
    except ValueError:
        return await _safe_reply(message, "❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>", parse_mode=ParseMode.HTML)

    if amount < ENTRY_MIN or amount > ENTRY_MAX:
        return await _safe_reply(
            message,
            f"❌ ᴇɴᴛʀʏ ᴍᴜꜱᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ <code>{ENTRY_MIN}</code> ᴀɴᴅ <code>{ENTRY_MAX}</code>.",
            parse_mode=ParseMode.HTML,
        )

    existing = get_game(message.chat.id)
    if existing and not existing.is_terminal():
        return await _safe_reply(
            message,
            "⚠️ <b>ᴀɴ ᴀʀᴇɴᴀ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ɪɴ ᴛʜɪꜱ ᴄʜᴀᴛ.</b>\n"
            "ᴜꜱᴇ <code>/rpsinfo</code> ᴛᴏ ᴠɪᴇᴡ ɪᴛ.",
            parse_mode=ParseMode.HTML,
        )

    user_game = get_user_game(message.from_user.id)
    if user_game and user_game.chat_id != message.chat.id:
        return await _safe_reply(
            message,
            "⚠️ <b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀɴᴏᴛʜᴇʀ ʀᴘꜱ ᴀʀᴇɴᴀ.</b>",
            parse_mode=ParseMode.HTML,
        )

    # ✅ Ensure user record exists
    await _ensure_user_record(message.from_user.id, _name(message.from_user))

    balance = await _get_balance(message.from_user.id)
    if balance < amount:
        return await _safe_reply(
            message,
            f"⚡ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ.</b>\n"
            f"<i>ʏᴏᴜ ʜᴀᴠᴇ</i> <code>{balance}</code> <i>ᴄᴏɪɴꜱ, ɴᴇᴇᴅ</i> <code>{amount}</code>.",
            parse_mode=ParseMode.HTML,
        )

    ok = await remove_coins(message.from_user.id, amount)
    if not ok:
        return await _safe_reply(message, "❌ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ʙᴀʟᴀɴᴄᴇ.", parse_mode=ParseMode.HTML)

    game = create_game(
        chat_id=message.chat.id,
        host_id=message.from_user.id,
        host_name=_name(message.from_user),
        host_mention=_mention(message.from_user.id, _name(message.from_user)),
        entry_fee=amount,
    )
    game.state = STATE_COLLECTING

    game.add_player(message.from_user.id, _name(message.from_user),
                    _mention(message.from_user.id, _name(message.from_user)))
    host_p = game.get_player(message.from_user.id)
    if host_p:
        host_p["paid"] = True
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
#  JOIN
# ══════════════════════════════════════════════════════════════════════════════
async def _process_join(game: RPSGame, uid: int, name: str, mention: str,
                        reply_to: Message | None = None) -> tuple[bool, str]:
    if game.state != STATE_COLLECTING:
        return False, "ʟᴏʙʙʏ ᴄʟᴏꜱᴇᴅ."
    if game.has_player(uid):
        return False, "ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜᴇ ᴀʀᴇɴᴀ."
    if game.is_full():
        return False, "ᴀʀᴇɴᴀ ɪꜱ ꜰᴜʟʟ."
    other = get_user_game(uid)
    if other and other.chat_id != game.chat_id:
        return False, "ʏᴏᴜ ᴀʀᴇ ɪɴ ᴀɴᴏᴛʜᴇʀ ᴀʀᴇɴᴀ."

    # ✅ Ensure user record before deducting
    await _ensure_user_record(uid, name)

    bal = await _get_balance(uid)
    if bal < game.entry_fee:
        return False, f"ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ ({bal} < {game.entry_fee})."

    ok = await remove_coins(uid, game.entry_fee)
    if not ok:
        return False, "ᴘᴀʏᴍᴇɴᴛ ꜰᴀɪʟᴇᴅ."

    if not game.add_player(uid, name, mention):
        try:
            await add_coins(uid, game.entry_fee)
        except Exception:
            pass
        return False, "ᴄᴏᴜʟᴅ ɴᴏᴛ ᴊᴏɪɴ."

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


@app.on_message(filters.command(["joinrps"], prefixes=PREFIXES) & filters.group)
async def rps_join_cmd(_, message: Message):
    if not _is_group(message) or not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game or game.state != STATE_COLLECTING:
        return await _safe_reply(message, "❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.</b>", parse_mode=ParseMode.HTML)

    ok, reason = await _process_join(
        game, message.from_user.id,
        _name(message.from_user),
        _mention(message.from_user.id, _name(message.from_user)),
        reply_to=message,
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
        f"🔥 {_mention(message.from_user.id, _name(message.from_user))} ᴊᴏɪɴᴇᴅ ᴛʜᴇ ʙᴀᴛᴛʟᴇ!",
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


@app.on_callback_query(filters.regex(r"^rps_join:"))
async def rps_join_cb(_, q: CallbackQuery):
    try:
        chat_id = int(q.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return await q.answer()
    game = get_game(chat_id)
    if not game or game.state != STATE_COLLECTING:
        return await q.answer("Lobby closed.", show_alert=True)

    ok, reason = await _process_join(
        game, q.from_user.id,
        _name(q.from_user),
        _mention(q.from_user.id, _name(q.from_user)),
    )
    if not ok:
        return await q.answer(reason, show_alert=True)

    await q.answer("✅ Joined!", show_alert=False)
    if game.lobby_message_id:
        await _safe_edit(
            game.chat_id, game.lobby_message_id,
            _render_lobby(game, LOBBY_SECONDS),
            parse_mode=ParseMode.HTML, reply_markup=_lobby_kb(game),
        )
    await _safe_send(
        game.chat_id,
        f"🔥 {_mention(q.from_user.id, _name(q.from_user))} ᴊᴏɪɴᴇᴅ ᴛʜᴇ ʙᴀᴛᴛʟᴇ!",
        parse_mode=ParseMode.HTML,
    )
    if game.is_full():
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _begin_match(game)


# ══════════════════════════════════════════════════════════════════════════════
#  LOBBY TIMER
# ══════════════════════════════════════════════════════════════════════════════
async def _lobby_timer(game: RPSGame):
    try:
        await asyncio.sleep(LOBBY_SECONDS)
        if game.state != STATE_COLLECTING:
            return
        if not game.can_start():
            await _cancel_and_refund(game, reason="ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ")
            return
        await _begin_match(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[RPS lobby] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MATCH FLOW
# ══════════════════════════════════════════════════════════════════════════════
async def _begin_match(game: RPSGame):
    if game.state != STATE_COLLECTING:
        return
    if not game.can_start():
        return await _cancel_and_refund(game, reason="ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ")

    # ✅ FIX: Freeze initial player count + pool BEFORE any eliminations
    game.freeze_pool()
    game.state = STATE_ACTIVE
    await persist_game(game)

    print(f"[RPS] Game started — players={game.initial_player_count}, "
          f"gross={game.total_entry_collected}", flush=True)

    await _safe_send(game.chat_id, _render_round_start(game), parse_mode=ParseMode.HTML)
    await asyncio.sleep(1.5)
    await _start_round(game)


async def _start_round(game: RPSGame):
    if game.state != STATE_ACTIVE:
        return

    if len(game.players) == 1:
        return await _finish_game(game)

    game.start_new_round()
    await persist_game(game)

    prompt = _render_round_prompt(game, ROUND_SECONDS)
    kb = _round_kb(game)

    sent = await _safe_send(
        game.chat_id, prompt,
        parse_mode=ParseMode.HTML, reply_markup=kb,
    )
    if sent:
        game.round_message_id = sent.id

    game.round_task = asyncio.create_task(_round_timer(game, game.round_id))


async def _round_timer(game: RPSGame, round_id: str):
    try:
        await asyncio.sleep(ROUND_SECONDS)
        if game.state != STATE_ACTIVE:
            return
        if game.round_id != round_id:
            return
        if game.all_submitted():
            return
        await _resolve_round(game, auto_fill=True)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[RPS round timer] {type(e).__name__}: {e}", flush=True)


async def _resolve_round(game: RPSGame, auto_fill: bool = False):
    if game.state != STATE_ACTIVE:
        return
    if auto_fill:
        eliminated_by_timeout = game.apply_timeout_policy(TIMEOUT_RANDOM)
        if eliminated_by_timeout:
            await _safe_send(
                game.chat_id,
                f"⏰ <b>ᴛɪᴍᴇᴏᴜᴛ ᴇʟɪᴍɪɴᴀᴛɪᴏɴ:</b> "
                f"<code>{len(eliminated_by_timeout)}</code> ᴘʟᴀʏᴇʀ(ꜱ) ʀᴇᴍᴏᴠᴇᴅ.",
                parse_mode=ParseMode.HTML,
            )

    survivors, eliminated, reason = game.resolve_current_round()
    auto_filled = set(game.round_auto)

    if eliminated:
        game.eliminate(eliminated)

    if game.round_message_id:
        await _safe_edit(
            game.chat_id, game.round_message_id,
            _render_reveal(game, survivors, eliminated, reason, auto_filled),
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
    else:
        await _safe_send(
            game.chat_id,
            _render_reveal(game, survivors, eliminated, reason, auto_filled),
            parse_mode=ParseMode.HTML,
        )

    await persist_game(game)

    if len(game.players) == 0:
        return await _cancel_and_refund(game, reason="ᴀʟʟ ᴘʟᴀʏᴇʀꜱ ᴇʟɪᴍɪɴᴀᴛᴇᴅ")
    if len(game.players) == 1:
        return await _finish_game(game)

    await asyncio.sleep(2)
    await _start_round(game)


# ══════════════════════════════════════════════════════════════════════════════
#  MOVE CALLBACK
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^rps_move:"))
async def rps_move_cb(_, q: CallbackQuery):
    try:
        _, cid_str, round_id, move = q.data.split(":", 3)
        chat_id = int(cid_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_ACTIVE:
        return await q.answer("Game not active.", show_alert=True)

    if game.round_id != round_id:
        return await q.answer("Round expired.", show_alert=True)

    ok, reason = game.submit_move(q.from_user.id, move)
    if not ok:
        msg = {
            "not_player": "You're not in this round.",
            "already_submitted": "Already locked in!",
            "invalid_move": "Invalid move.",
            "not_active": "Game not active.",
        }.get(reason, reason)
        return await q.answer(msg, show_alert=True)

    await q.answer("🔒 Move locked in!", show_alert=False)

    if game.all_submitted():
        if game.round_task and not game.round_task.done():
            game.round_task.cancel()
        await _resolve_round(game, auto_fill=False)


# ══════════════════════════════════════════════════════════════════════════════
#  FINISH  /  CANCEL
# ══════════════════════════════════════════════════════════════════════════════
async def _finish_game(game: RPSGame):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.payout_done:
        return
    game.state = STATE_SETTLING
    game.cancel_timers()

    winner = game.players[0] if game.players else None
    if not winner:
        return await _cancel_and_refund(game, reason="ɴᴏ ᴡɪɴɴᴇʀ")

    game.winner_id = winner["user_id"]
    gross, tax, net = game.calculate_pool()
    game.gross_pool = gross
    game.tax_amount = tax
    game.net_prize  = net

    print(f"[RPS] FINAL POOL: players={game.initial_player_count} "
          f"gross={gross}, tax={tax}, net={net}", flush=True)

    # ✅ Ensure winner record exists before payout
    await _ensure_user_record(winner["user_id"], winner["name"])

    # ✅ Robust payout
    payout_ok = await _payout_winner(winner["user_id"], net)
    if not payout_ok:
        print(f"[RPS CRITICAL] Payout FAILED for {winner['user_id']} amount={net}", flush=True)
        await _safe_send(
            game.chat_id,
            f"⚠️ <b>ᴘᴀʏᴏᴜᴛ ɪꜱꜱᴜᴇ!</b>\n"
            f"ᴀᴅᴍɪɴ ᴋᴏ ᴄᴏɴᴛᴀᴄᴛ ᴋᴀʀᴏ.\n"
            f"ᴡɪɴɴᴇʀ ID: <code>{winner['user_id']}</code>\n"
            f"ᴀᴍᴏᴜɴᴛ: <code>{net}</code>",
            parse_mode=ParseMode.HTML,
        )
        # Don't mark payout_done; keep game in SETTLING for manual fix
        return

    try:
        await add_xp(winner["user_id"], WINNER_XP)
    except Exception:
        pass

    # ✅ Tax to Elara (independent — runs even if XP fails)
    tax_ok = await _credit_elara(tax)
    print(f"[RPS] Tax {'✅' if tax_ok else '❌'}: {tax} → Elara", flush=True)

    game.payout_done = True
    game.state = STATE_FINISHED
    game.finished_at = datetime.now(timezone.utc)

    # XP for losers
    for p in game.eliminated:
        try:
            await add_xp(p["user_id"], LOSER_XP)
        except Exception:
            pass

    # Stats
    try:
        await record_result(
            winner["user_id"], winner["name"],
            won=True, wagered=game.entry_fee,
            gross_won=net, tax_paid=tax,
        )
    except Exception as e:
        print(f"[RPS stats winner] {type(e).__name__}: {e}", flush=True)

    for p in game.eliminated:
        try:
            await record_result(
                p["user_id"], p["name"],
                won=False, wagered=game.entry_fee,
            )
        except Exception:
            pass

    await _safe_send(game.chat_id, _render_winner(game), parse_mode=ParseMode.HTML)

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


async def _cancel_and_refund(game: RPSGame, reason: str):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.refund_done:
        return
    game.state = STATE_SETTLING
    game.cancel_timers()

    refunded = 0
    for p in game.players + game.eliminated:
        if not p.get("paid"):
            continue
        try:
            ok = await add_coins(p["user_id"], game.entry_fee)
            if ok:
                refunded += 1
            else:
                print(f"[RPS refund] add_coins False for {p['user_id']}", flush=True)
        except Exception as e:
            print(f"[RPS refund] {type(e).__name__}: {e}", flush=True)

    game.refund_done = True
    game.state = STATE_CANCELLED
    game.finished_at = datetime.now(timezone.utc)

    await _safe_send(
        game.chat_id,
        f"🚫 <b>ᴀʀᴇɴᴀ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
        f"<i>{_esc(reason)}</i>\n"
        f"💰 <b>ʀᴇꜰᴜɴᴅᴇᴅ:</b> <code>{refunded}</code> ᴘʟᴀʏᴇʀ(ꜱ)",
        parse_mode=ParseMode.HTML,
    )

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  /rpscancel  /rpsinfo  /rpsstats  /rpstop
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["rpscancel"], prefixes=PREFIXES) & filters.group)
async def rps_cancel(_, message: Message):
    if not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀʀᴇɴᴀ.", parse_mode=ParseMode.HTML)

    is_host = int(message.from_user.id) == int(game.host_id)
    is_adm  = await _is_admin(message.chat.id, message.from_user.id)
    if not (is_host or is_adm):
        return await _safe_reply(message, "❌ ᴏɴʟʏ ʜᴏꜱᴛ ᴏʀ ᴀᴅᴍɪɴ ᴄᴀɴ ᴄᴀɴᴄᴇʟ.", parse_mode=ParseMode.HTML)

    if game.state == STATE_ACTIVE:
        return await _safe_reply(
            message,
            "⚠️ ᴀʀᴇɴᴀ ɪꜱ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ. ᴄᴀɴᴄᴇʟ ᴏɴʟʏ ɪɴ ʟᴏʙʙʏ ꜱᴛᴀɢᴇ.",
            parse_mode=ParseMode.HTML,
        )

    await _cancel_and_refund(game, reason="ᴄᴀɴᴄᴇʟʟᴇᴅ ʙʏ ʜᴏꜱᴛ/ᴀᴅᴍɪɴ")


@app.on_message(filters.command(["rpsinfo"], prefixes=PREFIXES) & filters.group)
async def rps_info(_, message: Message):
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀʀᴇɴᴀ.", parse_mode=ParseMode.HTML)

    if game.state == STATE_COLLECTING:
        await _safe_reply(message, _render_lobby(game, LOBBY_SECONDS), parse_mode=ParseMode.HTML)
    elif game.state == STATE_ACTIVE:
        gross, tax, net = game.calculate_pool()
        await _safe_reply(
            message,
            f"🎮 <b>ᴀʀᴇɴᴀ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ</b>\n"
            f"ʀᴏᴜɴᴅ: <code>{game.round_no}</code>\n"
            f"ᴀʟɪᴠᴇ: <code>{len(game.players)}</code>\n"
            f"ᴇʟɪᴍɪɴᴀᴛᴇᴅ: <code>{len(game.eliminated)}</code>\n"
            f"💰 ᴘᴏᴏʟ: <code>{gross}</code> → ɴᴇᴛ <code>{net}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await _safe_reply(message, f"ᴀʀᴇɴᴀ ꜱᴛᴀᴛᴇ: <code>{game.state}</code>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["rpsstats"], prefixes=PREFIXES))
async def rps_stats_cmd(_, message: Message):
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
            f"📊 <b>{_esc(name)}'ꜱ ʀᴘꜱ ꜱᴛᴀᴛꜱ</b>\n\n❌ ɴᴏ ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )

    played = int(doc.get("games_played", 0))
    wins = int(doc.get("wins", 0))
    winrate = (wins / played * 100) if played else 0.0

    await _safe_reply(
        message,
        f"📊 <b>{_esc(name)}'ꜱ ʀᴘꜱ ꜱᴛᴀᴛꜱ</b>\n\n"
        f"🎮 ɢᴀᴍᴇꜱ: <code>{played}</code>\n"
        f"🏆 ᴡɪɴꜱ: <code>{wins}</code>\n"
        f"❌ ʟᴏꜱꜱᴇꜱ: <code>{int(doc.get('losses', 0))}</code>\n"
        f"🤝 ᴅʀᴀᴡꜱ: <code>{int(doc.get('draws', 0))}</code>\n"
        f"📈 ᴡɪɴʀᴀᴛᴇ: <code>{winrate:.1f}%</code>\n"
        f"💰 ᴡᴀɢᴇʀᴇᴅ: <code>{int(doc.get('coins_wagered', 0))}</code>\n"
        f"🏆 ɢʀᴏꜱꜱ ᴡᴏɴ: <code>{int(doc.get('gross_won', 0))}</code>\n"
        f"⚡ ᴛᴀx ᴘᴀɪᴅ: <code>{int(doc.get('tax_paid', 0))}</code>\n"
        f"📊 ɴᴇᴛ: <code>{int(doc.get('net_coins', 0)):+d}</code>\n"
        f"🔥 ꜱᴛʀᴇᴀᴋ: <code>{int(doc.get('win_streak', 0))}</code> "
        f"(ʙᴇꜱᴛ <code>{int(doc.get('best_streak', 0))}</code>)",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command(["rpstop", "rpsleaderboard"], prefixes=PREFIXES))
async def rps_top(_, message: Message):
    try:
        rows = await top_players(10)
    except Exception:
        rows = []

    if not rows:
        return await _safe_reply(
            message,
            "🏆 <b>ʀᴘꜱ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n❌ ɴᴏ ɢᴀᴍᴇꜱ ᴘʟᴀʏᴇᴅ ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>ʀᴘꜱ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        nm = row.get("name") or str(row["_id"])
        wins = int(row.get("wins", 0))
        net  = int(row.get("net_coins", 0))
        lines.append(
            f"{rank} <b>{_esc(nm)}</b> — 🏆 <code>{wins}</code> • 📊 <code>{net:+d}</code>"
        )
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)
