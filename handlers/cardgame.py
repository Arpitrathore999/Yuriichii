# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/cardgame.py — 🎮 ELARA CARD GAME 🎮
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app
from core.database import get_user, add_coins, add_xp
from core.card_engine import (
    ACTIVE_GAMES,
    CARD_LABELS,
    ENTRY_FEE_MAX,
    ENTRY_FEE_MIN,
    GAME_FEE_PERCENT,
    LOBBY_SECONDS,
    LOSER_XP,
    MAX_PLAYERS_LIMIT,
    TURN_SECONDS,
    WINNER_XP,
    CardGame,
    create_game,
    ensure_stats,
    get_game,
    record_game_result,
    remove_game,
    top_leaders,
)

PREFIXES = ["/", "!", "."]


# ─── Helpers ───────────────────────────────────────────────────────────────────
def _esc(v):
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mention(user):
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)
    return f'<a href="tg://user?id={int(user.id)}">{_esc(name)}</a>'


def _name(user):
    return getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)


def _is_group(message: Message) -> bool:
    return message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _panel_kb_check_cards():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴄᴀʀᴅꜱ", callback_data="cardgame:check")],
    ])


# ─── Balance helpers (uses existing economy) ───────────────────────────────────
async def _get_balance(user_id: int) -> int:
    doc = await get_user(int(user_id))
    if not doc:
        return 0
    return int(doc.get("coins", 0) or 0)


