# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/ttt.py — 🎮 ELARA TIC TAC TOE
#  Reuses existing economy / XP / streak. UI matches Elara games style.
#  Leaderboard is handled centrally in handlers/cardgame.py
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from core.bot import app
from core.database import get_user, add_coins, remove_coins, add_xp
from core.ttt_engine import (
    ACTIVE_GAMES,
    EMPTY,
    ENTRY_MAX,
    ENTRY_MIN,
    GAME_FEE_PERCENT,
    P1_SYMBOL,
    P2_SYMBOL,
    TURN_SECONDS,
    TOTAL_CELLS,
    WINNER_XP,
    TTTGame,
    create_game,
    ensure_ttt_stats,
    get_game,
    get_ttt_stats,
    get_user_active_game,
    mark_game_finished,
    persist_game,
    record_ttt_result,
    register_game,
    unregister_game,
)

PREFIXES = ["/", "!", "."]
ELARA_BOT_ID = 8899359004


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mention(user):
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)
    return f'<a href="tg://user?id={int(user.id)}">{_esc(name)}</a>'


def _name(user):
    return getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)


def _is_group(message: Message) -> bool:
    return message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def _get_balance(user_id: int, currency: str) -> int:
    doc = await get_user(int(user_id))
    if not doc:
        return 0
    return int(doc.get(currency, 0) or 0)


async def _deduct(user_id: int, amount: int, currency: str) -> bool:
    if amount <= 0:
        return False
    try:
        if currency == "gems":
            from database.mongo import users as users_col
            col = users_col()
            if col is None:
                return False
            result = await col.update_one(
                {"_id": int(user_id), "gems": {"$gte": int(amount)}},
                {"$inc": {"gems": -int(amount)}},
            )
            return result.modified_count == 1
        return await remove_coins(int(user_id), int(amount))
    except Exception as e:
        print(f"[TTT deduct] {type(e).__name__}: {e}", flush=True)
        return False


async def _credit(user_id: int, amount: int, currency: str) -> bool:
    if amount <= 0:
        return False
    try:
        if currency == "gems":
            from database.mongo import users as users_col
            col = users_col()
            if col is None:
                return False
            result = await col.update_one(
                {"_id": int(user_id)},
                {"$inc": {"gems": int(amount)}},
            )
            return result.modified_count == 1
        return await add_coins(int(user_id), int(amount))
    except Exception as e:
        print(f"[TTT credit] {type(e).__name__}: {e}", flush=True)
        return False


