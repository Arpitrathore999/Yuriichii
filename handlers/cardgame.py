# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/cardgame.py — 🎮 ELARA CARD GAME 🎮
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app
from core.database import get_user, add_coins, remove_coins, add_xp
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
        [
            InlineKeyboardButton(
                "📩 ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴄᴀʀᴅꜱ",
                url="https://t.me/ItzElaraBot",
            ),
        ],
    ])


# ─── Balance helpers ──────────────────────────────────────────────────────────
async def _get_balance(user_id: int) -> int:
    doc = await get_user(int(user_id))
    if not doc:
        return 0
    return int(doc.get("coins", 0) or 0)


async def _deduct(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    try:
        return await remove_coins(int(user_id), int(amount))
    except Exception as e:
        print(f"[CARDGAME deduct] {type(e).__name__}: {e}", flush=True)
        return False


async def _credit(user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    try:
        return await add_coins(int(user_id), int(amount))
    except Exception as e:
        print(f"[CARDGAME credit] {type(e).__name__}: {e}", flush=True)
        return False


async def _track(game: CardGame, msg):
    try:
        if msg:
            game.game_messages.append(msg.id)
    except Exception:
        pass


async def _delete_all_game_messages(game: CardGame):
    try:
        if game.pinned_msg_id:
            try:
                await app.unpin_chat_message(game.chat_id, game.pinned_msg_id)
            except Exception:
                pass
            try:
                await app.delete_messages(game.chat_id, game.pinned_msg_id)
            except Exception:
                pass

        if game.game_messages:
            for i in range(0, len(game.game_messages), 100):
                chunk = game.game_messages[i:i+100]
                try:
                    await app.delete_messages(game.chat_id, chunk)
                except Exception:
                    for mid in chunk:
                        try:
                            await app.delete_messages(game.chat_id, mid)
                        except Exception:
                            pass
    except Exception as e:
        print(f"[CARDGAME cleanup] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  /card
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

    m = await message.reply(
        "🃏 <b>ᴄᴀʀᴅ ɢᴀᴍᴇ ꜱᴛᴀʀᴛᴇᴅ.</b>\n\n"
        f"💰 <b>ᴇɴᴛʀʏ ꜰᴇᴇ:</b> <code>{entry_fee}</code>\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b> ᴍᴀx <code>{max_players}</code> ᴘʟᴀʏᴇʀꜱ\n"
        f"👉 ᴜꜱᴇ <code>/bet {entry_fee}</code>\n"
        f"⏳ <b>ɢᴀᴍᴇ ꜱᴛᴀʀᴛꜱ ɪɴ 2 ᴍɪɴᴜᴛᴇꜱ.</b>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    game.lobby_task = asyncio.create_task(_lobby_timeout(game))


async def _lobby_timeout(game: CardGame):
    try:
        await asyncio.sleep(LOBBY_SECONDS)
        if game.state != "lobby":
            return
        if len(game.players) < 2:
            await _cancel_lobby(game, reason="ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ ᴊᴏɪɴᴇᴅ")
            return
        await _start_game(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[CARDGAME lobby] {type(e).__name__}: {e}", flush=True)


async def _cancel_lobby(game: CardGame, reason: str):
    if game.state != "lobby":
        return
    game.state = "finished"
    for p in game.players:
        try:
            await _credit(p["user_id"], game.entry_fee)
        except Exception:
            pass

    await _delete_all_game_messages(game)
    remove_game(game.chat_id)

    try:
        m = await app.send_message(
            game.chat_id,
            f"❌ <b>ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n<i>{_esc(reason)}</i>\n"
            f"💰 ᴀʟʟ ᴇɴᴛʀʏ ꜰᴇᴇꜱ ʀᴇꜰᴜɴᴅᴇᴅ.",
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(10)
        try:
            await app.delete_messages(game.chat_id, m.id)
        except Exception:
            pass
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  /bet
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

    ok = await _deduct(message.from_user.id, amount)
    if not ok:
        return await message.reply("❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ʙᴀʟᴀɴᴄᴇ.</b>", parse_mode=ParseMode.HTML)

    game.add_player(
        message.from_user.id,
        _name(message.from_user),
        _mention(message.from_user),
    )
    await ensure_stats(message.from_user.id, _name(message.from_user))

    m = await message.reply(
        f"🦋 <b>{_mention(message.from_user)} ᴊᴏɪɴᴇᴅ.</b>\n"
        f"👥 ᴘʟᴀʏᴇʀꜱ: <code>{len(game.players)}/{game.max_players}</code>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if game.is_full():
        m2 = await message.reply("👥 <b>ɢᴀᴍᴇ ɪꜱ ꜰᴜʟʟ! ꜱᴛᴀʀᴛɪɴɢ ɴᴏᴡ...</b>", parse_mode=ParseMode.HTML)
        await _track(game, m2)
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

    from core.card_engine import _generate_equal_hands
    hands = _generate_equal_hands(len(game.players))
    for p, hand in zip(game.players, hands):
        p["hand"] = hand
        p["used"] = [False, False, False, False]

    players_line = "\n".join(f"👤 {p['mention']}" for p in game.players)
    total_pot = game.entry_fee * len(game.players)

    try:
        start_msg = await app.send_message(
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
        game.pinned_msg_id = start_msg.id
        try:
            await app.pin_chat_message(
                game.chat_id,
                start_msg.id,
                disable_notification=True,
            )
        except Exception as e:
            print(f"[CARDGAME pin] {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"[CARDGAME start-msg] {type(e).__name__}: {e}", flush=True)

    for p in game.players:
        await _send_private_cards(game, p["user_id"], round_no=1)

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
#  /flip
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("flip", prefixes=PREFIXES))
async def card_flip(_, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

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
        return await message.reply(msg, parse_mode=ParseMode.HTML)

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    if message.chat.type == ChatType.PRIVATE:
        try:
            await message.reply(f"✅ ᴄᴀʀᴅ <b>{card_label}</b> ᴘʟᴀʏᴇᴅ ᴘʀɪᴠᴀᴛᴇʟʏ.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        try:
            gm = await app.send_message(
                game.chat_id,
                f"🃏 {current['mention']} ꜰʟɪᴘᴘᴇᴅ ᴀ ᴄᴀʀᴅ.",
                parse_mode=ParseMode.HTML,
            )
            await _track(game, gm)
        except Exception:
            pass
    else:
        m = await message.reply(
            f"🃏 {current['mention']} ꜰʟɪᴘᴘᴇᴅ ᴄᴀʀᴅ <b>{card_label}</b>.",
            parse_mode=ParseMode.HTML,
        )
        await _track(game, m)

    if game.all_played_this_round():
        await _finish_round(game)
    else:
        game.next_turn()
        await _start_turn(game)


# ══════════════════════════════════════════════════════════════════════════════
#  Round / Turn
# ══════════════════════════════════════════════════════════════════════════════
async def _start_round(game: CardGame):
    game.round += 1
    game.reset_round_plays()

    n = len(game.players)

    if game.round == 1:
        # Round 1 — random first player
        game.first_turn_index = random.randint(0, n - 1)
    else:
        # Round 2+ — first shifts -1 (backwards)
        game.first_turn_index = (game.first_turn_index - 1) % n

    game.turn_index = game.first_turn_index

    order = [game.players[(game.first_turn_index + i) % n]["name"] for i in range(n)]
    print(f"[CARDGAME] Round {game.round} order: {order}", flush=True)

    await _start_turn(game, new_round=True)


async def _start_turn(game: CardGame, new_round: bool = False):
    current = game.current_player()
    if not current:
        return

    if new_round:
        m = await app.send_message(
            game.chat_id,
            f"✅ <b>ʀᴏᴜɴᴅ {game.round} ꜱᴛᴀʀᴛᴇᴅ.</b>\n\n"
            f"👉 {current['mention']} ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ.\n\n"
            "🃏 ᴜꜱᴇ <code>/flip a/b/c/d</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        m = await app.send_message(
            game.chat_id,
            f"👉 {current['mention']} ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ.\n"
            "🃏 ᴜꜱᴇ <code>/flip a/b/c/d</code>",
            parse_mode=ParseMode.HTML,
        )
    await _track(game, m)

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
            return

        ok, reason, value = game.auto_play(user_id)
        if not ok:
            return

        m = await app.send_message(
            game.chat_id,
            f"🤖 <b>ᴀᴜᴛᴏ-ᴘʟᴀʏ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.</b>\n"
            f"👉 {current['mention']} ᴛɪᴍᴇᴅ ᴏᴜᴛ — ᴀᴜᴛᴏ ᴘʟᴀʏᴇᴅ <b>{CARD_LABELS[game.round_plays[user_id]]}</b>.",
            parse_mode=ParseMode.HTML,
        )
        await _track(game, m)

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

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    played = []
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

    for w in winners:
        game.total_points[w["user_id"]] = game.total_points.get(w["user_id"], 0) + total

    lines = "\n".join(f"• {p['mention']} ➜ <code>{v}</code>" for p, _, v in played)
    winner_mentions = ", ".join(w["mention"] for w in winners)

    m = await app.send_message(
        game.chat_id,
        f"🎯 <b>ʀᴏᴜɴᴅ {game.round}</b>\n\n"
        f"{lines}\n\n"
        f"🏆 <b>ʀᴏᴜɴᴅ {game.round} ᴡɪɴɴᴇʀ(ꜱ):</b> {winner_mentions}\n"
        f"🃏 <b>ʜɪɢʜᴇꜱᴛ ᴄᴀʀᴅ:</b> <code>{highest}</code>\n"
        f"💰 <b>ᴘᴏɪɴᴛꜱ ɢᴀɪɴᴇᴅ:</b> <code>{total}</code> ᴇᴀᴄʜ",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    for p in game.players:
        await _send_private_cards(game, p["user_id"], game.round)

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

    max_points = max(game.total_points.values()) if game.total_points else 0
    tied = [p for p in game.players if game.total_points.get(p["user_id"], 0) == max_points]
    winner = random.choice(tied) if tied else None

    if not winner:
        return

    game.winner_id = winner["user_id"]

    total_pot = game.entry_fee * len(game.players)
    fee = int(total_pot * GAME_FEE_PERCENT)
    prize = total_pot - fee

    if not game.payout_done:
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

    final_lines = "\n".join(
        f"• {p['mention']} — <code>{game.total_points.get(p['user_id'], 0)}</code>"
        for p in game.players
    )

    # ── Fetch winner profile photo ──
    # ── Fetch winner profile photo ──
winner_photo = None
try:
    # ✅ Method 1: user object se photo
    user_obj = await app.get_users(winner["user_id"])
    if getattr(user_obj, "photo", None):
        winner_photo = user_obj.photo.big_file_id
        print(f"[CARDGAME photo] got from user_obj: {winner_photo[:20]}", flush=True)
except Exception as e:
    print(f"[CARDGAME photo method1] {type(e).__name__}: {e}", flush=True)

if not winner_photo:
    try:
        # ✅ Method 2: get_chat_photos
        async for ph in app.get_chat_photos(winner["user_id"], limit=1):
            winner_photo = ph.file_id
            print(f"[CARDGAME photo] got from get_chat_photos: {winner_photo[:20]}", flush=True)
            break
    except Exception as e:
        print(f"[CARDGAME photo method2] {type(e).__name__}: {e}", flush=True)

if not winner_photo:
    # ✅ Method 3: config fallback
    default_img = (getattr(config, "CARD_WINNER_IMAGE", "") or "").strip()
    if default_img:
        winner_photo = default_img
        print(f"[CARDGAME photo] using CARD_WINNER_IMAGE", flush=True)

if not winner_photo:
    # ✅ Method 4: start image
    start_img = (getattr(config, "START_IMAGE_URL", "") or "").strip()
    if start_img:
        winner_photo = start_img
        print(f"[CARDGAME photo] using START_IMAGE_URL", flush=True)

print(f"[CARDGAME] final winner_photo = {winner_photo[:30] if winner_photo else 'NONE'}", flush=True)

    # ── Delete all game messages BEFORE sending winner msg ──
    await _delete_all_game_messages(game)

    # ── Winner message ──
    group_text = (
        "🏁 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
        f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {winner['mention']}\n\n"
        f"🎯 <b>ꜰɪɴᴀʟ ᴘᴏɪɴᴛꜱ:</b>\n{final_lines}\n\n"
        f"💰 <b>ᴘʀɪᴢᴇ:</b> <code>{prize}</code>\n"
        f"⚡ <b>xᴘ:</b> <code>+{WINNER_XP}</code>\n"
        f"💵 <b>ɢᴀᴍᴇ ꜰᴇᴇ (10%):</b> <code>{fee}</code>\n\n"
        "👉 ᴘʟᴀʏ ᴀɢᴀɪɴ ᴜꜱɪɴɢ:\n"
        f"<code>/card {game.entry_fee} {game.max_players}</code>"
    )

    final_msg = None
if winner_photo:
    try:
        final_msg = await app.send_photo(
            game.chat_id,
            photo=winner_photo,
            caption=group_text,
            parse_mode=ParseMode.HTML,
        )
        print(f"[CARDGAME] sent with photo: {final_msg.id}", flush=True)
    except Exception as e:
        print(f"[CARDGAME photo-send] {type(e).__name__}: {e}", flush=True)
        final_msg = None

if final_msg is None:
    # Fallback: text only
    try:
        final_msg = await app.send_message(
            game.chat_id,
            group_text,
            parse_mode=ParseMode.HTML,
        )
        print(f"[CARDGAME] sent text only: {final_msg.id}", flush=True)
    except Exception as e:
        print(f"[CARDGAME text-send] {type(e).__name__}: {e}", flush=True)

    # ✅ Pin final message
    try:
        if final_msg:
            await app.pin_chat_message(
                game.chat_id,
                final_msg.id,
                disable_notification=True,
            )
    except Exception as e:
        print(f"[CARDGAME pin-final] {type(e).__name__}: {e}", flush=True)

    # ── DM each player ──
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
#  /leaders
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