async def _deduct(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    return await add_coins(int(user_id), -int(amount))


async def _credit(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    return await add_coins(int(user_id), int(amount))


# ══════════════════════════════════════════════════════════════════════════════
#  /card — Create a new game
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("card", prefixes=PREFIXES) & filters.group)
async def card_create(_, message: Message):
    if not _is_group(message):
        return

    args = list(message.command or [])[1:]
    if len(args) < 2:
        return await message.reply(
            "❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/card &lt;amount&gt; &lt;players&gt;</code>\n"
            "<i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/card 501 2</code>",
            parse_mode=ParseMode.HTML,
        )

    try:
        entry_fee = int(args[0])
        max_players = int(args[1])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀꜱ.</b>", parse_mode=ParseMode.HTML)

    if entry_fee < ENTRY_FEE_MIN or entry_fee > ENTRY_FEE_MAX:
        return await message.reply(
            f"❌ ᴇɴᴛʀʏ ꜰᴇᴇ ᴍᴜꜱᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ <code>{ENTRY_FEE_MIN}</code> ᴀɴᴅ <code>{ENTRY_FEE_MAX}</code>.",
            parse_mode=ParseMode.HTML,
        )
    if max_players < 2 or max_players > MAX_PLAYERS_LIMIT:
        return await message.reply(
            f"❌ ᴘʟᴀʏᴇʀꜱ ᴍᴜꜱᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ <code>2</code> ᴀɴᴅ <code>{MAX_PLAYERS_LIMIT}</code>.",
            parse_mode=ParseMode.HTML,
        )

    existing = get_game(message.chat.id)
    if existing and not existing.is_finished():
        return await message.reply(
            "⚠️ <b>ᴀ ɢᴀᴍᴇ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ɪɴ ᴛʜɪꜱ ᴄʜᴀᴛ.</b>",
            parse_mode=ParseMode.HTML,
        )

    game = create_game(message.chat.id, entry_fee, max_players, message.from_user.id)

    # Auto-add creator? No — creator must /bet to join, matches spec.
    await message.reply(
        "🃏 <b>ᴄᴀʀᴅ ɢᴀᴍᴇ ꜱᴛᴀʀᴛᴇᴅ.</b>\n\n"
        f"💰 <b>ᴇɴᴛʀʏ ꜰᴇᴇ:</b> <code>{entry_fee}</code>\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b> ᴍᴀx <code>{max_players}</code> ᴘʟᴀʏᴇʀꜱ\n"
        f"👉 ᴜꜱᴇ <code>/bet {entry_fee}</code> ɢᴇᴍꜱ/ᴄᴏɪɴꜱ\n"
        f"⏳ <b>ɢᴀᴍᴇ ꜱᴛᴀʀᴛꜱ ɪɴ 2 ᴍɪɴᴜᴛᴇꜱ.</b>",
        parse_mode=ParseMode.HTML,
    )

    # Schedule lobby timeout
    game.lobby_task = asyncio.create_task(_lobby_timeout(game))


async def _lobby_timeout(game: CardGame):
    try:
        await asyncio.sleep(LOBBY_SECONDS)
        if game.state != "lobby":
            return
        if len(game.players) < 2:
            # Not enough players → cancel, refund
            await _cancel_lobby(game, reason="ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ ᴊᴏɪɴᴇᴅ")
            return
        # Enough players → start with current count
        await _start_game(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[CARDGAME lobby] {type(e).__name__}: {e}", flush=True)


async def _cancel_lobby(game: CardGame, reason: str):
    if game.state != "lobby":
        return
    game.state = "finished"
    # Refund players
    for p in game.players:
        try:
            await _credit(p["user_id"], game.entry_fee)
        except Exception:
            pass
    remove_game(game.chat_id)
    try:
        await app.send_message(
            game.chat_id,
            f"❌ <b>ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n<i>{_esc(reason)}</i>\n"
            f"💰 ᴀʟʟ ᴇɴᴛʀʏ ꜰᴇᴇꜱ ʀᴇꜰᴜɴᴅᴇᴅ.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  /bet — Join the game
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("bet", prefixes=PREFIXES) & filters.group)
async def card_bet(_, message: Message):
    if not _is_group(message):
        return

    game = get_game(message.chat.id)
    if not game or game.state == "finished":
        return await message.reply("❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴄᴀʀᴅ ɢᴀᴍᴇ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)

    if game.state != "lobby":
        return await message.reply("❌ <b>ɢᴀᴍᴇ ʜᴀꜱ ᴀʟʀᴇᴀᴅʏ ꜱᴛᴀʀᴛᴇᴅ.</b>", parse_mode=ParseMode.HTML)

    args = list(message.command or [])[1:]
    if not args:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/bet &lt;amount&gt;</code>", parse_mode=ParseMode.HTML)

    try:
        amount = int(args[0])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>", parse_mode=ParseMode.HTML)

    if amount != game.entry_fee:
        return await message.reply(
            f"❌ <b>ɪɴᴠᴀʟɪᴅ ʙᴇᴛ ᴀᴍᴏᴜɴᴛ.</b>\n"
            f"<i>ʀᴇQᴜɪʀᴇᴅ:</i> <code>{game.entry_fee}</code>",
            parse_mode=ParseMode.HTML,
        )

    if game.has_player(message.from_user.id):
        return await message.reply("⚠️ <b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜɪꜱ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)

    if game.is_full():
        return await message.reply("❌ <b>ɢᴀᴍᴇ ɪꜱ ꜰᴜʟʟ.</b>", parse_mode=ParseMode.HTML)

    balance = await _get_balance(message.from_user.id)
    if balance < amount:
        return await message.reply("❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ.</b>", parse_mode=ParseMode.HTML)

    # Deduct
    ok = await _deduct(message.from_user.id, amount)
    if not ok:
        return await message.reply("❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ʙᴀʟᴀɴᴄᴇ.</b>", parse_mode=ParseMode.HTML)

    game.add_player(
        message.from_user.id,
        _name(message.from_user),
        _mention(message.from_user),
    )
    await ensure_stats(message.from_user.id, _name(message.from_user))

    await message.reply(
        f"🦋 <b>{_mention(message.from_user)} ᴊᴏɪɴᴇᴅ.</b>\n"
        f"👥 ᴘʟᴀʏᴇʀꜱ: <code>{len(game.players)}/{game.max_players}</code>",
        parse_mode=ParseMode.HTML,
    )

    if game.is_full():
        await message.reply("👥 <b>ɢᴀᴍᴇ ɪꜱ ꜰᴜʟʟ! ꜱᴛᴀʀᴛɪɴɢ ɴᴏᴡ...</b>", parse_mode=ParseMode.HTML)
        # Cancel lobby task
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _start_game(game)


# ══════════════════════════════════════════════════════════════════════════════
#  Game Start
# ══════════════════════════════════════════════════════════════════════════════
async def _start_game(game: CardGame):
    if game.state != "lobby":
        return
    if len(game.players) < 2:
        return await _cancel_lobby(game, reason="ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ")

    game.state = "running"
    game.start_time = datetime.now(timezone.utc)

    # Generate equal-sum hands
    from core.card_engine import _generate_equal_hands
    hands = _generate_equal_hands(len(game.players))
    for p, hand in zip(game.players, hands):
        p["hand"] = hand
        p["used"] = [False, False, False, False]

    players_line = "\n".join(f"👤 {p['mention']}" for p in game.players)
    total_pot = game.entry_fee * len(game.players)

    await app.send_message(
        game.chat_id,
        "👻 <b>ɢᴀᴍᴇ ꜱᴛᴀʀᴛᴇᴅ!</b>\n\n"
        f"💰 ᴘʟᴀʏᴇʀ'ꜱ ʙᴇᴛ ᴀᴍᴏᴜɴᴛ: <code>{game.entry_fee}</code>\n"
        f"👥 ᴛᴏᴛᴀʟ ᴘʟᴀʏᴇʀꜱ: <code>{len(game.players)}</code>\n"
        f"💵 ᴛᴏᴛᴀʟ ᴘᴏᴛ: <code>{total_pot}</code>\n\n"
        f"👉 {players_line}\n\n"
        "<i>ᴛᴀᴘ ʙᴇʟᴏᴡ ᴛᴏ ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴘʀɪᴠᴀᴛᴇ ᴄᴀʀᴅꜱ.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_panel_kb_check_cards(),
    )

    # Send each player private cards
    for p in game.players:
        await _send_private_cards(game, p["user_id"], round_no=1)

    # Start round 1
    await _start_round(game)


async def _send_private_cards(game: CardGame, user_id: int, round_no: int):
    p = game.get_player(user_id)
    if not p:
        return
    lines = []
    for i, label in enumerate(CARD_LABELS):
        if not p["used"][i]:
            lines.append(f"ᴄᴀʀᴅ {label} ➜ <code>{p['hand'][i]}</code>")
        else:
            lines.append(f"ᴄᴀʀᴅ {label} ❌ ᴜꜱᴇᴅ")

    text = (
        f"🎯 <b>ʀᴏᴜɴᴅ {round_no}</b>\n\n"
        "🃏 <b>ʏᴏᴜʀ ʀᴇᴍᴀɪɴɪɴɢ ᴄᴀʀᴅꜱ:</b>\n"
        + "\n".join(lines)
        + "\n\n💡 <i>ɴᴏᴛᴇ: ᴄᴀʀᴅ ꜱᴜᴍ ɪꜱ ꜱᴀᴍᴇ ꜰᴏʀ ᴇᴠᴇʀʏᴏɴᴇ.</i>\n\n"
        "👉 ᴜꜱᴇ <code>/flip a</code> / <code>b</code> / <code>c</code> / <code>d</code>\n"
        "<i>ʏᴏᴜ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴏʀ ʜᴇʀᴇ ɪɴ ᴅᴍ.</i>"
    )
    try:
        await app.send_message(user_id, text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  /flip — Play a card
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("flip", prefixes=PREFIXES))
async def card_flip(_, message: Message):
    # Works in DM or in group
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    # Find active game: if in group, that group; if in DM, find the game containing the user
    game = None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        game = get_game(chat_id)
    else:
        for g in list(ACTIVE_GAMES.values()):
            if g.has_player(user_id) and g.state == "running":
                game = g
                break

    if not game or game.state != "running":
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴄᴀʀᴅ ɢᴀᴍᴇ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)

    if not game.has_player(user_id):
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛ ɪɴ ᴛʜɪꜱ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)

    args = list(message.command or [])[1:]
    if not args:
        return await message.reply("⚠️ ᴜꜱᴇ <code>/flip a</code>, <code>/flip b</code>, <code>/flip c</code> ᴏʀ <code>/flip d</code>.", parse_mode=ParseMode.HTML)

    card_label = args[0].lower().strip()
    if card_label not in CARD_LABELS:
        return await message.reply("⚠️ ᴜꜱᴇ <code>/flip a</code>, <code>/flip b</code>, <code>/flip c</code> ᴏʀ <code>/flip d</code>.", parse_mode=ParseMode.HTML)

    # Turn check
    current = game.current_player()
    if not current or current["user_id"] != user_id:
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("⏳ ɪᴛ'ꜱ ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ.", parse_mode=ParseMode.HTML)

    ok, reason, _ = game.use_card(user_id, card_label)
    if not ok:
        if message.chat.type == ChatType.PRIVATE:
            return await message.reply(f"⚠️ {_esc(reason)}", parse_mode=ParseMode.HTML)
        mapping = {
            "already_used": "⚠️ ᴄᴀʀᴅ ᴀʟʀᴇᴀᴅʏ ᴜꜱᴇᴅ.",
            "already_played_round": "⚠️ ʏᴏᴜ ʜᴀᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴘʟᴀʏᴇᴅ ʏᴏᴜʀ ᴄᴀʀᴅ ꜰᴏʀ ᴛʜɪꜱ ʀᴏᴜɴᴅ.",
            "invalid_card": "⚠️ ᴜꜱᴇ <code>/flip a</code> / <code>b</code> / <code>c</code> / <code>d</code>.",
            "not_player": "❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛ ɪɴ ᴛʜɪꜱ ɢᴀᴍᴇ.",
            "no_cards": "⚠️ ɴᴏ ᴄᴀʀᴅꜱ ʟᴇꜰᴛ.",
        }
        msg = mapping.get(reason, f"⚠️ {_esc(reason)}")
        if message.chat.type == ChatType.PRIVATE:
            try:
                await message.reply(msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return
        return await message.reply(msg, parse_mode=ParseMode.HTML)

    # Cancel auto-play timer
    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    if message.chat.type == ChatType.PRIVATE:
        try:
            await message.reply(
                f"✅ ᴄᴀʀᴅ <b>{card_label}</b> ᴘʟᴀʏᴇᴅ ᴘʀɪᴠᴀᴛᴇʟʏ.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        # Also notify group
        try:
            await app.send_message(
                game.chat_id,
                f"🃏 {current['mention']} ꜰʟɪᴘᴘᴇᴅ ᴀ ᴄᴀʀᴅ.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    else:
        await message.reply(
            f"🃏 {current['mention']} ꜰʟɪᴘᴘᴇᴅ ᴄᴀʀᴅ <b>{card_label}</b>.",
            parse_mode=ParseMode.HTML,
        )

    # Check if round complete
    if game.all_played_this_round():
        await _finish_round(game)
    else:
        game.next_turn()
        await _start_turn(game)


async def _start_round(game: CardGame):
    game.round += 1
    game.reset_round_plays()
    game.turn_index = 0
    await _start_turn(game, new_round=True)


async def _start_turn(game: CardGame, new_round: bool = False):
    current = game.current_player()
    if not current:
        return

    if new_round:
        await app.send_message(
            game.chat_id,
            f"✅ <b>ʀᴏᴜɴᴅ {game.round} ꜱᴛᴀʀᴛᴇᴅ.</b>\n\n"
            f"👉 {current['mention']} ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ.\n\n"
            "🃏 ᴜꜱᴇ <code>/flip a/b/c/d</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await app.send_message(
            game.chat_id,
            f"👉 {current['mention']} ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ.\n"
            "🃏 ᴜꜱᴇ <code>/flip a/b/c/d</code>",
            parse_mode=ParseMode.HTML,
        )

    # Start auto-play timer
    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()
    game.turn_task = asyncio.create_task(_turn_timeout(game, current["user_id"], game.round))


async def _turn_timeout(game: CardGame, user_id: int, round_no: int):
    try:
        await asyncio.sleep(TURN_SECONDS)
        if game.state != "running" or game.round != round_no:
            return
        current = game.current_player()
        if not current or current["user_id"] != user_id:
            return
        if int(user_id) in game.round_plays:
            return  # already played

        ok, reason, value = game.auto_play(user_id)
        if not ok:
            return

        await app.send_message(
            game.chat_id,
            f"🤖 <b>ᴀᴜᴛᴏ-ᴘʟᴀʏ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.</b>\n"
            f"👉 {current['mention']} ᴛɪᴍᴇᴅ ᴏᴜᴛ — ᴀᴜᴛᴏ ᴘʟᴀʏᴇᴅ <b>{CARD_LABELS[game.round_plays[user_id]]}</b>.",
            parse_mode=ParseMode.HTML,
        )

        if game.all_played_this_round():
            await _finish_round(game)
        else:
            game.next_turn()
            await _start_turn(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[CARDGAME turn] {type(e).__name__}: {e}", flush=True)


async def _finish_round(game: CardGame):
    if game.state != "running":
        return

    # Cancel turn timer
    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    played = []  # [(player, card_label, value)]
    for p in game.players:
        idx = game.round_plays.get(p["user_id"])
        if idx is None:
            continue
        played.append((p, CARD_LABELS[idx], p["hand"][idx]))

    if not played:
        return

    highest = max(v for _, _, v in played)
    total = sum(v for _, _, v in played)
    winners = [p for p, _, v in played if v == highest]

    # Award total points to each winner
    for p in game.players:
        pass
    for w in winners:
        game.total_points[w["user_id"]] = game.total_points.get(w["user_id"], 0) + total

    lines = "\n".join(f"• {p['mention']} ➜ <code>{v}</code>" for p, _, v in played)
    winner_mentions = ", ".join(w["mention"] for w in winners)

    await app.send_message(
        game.chat_id,
        f"🎯 <b>ʀᴏᴜɴᴅ {game.round}</b>\n\n"
        f"{lines}\n\n"
        f"🏆 <b>ʀᴏᴜɴᴅ {game.round} ᴡɪɴɴᴇʀ(ꜱ):</b> {winner_mentions}\n"
        f"🃏 <b>ʜɪɢʜᴇꜱᴛ ᴄᴀʀᴅ:</b> <code>{highest}</code>\n"
        f"💰 <b>ᴘᴏɪɴᴛꜱ ɢᴀɪɴᴇᴅ:</b> <code>{total}</code> ᴇᴀᴄʜ",
        parse_mode=ParseMode.HTML,
    )

    # Update private DMs with remaining cards
    for p in game.players:
        await _send_private_cards(game, p["user_id"], game.round)

    # Next round or finish
    if game.round >= 4:
        await _finish_game(game)
    else:
        await _start_round(game)


# ══════════════════════════════════════════════════════════════════════════════
#  Game Finish
# ══════════════════════════════════════════════════════════════════════════════
async def _finish_game(game: CardGame):
    if game.state != "running":
        return
    game.state = "finished"

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    # Find final winner(s)
    max_points = max(game.total_points.values()) if game.total_points else 0
    tied = [p for p in game.players if game.total_points.get(p["user_id"], 0) == max_points]
    winner = random.choice(tied) if tied else None

    if not winner:
        return

    game.winner_id = winner["user_id"]

    # Payout (once)
    if not game.payout_done:
        total_pot = game.entry_fee * len(game.players)
        fee = int(total_pot * GAME_FEE_PERCENT)
        prize = total_pot - fee
        try:
            await _credit(winner["user_id"], prize)
        except Exception as e:
            print(f"[CARDGAME payout] {type(e).__name__}: {e}", flush=True)
        try:
            await add_xp(winner["user_id"], WINNER_XP)
        except Exception:
            pass
        for p in game.players:
            if p["user_id"] != winner["user_id"]:
                try:
                    await add_xp(p["user_id"], LOSER_XP)
                except Exception:
                    pass
        game.payout_done = True
    else:
        total_pot = game.entry_fee * len(game.players)
        fee = int(total_pot * GAME_FEE_PERCENT)
        prize = total_pot - fee

    # Save stats
    for p in game.players:
        try:
            await record_game_result(
                p["user_id"],
                p["name"],
                game.total_points.get(p["user_id"], 0),
                won=(p["user_id"] == winner["user_id"]),
            )
        except Exception:
            pass

    # Group final
    final_lines = "\n".join(
        f"• {p['mention']} — <code>{game.total_points.get(p['user_id'], 0)}</code>"
        for p in game.players
    )

    await app.send_message(
        game.chat_id,
        "🏁 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
        f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {winner['mention']}\n\n"
        f"🎯 <b>ꜰɪɴᴀʟ ᴘᴏɪɴᴛꜱ:</b>\n{final_lines}\n\n"
        f"💰 <b>ᴘʀɪᴢᴇ:</b> <code>{prize}</code>\n"
        f"⚡ <b>xᴘ:</b> <code>+{WINNER_XP}</code>\n"
        f"💵 <b>ɢᴀᴍᴇ ꜰᴇᴇ (10%):</b> <code>{fee}</code>\n\n"
        "👉 ᴘʟᴀʏ ᴀɢᴀɪɴ ᴜꜱɪɴɢ:\n"
        f"<code>/card {game.entry_fee} {game.max_players}</code>",
        parse_mode=ParseMode.HTML,
    )

    # DM results
    for p in game.players:
        is_winner = p["user_id"] == winner["user_id"]
        pts = game.total_points.get(p["user_id"], 0)
        try:
            await app.send_message(
                p["user_id"],
                "🏁 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
                f"🎯 <b>ʏᴏᴜʀ ᴛᴏᴛᴀʟ ᴘᴏɪɴᴛꜱ:</b> <code>{pts}</code>\n"
                f"🏆 <b>ᴡɪɴɴɪɴɢ ᴘᴏɪɴᴛꜱ:</b> <code>{max_points}</code>\n"
                f"👑 <b>ᴡɪɴɴᴇʀ(ꜱ):</b> {winner['mention']}\n"
                f"💰 <b>ʏᴏᴜ ᴡᴏɴ:</b> <code>{prize if is_winner else 0}</code>\n"
                f"⚡ <b>xᴘ ɢᴀɪɴᴇᴅ:</b> <code>+{WINNER_XP if is_winner else LOSER_XP}</code>\n\n"
                f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b>\n{final_lines}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    remove_game(game.chat_id)


# ══════════════════════════════════════════════════════════════════════════════
#  /leaders — Card game leaderboard
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["leaders", "cardleaders"], prefixes=PREFIXES))
async def card_leaders(_, message: Message):
    rows = await top_leaders(10)
    if not rows:
        return await message.reply("❌ ɴᴏ ᴄᴀʀᴅ ɢᴀᴍᴇ ꜱᴛᴀᴛꜱ ʏᴇᴛ.", parse_mode=ParseMode.HTML)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>ᴇʟᴀʀᴀ ᴄᴀʀᴅ ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀꜱ</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        name = row.get("name") or str(row["_id"])
        won = int(row.get("won", 0))
        pts = int(row.get("total_points", 0))
        streak = int(row.get("streak", 0))
        lines.append(
            f"{rank} <b>{_esc(name)}</b> — <code>{won}</code> ᴡɪɴꜱ • "
            f"<code>{pts}</code> ᴘᴛꜱ • 🔥 <code>{streak}</code>"
        )
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  Callback — 📩 Check Your Cards
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^cardgame:check$"))
async def cardgame_check(_, query):
    user_id = query.from_user.id
    # Find game with this user
    game = None
    for g in list(ACTIVE_GAMES.values()):
        if g.has_player(user_id) and g.state == "running":
            game = g
            break
    if not game:
        return await query.answer("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)

    p = game.get_player(user_id)
    if not p:
        return await query.answer("❌ ɴᴏᴛ ᴀ ᴘʟᴀʏᴇʀ.", show_alert=True)

    lines = []
    for i, label in enumerate(CARD_LABELS):
        if not p["used"][i]:
            lines.append(f"ᴄᴀʀᴅ {label} ➜ <code>{p['hand'][i]}</code>")
        else:
            lines.append(f"ᴄᴀʀᴅ {label} ❌ ᴜꜱᴇᴅ")

    text = (
        f"🎯 <b>ʀᴏᴜɴᴅ {game.round}</b>\n\n"
        "🃏 <b>ʏᴏᴜʀ ʀᴇᴍᴀɪɴɪɴɢ ᴄᴀʀᴅꜱ:</b>\n"
        + "\n".join(lines)
    )
    try:
        await app.send_message(user_id, text, parse_mode=ParseMode.HTML)
        await query.answer("📩 ꜱᴇɴᴛ ɪɴ ᴅᴍ!", show_alert=False)
    except Exception:
        await query.answer("❌ ᴅᴍ ʙʟᴏᴄᴋᴇᴅ.", show_alert=True)