async def _credit_elara(amount: int, currency: str) -> bool:
    if amount <= 0:
        return False
    try:
        from database.mongo import users as users_col
        col = users_col()
        if col is None:
            return False
        await col.update_one(
            {"_id": int(ELARA_BOT_ID)},
            {"$inc": {currency: int(amount)}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[TTT tax] {type(e).__name__}: {e}", flush=True)
        return False


def _board_keyboard(game: TTTGame, disabled: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx = r * 3 + c
            cell = game.board[idx]
            label = cell if cell != EMPTY else "⬜"
            cb = (
                f"ttt_move:{game.game_id}:{idx}"
                if not disabled and game.status == "ACTIVE"
                else f"ttt_noop:{game.game_id}"
            )
            row.append(InlineKeyboardButton(label, callback_data=cb))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _join_keyboard(game: TTTGame) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ ᴊᴏɪɴ ɢᴀᴍᴇ", callback_data=f"ttt_join:{game.game_id}")],
    ])


# ── Invite (matches Card/Hack style) ──────────────────────────────────────────
def _invite_text(game: TTTGame) -> str:
    reward = game.bet * 2
    cur = game.currency.upper()
    return (
        "🎮 <b>ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴄʜᴀʟʟᴇɴɢᴇ</b> 🎮\n\n"
        f"👤 <b>ʜᴏsᴛ:</b> {game.host_mention}\n"
        f"💰 <b>ʜᴏsᴛ ʙᴇᴛ:</b> <code>{game.bet}</code> {cur}\n"
        f"🏆 <b>ʀᴇᴡᴀʀᴅ:</b> ᴡɪɴɴᴇʀ ɢᴇᴛs <code>{reward}</code> {cur}\n"
        f"      ᴅʀᴀᴡ = ʙᴇᴛ ʀᴇꜰᴜɴᴅᴇᴅ\n\n"
        "👇 ᴛᴀᴘ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ ᴛʜᴇ ɢᴀᴍᴇ"
    )


# ── Active match (matches Card/Hack style) ───────────────────────────────────
def _active_text(game: TTTGame, extra: str = "") -> str:
    reward = game.bet * 2
    cur = game.currency.upper()
    turn_uid = game.current_turn
    if turn_uid == game.host_id:
        turn_name = game.host_name
        turn_sym = P1_SYMBOL
    else:
        turn_name = game.opponent_name or "Player"
        turn_sym = P2_SYMBOL

    body = (
        "🎮 <b>ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴍᴀᴛᴄʜ</b> 🎮\n\n"
        f"{P1_SYMBOL} <b>{_esc(game.host_name)}</b> "
        f"<b>ᴠs</b> "
        f"{P2_SYMBOL} <b>{_esc(game.opponent_name or 'ᴡᴀɪᴛɪɴɢ...')}</b>\n\n"
        f"🏆 <b>ʀᴇᴡᴀʀᴅ:</b> ᴡɪɴɴᴇʀ ɢᴇᴛs <code>{reward}</code> {cur}\n"
        f"💰 <b>ᴅʀᴀᴡ</b> = ʙᴇᴛ ʀᴇꜰᴜɴᴅᴇᴅ\n\n"
        f"👉 <b>ᴛᴜʀɴ:</b> {_esc(turn_name)} ({turn_sym})\n"
        f"⏳ ʏᴏᴜ ʜᴀᴠᴇ <code>{TURN_SECONDS}</code> sᴇᴄᴏɴᴅs ᴛᴏ ᴍᴏᴠᴇ!"
    )
    if extra:
        body = extra + "\n\n" + body
    return body


# ══════════════════════════════════════════════════════════════════════════════
#  /ttt
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("ttt", prefixes=PREFIXES) & filters.group)
async def ttt_create(_, message: Message):
    if not _is_group(message):
        return
    if not message.from_user:
        return

    existing = get_user_active_game(message.from_user.id)
    if existing and not existing.is_finished():
        return await message.reply(
            "❌ <b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ɢᴀᴍᴇ.</b>",
            parse_mode=ParseMode.HTML,
        )

    args = list(message.command or [])[1:]
    if not args:
        return await message.reply(
            "❌ <b>ᴜsᴀɢᴇ:</b> <code>/ttt &lt;amount&gt; [currency]</code>\n"
            "<i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/ttt 500 coin</code>",
            parse_mode=ParseMode.HTML,
        )

    try:
        bet = int(args[0])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>", parse_mode=ParseMode.HTML)

    if bet < ENTRY_MIN or bet > ENTRY_MAX:
        return await message.reply(
            f"❌ ʙᴇᴛ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ <code>{ENTRY_MIN}</code> ᴀɴᴅ <code>{ENTRY_MAX}</code>.",
            parse_mode=ParseMode.HTML,
        )

    currency = "coins"
    if len(args) >= 2:
        c = args[1].lower()
        if c in ("coin", "coins"):
            currency = "coins"
        elif c in ("gem", "gems"):
            currency = "gems"
        else:
            return await message.reply(
                "❌ <b>ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ ᴄᴜʀʀᴇɴᴄʏ.</b> ᴜsᴇ <code>coin</code> ᴏʀ <code>gems</code>.",
                parse_mode=ParseMode.HTML,
            )

    from database.users import ensure_user
    await ensure_user(message.from_user)

    balance = await _get_balance(message.from_user.id, currency)
    if balance < bet:
        return await message.reply(
            f"⚠️ <b>ʏᴏᴜ ʜᴀᴠᴇ ᴏɴʟʏ {balance} {currency.upper()},</b>\n"
            f"<i>ʏᴏᴜ ɴᴇᴇᴅ {bet} {currency.upper()}.</i>",
            parse_mode=ParseMode.HTML,
        )

    ok = await _deduct(message.from_user.id, bet, currency)
    if not ok:
        return await message.reply(
            "❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ʙᴇᴛ. ᴛʀʏ ᴀɢᴀɪɴ.</b>",
            parse_mode=ParseMode.HTML,
        )

    game = create_game(
        chat_id=message.chat.id,
        host_id=message.from_user.id,
        host_name=_name(message.from_user),
        host_mention=_mention(message.from_user),
        bet=bet,
        currency=currency,
    )
    await ensure_ttt_stats(message.from_user.id, _name(message.from_user))
    await persist_game(game)

    try:
        inv = await message.reply(
            _invite_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_join_keyboard(game),
        )
        game.invite_message_id = inv.id

        try:
            await app.pin_chat_message(game.chat_id, inv.id, disable_notification=True)
        except Exception as e:
            print(f"[TTT pin] {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"[TTT invite] {type(e).__name__}: {e}", flush=True)
        await _credit(message.from_user.id, bet, currency)
        unregister_game(game.game_id)
        return await message.reply("❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ sᴛᴀʀᴛ ɢᴀᴍᴇ.</b>")


# ══════════════════════════════════════════════════════════════════════════════
#  JOIN button
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^ttt_join:"))
async def ttt_join(_, query: CallbackQuery):
    gid = query.data.split(":", 1)[1]
    game = get_game(gid)
    user = query.from_user

    if not game:
        return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)

    if game.is_finished():
        return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ.", show_alert=True)

    if game.status != "WAITING":
        return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ.", show_alert=True)

    if game.has_host(user.id):
        return await query.answer("❌ ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ᴛʜᴇ ʜᴏsᴛ ᴏꜰ ᴛʜɪs ɢᴀᴍᴇ.", show_alert=True)

    if game.has_opponent():
        return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ᴀʟʀᴇᴀᴅʏ ʜᴀs ᴛᴡᴏ ᴘʟᴀʏᴇʀs.", show_alert=True)

    existing = get_user_active_game(user.id)
    if existing and existing.game_id != game.game_id:
        return await query.answer(
            "❌ ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ɢᴀᴍᴇ.",
            show_alert=True,
        )

    from database.users import ensure_user
    await ensure_user(user)

    balance = await _get_balance(user.id, game.currency)
    if balance < game.bet:
        return await query.answer(
            f"⚠️ ʏᴏᴜ ʜᴀᴠᴇ ᴏɴʟʏ {balance} {game.currency.upper()}, "
            f"ʏᴏᴜ ɴᴇᴇᴅ {game.bet} {game.currency.upper()}.",
            show_alert=True,
        )

    ok = await _deduct(user.id, game.bet, game.currency)
    if not ok:
        return await query.answer("❌ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ʙᴇᴛ.", show_alert=True)

    game.opponent_id = int(user.id)
    game.opponent_name = _name(user)
    game.opponent_mention = _mention(user)
    game.status = "ACTIVE"
    game.current_turn = game.host_id
    game.turn_started_at = datetime.now(timezone.utc)

    from core.ttt_engine import USER_ACTIVE
    USER_ACTIVE[game.opponent_id] = game.game_id

    await ensure_ttt_stats(user.id, _name(user))
    await persist_game(game)

    await query.answer("✅ ᴊᴏɪɴᴇᴅ!")

    try:
        await query.message.edit_text(
            _active_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_board_keyboard(game),
        )
        game.board_message_id = query.message.id
    except Exception as e:
        print(f"[TTT join-edit] {type(e).__name__}: {e}", flush=True)
        try:
            m = await app.send_message(
                game.chat_id,
                _active_text(game),
                parse_mode=ParseMode.HTML,
                reply_markup=_board_keyboard(game),
            )
            game.board_message_id = m.id
        except Exception as e2:
            print(f"[TTT join-send] {type(e2).__name__}: {e2}", flush=True)

    for uid in (game.host_id, game.opponent_id):
        try:
            await app.send_message(
                uid,
                "✅ <b>ᴊᴏɪɴᴇᴅ! ᴛʜᴇ ᴍᴀᴛᴄʜ ʜᴀs sᴛᴀʀᴛᴇᴅ</b>\n\n"
                "<i>ɢᴏ ʙᴀᴄᴋ ᴛᴏ ᴛʜᴇ ɢʀᴏᴜᴘ ᴛᴏ ᴘʟᴀʏ.</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    game.cancel_timer()
    game.turn_task = asyncio.create_task(_turn_timeout(game, game.current_turn))


# ══════════════════════════════════════════════════════════════════════════════
#  Board move
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^ttt_move:"))
async def ttt_move(_, query: CallbackQuery):
    parts = query.data.split(":")
    if len(parts) != 3:
        return await query.answer()
    gid, pos_raw = parts[1], parts[2]
    try:
        pos = int(pos_raw)
    except ValueError:
        return await query.answer()

    game = get_game(gid)
    user = query.from_user

    if not game:
        return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)

    if game.is_finished():
        return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)

    if not game.is_player(user.id):
        return await query.answer("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴘʟᴀʏᴇʀ ɪɴ ᴛʜɪs ᴍᴀᴛᴄʜ.", show_alert=True)

    ok, reason = game.apply_move(user.id, pos)
    if not ok:
        if reason == "not_your_turn":
            return await query.answer("❌ ɪᴛ's ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ!", show_alert=True)
        if reason == "cell_taken":
            return await query.answer("⚠️ ᴛʜᴀᴛ ᴄᴇʟʟ ɪs ᴀʟʀᴇᴀᴅʏ ᴛᴀᴋᴇɴ!", show_alert=True)
        if reason == "not_player":
            return await query.answer("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴘʟᴀʏᴇʀ ɪɴ ᴛʜɪs ᴍᴀᴛᴄʜ.", show_alert=True)
        if reason == "game_not_active":
            return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)
        return await query.answer()

    game.cancel_timer()

    winner_symbol = game.check_winner()
    if winner_symbol:
        winner_id = game.resolve_winner_id(winner_symbol)
        await query.answer("🎉 ᴡᴇ ʜᴀᴠᴇ ᴀ ᴡɪɴɴᴇʀ!")
        try:
            await query.message.edit_reply_markup(reply_markup=_board_keyboard(game, disabled=True))
        except Exception:
            pass
        await _finish_game(game, winner_id=winner_id, draw=False)
        return

    if game.is_draw():
        await query.answer("🤝 ᴅʀᴀᴡ!")
        try:
            await query.message.edit_reply_markup(reply_markup=_board_keyboard(game, disabled=True))
        except Exception:
            pass
        await _finish_game(game, winner_id=None, draw=True)
        return

    game.switch_turn()
    await persist_game(game)

    try:
        await query.message.edit_text(
            _active_text(game),
            parse_mode=ParseMode.HTML,
            reply_markup=_board_keyboard(game),
        )
    except Exception as e:
        print(f"[TTT edit-board] {type(e).__name__}: {e}", flush=True)

    game.turn_task = asyncio.create_task(_turn_timeout(game, game.current_turn))


