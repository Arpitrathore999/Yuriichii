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
    KICKED_FEE_PERCENT,
    LOBBY_SECONDS,
    LOSER_XP,
    MAX_MISSES,
    MAX_PLAYERS_LIMIT,
    TOTAL_ROUNDS,
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
ELARA_BOT_ID = 8899359004


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
            {
                "$inc": {"coins": int(amount)},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        print(f"[CARDGAME tax] +{amount} coins → Elara", flush=True)
        return True
    except Exception as e:
        print(f"[CARDGAME tax] FAIL: {type(e).__name__}: {e}", flush=True)
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
    p = game.get_player(user_id) or game.get_kicked(user_id)
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
    if n == 0:
        return await _finish_game(game)

    if game.round == 1:
        game.first_turn_index = random.randint(0, n - 1)
    else:
        game.first_turn_index = (game.first_turn_index - 1) % n

    game.turn_index = game.first_turn_index

    # Notify kicked players about their upcoming auto-flip
    if game.kicked:
        for kp in game.kicked:
            if not all(kp["used"]):
                try:
                    await app.send_message(
                        kp["user_id"],
                        f"🤖 <b>ʀᴏᴜɴᴅ {game.round} — ᴀᴜᴛᴏ ꜰʟɪᴘ</b>\n\n"
                        f"<i>ʏᴏᴜ ᴀʀᴇ ᴋɪᴄᴋᴇᴅ. ᴛʜɪꜱ ʀᴏᴜɴᴅ ᴏɴᴇ ᴏꜰ ʏᴏᴜʀ ʀᴇᴍᴀɪɴɪɴɢ ᴄᴀʀᴅꜱ ᴡɪʟʟ ᴀᴜᴛᴏ-ꜰʟɪᴘ.</i>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass

    await _start_turn(game, new_round=True)


async def _start_turn(game: CardGame, new_round: bool = False):
    current = game.current_player()
    if not current:
        # No active players left → check for kicked auto-flips → finish
        return await _handle_kicked_autoflips_and_advance(game)

    if new_round:
        m = await app.send_message(
            game.chat_id,
            f"✅ <b>ʀᴏᴜɴᴅ {game.round} ꜱᴛᴀʀᴛᴇᴅ.</b>\n\n"
            f"👉 {current['mention']} ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ.\n\n"
            f"⏳ ʏᴏᴜ ʜᴀᴠᴇ <code>{TURN_SECONDS}</code> ꜱᴇᴄᴏɴᴅꜱ.\n"
            "🃏 ᴜꜱᴇ <code>/flip a/b/c/d</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        m = await app.send_message(
            game.chat_id,
            f"👉 {current['mention']} ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ.\n"
            f"⏳ <code>{TURN_SECONDS}</code>ꜱ ᴛᴏ ꜰʟɪᴘ.\n"
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

        player = game.get_player(user_id)
        if not player:
            return

        player["misses"] = player.get("misses", 0) + 1
        miss_count = player["misses"]

        # Auto-flip 1 random card for this miss (both 1st and 2nd)
        ok, reason, idx, value = game.auto_flip_random(user_id)
        if not ok:
            # No cards available — skip turn
            game.next_turn()
            return await _start_turn(game)

        flipped_label = CARD_LABELS[idx]

        if miss_count == 1:
            # ⚠️ 1st miss: auto-flip + warning
            m = await app.send_message(
                game.chat_id,
                f"⚠️ <b>ᴛɪᴍᴇᴏᴜᴛ — ᴀᴜᴛᴏ-ꜰʟɪᴘ!</b>\n\n"
                f"{player['mention']} ᴛɪᴍᴇᴅ ᴏᴜᴛ.\n"
                f"🎲 ᴄᴀʀᴅ <b>{flipped_label}</b> ᴀᴜᴛᴏ-ꜰʟɪᴘᴘᴇᴅ.\n"
                f"<i>ᴇᴋ ᴀᴜʀ ᴍɪꜱꜱ = ꜱᴇᴇᴅʜᴀ ᴋɪᴄᴋ 👢</i>",
                parse_mode=ParseMode.HTML,
            )
            await _track(game, m)

            if game.all_played_this_round():
                return await _finish_round(game)
            game.next_turn()
            await _start_turn(game)
            return

        # ── 2nd miss: auto-flip + KICK ──
        kicked_p = game.kick_player(user_id)

        # Instantly auto-flip ALL remaining cards for the kicked player
        for _ in range(4):
            ok2, _, idx2, val2 = game.auto_flip_random(user_id)
            if not ok2:
                break

        # DM the kicked player
        try:
            await app.send_message(
                user_id,
                "👢 <b>ʏᴏᴜ ᴡᴇʀᴇ ᴋɪᴄᴋᴇᴅ!</b>\n\n"
                f"<i>2 ᴛɪᴍᴇᴏᴜᴛꜱ. ʏᴏᴜʀ ʀᴇᴍᴀɪɴɪɴɢ ᴄᴀʀᴅꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ᴀᴜᴛᴏ-ꜰʟɪᴘᴘᴇᴅ.</i>\n"
                f"<i>ʏᴏᴜʀ ᴇɴᴛʀʏ ꜰᴇᴇ ꜱᴛᴀʏꜱ ɪɴ ᴛʜᴇ ᴘᴏᴛ.</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        remaining_active = len(game.players)
        m = await app.send_message(
            game.chat_id,
            f"👢 <b>ᴋɪᴄᴋᴇᴅ!</b>\n\n"
            f"{kicked_p['mention']} ʜᴀꜱ ʙᴇᴇɴ ᴋɪᴄᴋᴇᴅ — <b>2 ᴛɪᴍᴇᴏᴜᴛꜱ</b>.\n"
            f"🎲 ᴀʟʟ ʀᴇᴍᴀɪɴɪɴɢ ᴄᴀʀᴅꜱ ᴀᴜᴛᴏ-ꜰʟɪᴘᴘᴇᴅ.\n"
            f"💰 ᴇɴᴛʀʏ ꜰᴇᴇ ꜱᴛᴀʏꜱ ɪɴ ᴛʜᴇ ᴘᴏᴛ.\n"
            f"👥 <b>ʀᴇᴍᴀɪɴɪɴɢ ᴀᴄᴛɪᴠᴇ:</b> <code>{remaining_active}</code>",
            parse_mode=ParseMode.HTML,
        )
        await _track(game, m)

        # Game ends immediately if no active players left
        if remaining_active == 0:
            return await _finish_game(game)

        # If round complete (all active played), advance
        if game.all_played_this_round():
            return await _finish_round(game)

        game.next_turn()
        await _start_turn(game)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[CARDGAME turn] {type(e).__name__}: {e}", flush=True)


async def _handle_kicked_autoflips_and_advance(game: CardGame):
    """Fallback: no active players. Auto-flip kicked, then finish game."""
    for kp in game.kicked:
        for _ in range(4):
            ok, _, _, _ = game.auto_flip_random(kp["user_id"])
            if not ok:
                break
    return await _finish_game(game)


async def _finish_round(game: CardGame):
    if game.state != "running":
        return

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    played = []
    # Active players who played
    for p in game.players:
        idx = game.round_plays.get(p["user_id"])
        if idx is None:
            continue
        played.append((p, CARD_LABELS[idx], p["hand"][idx]))
    # Kicked players who auto-flipped this round (shouldn't be here yet, but safe)
    for p in game.kicked:
        idx = game.round_plays.get(p["user_id"])
        if idx is None:
            continue
        played.append((p, CARD_LABELS[idx], p["hand"][idx]))

    if not played:
        return await _finish_game(game)

    highest = max(v for _, _, v in played)
    total = sum(v for _, _, v in played)
    winners = [p for p, _, v in played if v == highest]

    for w in winners:
        game.total_points[w["user_id"]] = game.total_points.get(w["user_id"], 0) + total

    lines = "\n".join(
        f"• {p['mention']} ➜ <code>{v}</code>" +
        (" <i>(auto)</i>" if game.is_kicked(p["user_id"]) else "")
        for p, _, v in played
    )
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

    # Send updated private cards
    for p in game.players:
        await _send_private_cards(game, p["user_id"], game.round)
    for p in game.kicked:
        await _send_private_cards(game, p["user_id"], game.round)

    if game.round >= TOTAL_ROUNDS:
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

    # Collect all participants (active + kicked)
    all_participants = game.players + game.kicked

    if not all_participants:
        await _delete_all_game_messages(game)
        remove_game(game.chat_id)
        return

    max_points = max(game.total_points.values()) if game.total_points else 0
    tied = [p for p in all_participants if game.total_points.get(p["user_id"], 0) == max_points]
    winner = random.choice(tied) if tied else None

    if not winner:
        return

    game.winner_id = winner["user_id"]
    game.winner_kicked = game.is_kicked(winner["user_id"])

    total_pot = game.entry_fee * len(all_participants)
    fee_pct = KICKED_FEE_PERCENT if game.winner_kicked else GAME_FEE_PERCENT
    fee = int(total_pot * fee_pct)
    prize = total_pot - fee

    if not game.payout_done:
        # ✅ Winner → prize
        try:
            await _credit(winner["user_id"], prize)
        except Exception as e:
            print(f"[CARDGAME payout] {type(e).__name__}: {e}", flush=True)

        # ✅ Tax → Elara
        await _credit_elara(fee)

        try:
            await add_xp(winner["user_id"], WINNER_XP)
        except Exception:
            pass
        for p in all_participants:
            if p["user_id"] != winner["user_id"]:
                try:
                    await add_xp(p["user_id"], LOSER_XP)
                except Exception:
                    pass
        game.payout_done = True

    for p in all_participants:
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
        f"• {p['mention']} — <code>{game.total_points.get(p['user_id'], 0)}</code>" +
        (" <i>(kicked — auto)</i>" if game.is_kicked(p["user_id"]) else "")
        for p in all_participants
    )

    # ── Winner photo ──
    winner_photo_path = None
    winner_photo_url = None

    try:
        async for ph in app.get_chat_photos(winner["user_id"], limit=1):
            winner_photo_path = await app.download_media(
                ph.file_id,
                file_name="/tmp/elara_winner.jpg",
            )
            break
    except Exception as e:
        print(f"[CARDGAME photo] FAIL: {type(e).__name__}: {e}", flush=True)

    if not winner_photo_path:
        default_img = (getattr(config, "CARD_WINNER_IMAGE", "") or "").strip()
        if default_img:
            winner_photo_url = default_img

    if not winner_photo_path and not winner_photo_url:
        start_img = (getattr(config, "START_IMAGE_URL", "") or "").strip()
        if start_img:
            winner_photo_url = start_img

    await _delete_all_game_messages(game)

    kicked_note = "\n⚡ <b>ᴋɪᴄᴋᴇᴅ ᴡɪɴɴᴇʀ!</b> <i>70/30 ꜱᴘʟɪᴛ</i>" if game.winner_kicked else ""
    group_text = (
        "🏁 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
        f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {winner['mention']}{kicked_note}\n\n"
        f"🎯 <b>ꜰɪɴᴀʟ ᴘᴏɪɴᴛꜱ:</b>\n{final_lines}\n\n"
        f"💰 <b>ᴘʀɪᴢᴇ:</b> <code>{prize}</code>\n"
        f"⚡ <b>xᴘ:</b> <code>+{WINNER_XP}</code>\n"
        f"💵 <b>ɢᴀᴍᴇ ꜰᴇᴇ ({int(fee_pct*100)}%):</b> <code>{fee}</code>\n\n"
        "👉 ᴘʟᴀʏ ᴀɢᴀɪɴ ᴜꜱɪɴɢ:\n"
        f"<code>/card {game.entry_fee} {game.max_players}</code>"
    )

    final_msg = None
    if winner_photo_path and os.path.exists(winner_photo_path):
        try:
            final_msg = await app.send_photo(
                game.chat_id,
                photo=winner_photo_path,
                caption=group_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[CARDGAME local-photo] FAIL: {type(e).__name__}: {e}", flush=True)
            final_msg = None

    if final_msg is None and winner_photo_url:
        try:
            final_msg = await app.send_photo(
                game.chat_id,
                photo=winner_photo_url,
                caption=group_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[CARDGAME url-photo] FAIL: {type(e).__name__}: {e}", flush=True)
            final_msg = None

    if final_msg is None:
        try:
            final_msg = await app.send_message(game.chat_id, group_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"[CARDGAME text-send] FAIL: {type(e).__name__}: {e}", flush=True)

    try:
        if final_msg:
            await app.pin_chat_message(game.chat_id, final_msg.id, disable_notification=True)
    except Exception as e:
        print(f"[CARDGAME pin-final] FAIL: {type(e).__name__}: {e}", flush=True)

    if winner_photo_path and os.path.exists(winner_photo_path):
        try:
            os.remove(winner_photo_path)
        except Exception:
            pass

    # DM all participants
    for p in all_participants:
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
#  /leaders — combined (Card + Hack)
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["leaders", "leaderboard"], prefixes=PREFIXES))
async def leaders_cmd(_, message: Message):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🃏 ᴄᴀʀᴅ ɢᴀᴍᴇ", callback_data="lb:card"),
            InlineKeyboardButton("🛸 ʜᴀᴄᴋ ɢᴀᴍᴇ", callback_data="lb:hack"),
        ],
    ])

    await message.reply(
        "🏆 <b>ᴇʟᴀʀᴀ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅꜱ</b>\n\n"
        "ᴄʜᴏᴏsᴇ ᴀ ɢᴀᴍᴇ ᴛᴏ ᴠɪᴇᴡ ɪᴛs ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@app.on_callback_query(filters.regex(r"^lb:"))
async def leaders_callback(_, query):
    data = query.data.split(":")[1]

    back_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🃏 ᴄᴀʀᴅ", callback_data="lb:card"),
            InlineKeyboardButton("🛸 ʜᴀᴄᴋ", callback_data="lb:hack"),
        ],
        [
            InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb:close"),
        ],
    ])

    if data == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if data == "card":
        rows = await top_leaders(10)
        if not rows:
            text = "🃏 <b>ᴄᴀʀᴅ ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n❌ ɴᴏ ꜱᴛᴀᴛꜱ ʏᴇᴛ."
        else:
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            lines = ["🃏 <b>ᴄᴀʀᴅ ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n"]
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
            text = "\n".join(lines)
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except Exception:
            pass
        await query.answer()
        return

    if data == "hack":
        from core.hack_engine import top_hackers
        rows = await top_hackers(10)
        if not rows:
            text = "🛸 <b>ʜᴀᴄᴋ ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n❌ ɴᴏ ꜱᴛᴀᴛꜱ ʏᴇᴛ."
        else:
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            lines = ["🛸 <b>ʜᴀᴄᴋ ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n"]
            for i, row in enumerate(rows, 1):
                rank = medals.get(i, f"{i}.")
                name = row.get("name") or str(row["_id"])
                won = int(row.get("won", 0))
                streak = int(row.get("streak", 0))
                lines.append(
                    f"{rank} <b>{_esc(name)}</b> — <code>{won}</code> ᴡɪɴꜱ • 🔥 <code>{streak}</code>"
                )
            text = "\n".join(lines)
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except Exception:
            pass
        await query.answer()
        return