@app.on_callback_query(filters.regex(r"^ttt_noop:"))
async def ttt_noop(_, query: CallbackQuery):
    return await query.answer("❌ ᴛʜɪs ɢᴀᴍᴇ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=False)


# ══════════════════════════════════════════════════════════════════════════════
#  Timer / Turn timeout
# ══════════════════════════════════════════════════════════════════════════════
async def _turn_timeout(game: TTTGame, expected_turn: int):
    try:
        await asyncio.sleep(TURN_SECONDS)
        if game.is_finished():
            return
        if game.status != "ACTIVE":
            return
        if int(game.current_turn or 0) != int(expected_turn):
            return

        game.switch_turn()
        await persist_game(game)

        try:
            if game.board_message_id:
                await app.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.board_message_id,
                    text="⏰ <b>ᴛɪᴍᴇ's ᴜᴘ!</b>\n\n" + _active_text(game),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_board_keyboard(game),
                )
        except Exception as e:
            print(f"[TTT timeout-edit] {type(e).__name__}: {e}", flush=True)

        game.turn_task = asyncio.create_task(_turn_timeout(game, game.current_turn))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[TTT turn] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Finish game (win or draw) — USER PFP for winner, else normal text
# ══════════════════════════════════════════════════════════════════════════════
async def _finish_game(game: TTTGame, winner_id: Optional[int], draw: bool = False):
    if game.payout_done:
        return
    game.payout_done = True
    game.cancel_timer()

    total_pot = game.bet * 2
    cur = game.currency.upper()

    # ── DRAW ──
    if draw:
        game.status = "DRAW"
        await _credit(game.host_id, game.bet, game.currency)
        if game.opponent_id:
            await _credit(game.opponent_id, game.bet, game.currency)

        await record_ttt_result(game.host_id, game.host_name, won=False, draw=True)
        if game.opponent_id:
            await record_ttt_result(game.opponent_id, game.opponent_name or "", won=False, draw=True)

        await mark_game_finished(game.game_id, "DRAW")
        unregister_game(game.game_id)

        text = (
            "🤝 <b>ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴅʀᴀᴡ!</b>\n\n"
            "<i>ᴛʜᴇ ᴍᴀᴛᴄʜ ᴇɴᴅᴇᴅ ɪɴ ᴀ ᴅʀᴀᴡ.</i>\n\n"
            "💰 <b>ʙᴇᴛ ʀᴇꜰᴜɴᴅᴇᴅ:</b>\n"
            f"👤 <b>{_esc(game.host_name)}:</b> <code>{game.bet}</code> {cur}\n"
        )
        if game.opponent_id:
            text += f"👤 <b>{_esc(game.opponent_name or '')}:</b> <code>{game.bet}</code> {cur}\n"
        text += "\n💡 <b>ᴛʏᴘᴇ /ttt ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ!</b>"

        try:
            await app.send_message(game.chat_id, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"[TTT draw-msg] {type(e).__name__}: {e}", flush=True)
        return

    # ── WINNER ──
    if winner_id is None:
        return
    game.status = "FINISHED"
    game.winner_id = int(winner_id)

    fee = int(total_pot * GAME_FEE_PERCENT)
    prize = total_pot - fee

    await _credit(winner_id, prize, game.currency)
    await _credit_elara(fee, game.currency)

    try:
        await add_xp(winner_id, WINNER_XP)
    except Exception:
        pass

    winner_name = game.host_name if winner_id == game.host_id else (game.opponent_name or "")
    loser_id = game.opponent_id if winner_id == game.host_id else game.host_id
    loser_name = game.opponent_name if winner_id == game.host_id else game.host_name

    await record_ttt_result(winner_id, winner_name, won=True, draw=False, coins_won=prize)
    if loser_id:
        await record_ttt_result(loser_id, loser_name or "", won=False, draw=False)

    await mark_game_finished(game.game_id, "FINISHED")
    unregister_game(game.game_id)

    stats = await get_ttt_stats(winner_id) or {}

    winner_user_obj = None
    try:
        winner_user_obj = await app.get_users(winner_id)
    except Exception:
        pass
    winner_display = _mention(winner_user_obj) if winner_user_obj else f"<b>{_esc(winner_name)}</b>"

    players_line = _esc(game.host_name)
    if game.opponent_name:
        players_line += f", {_esc(game.opponent_name)}"

    final_text = (
        f"👤 <b>{_esc(winner_name).upper()}'s ʀᴏʏᴀʟ ᴠɪᴄᴛᴏʀʏ</b>\n\n"
        "🎉 <b>ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b> 🎉\n"
        f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {winner_display}\n"
        f"💰 <b>{cur} ɢᴀɪɴᴇᴅ:</b> <code>{prize}</code> (10% ꜰᴇᴇ)\n"
        f"⚡ <b>xᴘ ɢᴀɪɴᴇᴅ:</b> <code>+{WINNER_XP}</code>\n"
        f"🔥 <b>sᴛʀᴇᴀᴋ:</b> <code>{int(stats.get('ttt_streak', 0))}</code>\n"
        f"🏅 <b>ᴛᴏᴛᴀʟ ᴡɪɴs:</b> <code>{int(stats.get('ttt_wins', 0))}</code>\n\n"
        f"👥 <b>ᴘʟᴀʏᴇʀs:</b> {players_line}\n\n"
        "💡 <b>ᴛʏᴘᴇ /ttt ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ!</b>"
    )

    # ✅ Try to fetch winner's PFP
    photo_path = None
    try:
        async for ph in app.get_chat_photos(winner_id, limit=1):
            file_id = (
                getattr(ph, "big_file_id", None)
                or getattr(ph, "file_id", None)
                or getattr(ph, "small_file_id", None)
            )
            if file_id:
                photo_path = await app.download_media(
                    file_id, file_name="/tmp/ttt_winner.jpg"
                )
            break
    except Exception as e:
        print(f"[TTT photo] {type(e).__name__}: {e}", flush=True)

    sent = None
    if photo_path and os.path.exists(photo_path):
        try:
            sent = await app.send_photo(
                game.chat_id,
                photo=photo_path,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[TTT photo-send] {type(e).__name__}: {e}", flush=True)
            sent = None
        finally:
            try:
                os.remove(photo_path)
            except Exception:
                pass

    if sent is None:
        try:
            await app.send_message(game.chat_id, final_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"[TTT final-msg] {type(e).__name__}: {e}", flush=True)