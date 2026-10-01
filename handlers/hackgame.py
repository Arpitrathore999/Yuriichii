# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/hackgame.py — 🛸 ELARA HACK GAME
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message

import config
from core.bot import app
from core.database import get_user, add_coins, remove_coins, add_xp
from core.hack_engine import (
    ACTIVE_GAMES,
    ENTRY_MAX,
    ENTRY_MIN,
    GAME_FEE_PERCENT,
    LOSER_XP,
    MAX_MISSES,
    TURN_SECONDS,
    VALID_LENGTHS,
    WINNER_XP,
    HackGame,
    create_game,
    ensure_stats,
    generate_secret,
    get_game,
    is_valid_guess,
    record_result,
    remove_game,
    score_guess,
    top_hackers,
)

PREFIXES = ["/", "!", "."]
MIN_PLAYERS = 2
MAX_PLAYERS = 10
LOBBY_SECONDS = 120
ELARA_BOT_ID = 8899359004


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
        print(f"[HACK deduct] {type(e).__name__}: {e}", flush=True)
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
        print(f"[HACK credit] {type(e).__name__}: {e}", flush=True)
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
            {
                "$inc": {currency: int(amount)},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        print(f"[HACK tax] +{amount} {currency} → Elara", flush=True)
        return True
    except Exception as e:
        print(f"[HACK tax] FAIL: {type(e).__name__}: {e}", flush=True)
        return False


async def _track(game: HackGame, msg):
    try:
        if msg:
            game.game_messages.append(msg.id)
    except Exception:
        pass


async def _delete_all_game_messages(game: HackGame):
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
        print(f"[HACK cleanup] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  /hack
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("hack", prefixes=PREFIXES) & filters.group)
async def hack_create(_, message: Message):
    if not _is_group(message):
        return
    args = list(message.command or [])[1:]
    if len(args) < 2:
        return await message.reply(
            "❌ <b>ᴜsᴀɢᴇ:</b> <code>/hack &lt;amount&gt; &lt;digits&gt;</code>\n"
            "<i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/hack 500 3</code>",
            parse_mode=ParseMode.HTML,
        )
    try:
        amount = int(args[0])
        length = int(args[1])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀs.</b>", parse_mode=ParseMode.HTML)

    if amount < ENTRY_MIN or amount > ENTRY_MAX:
        return await message.reply(
            f"❌ ᴇɴᴛʀʏ ꜰᴇᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ <code>{ENTRY_MIN}</code> ᴀɴᴅ <code>{ENTRY_MAX}</code>.",
            parse_mode=ParseMode.HTML,
        )
    if length not in VALID_LENGTHS:
        return await message.reply(
            "❌ ᴄᴏᴅᴇ ʟᴇɴɢᴛʜ ᴍᴜsᴛ ʙᴇ <code>3</code>, <code>4</code>, <code>5</code> ᴏʀ <code>6</code>.",
            parse_mode=ParseMode.HTML,
        )

    existing = get_game(message.chat.id)
    if existing and not existing.is_finished():
        return await message.reply(
            "⚠️ <b>ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ɪɴ ᴛʜɪs ᴄʜᴀᴛ.</b>",
            parse_mode=ParseMode.HTML,
        )

    game = create_game(
        message.chat.id,
        message.from_user.id,
        _name(message.from_user),
        _mention(message.from_user),
        amount,
        "coins",
        length,
    )

    m = await message.reply(
        "💻 <b>ʜᴀᴄᴋᴇʀ ɢᴀᴍᴇ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
        f"💰 <b>ᴇɴᴛʀʏ ꜰᴇᴇ:</b> <code>{amount}</code> ᴄᴏɪɴs\n"
        f"🔐 <b>ᴛᴏᴛᴀʟ ʟᴇɴɢᴛʜ:</b> <code>{length}</code> ᴅɪɢɪᴛs\n"
        f"👥 <b>ᴍᴀx ᴘʟᴀʏᴇʀs:</b> <code>{MAX_PLAYERS}</code>\n\n"
        f"👉 ᴛᴏ ʀᴇɢɪsᴛᴇʀ: <code>/register {amount}</code>\n"
        f"⏳ <b>ɢᴀᴍᴇ sᴛᴀʀᴛs ɪɴ 2 ᴍɪɴᴜᴛᴇs.</b>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    game.lobby_task = asyncio.create_task(_lobby_timeout(game))


async def _lobby_timeout(game: HackGame):
    try:
        await asyncio.sleep(LOBBY_SECONDS)
        if game.state != "lobby":
            return
        if len(game.players) < MIN_PLAYERS:
            await _cancel_game(game, "ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀs ᴊᴏɪɴᴇᴅ")
            return
        await _start_game(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[HACK lobby] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  /register
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("register", prefixes=PREFIXES) & filters.group)
async def hack_register(_, message: Message):
    if not _is_group(message):
        return
    game = get_game(message.chat.id)
    if not game or game.state == "finished":
        return await message.reply("❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ʜᴀᴄᴋ ɢᴀᴍᴇ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)
    if game.state != "lobby":
        return await message.reply("❌ <b>ɢᴀᴍᴇ ʜᴀs ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ.</b>", parse_mode=ParseMode.HTML)

    if len(game.players) >= MAX_PLAYERS:
        return await message.reply(
            f"❌ <b>ᴘʟᴀʏᴇʀ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ!</b>\n<i>ᴍᴀx {MAX_PLAYERS} ᴘʟᴀʏᴇʀs ᴏɴʟʏ.</i>",
            parse_mode=ParseMode.HTML,
        )

    args = list(message.command or [])[1:]
    if not args:
        return await message.reply("❌ <b>ᴜsᴀɢᴇ:</b> <code>/register &lt;amount&gt; [coins|gems]</code>", parse_mode=ParseMode.HTML)
    try:
        amount = int(args[0])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>", parse_mode=ParseMode.HTML)

    currency = "coins"
    if len(args) >= 2:
        c = args[1].lower()
        if c in ("gems", "gem"):
            currency = "gems"
        elif c in ("coins", "coin"):
            currency = "coins"

    if amount != game.entry_amount:
        return await message.reply(
            f"❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>\n<i>ʀᴇQᴜɪʀᴇᴅ:</i> <code>{game.entry_amount}</code>",
            parse_mode=ParseMode.HTML,
        )
    if game.has_player(message.from_user.id):
        return await message.reply("⚠️ <b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ʀᴇɢɪsᴛᴇʀᴇᴅ.</b>", parse_mode=ParseMode.HTML)

    balance = await _get_balance(message.from_user.id, currency)
    if balance < amount:
        return await message.reply(f"❌ <b>ɪɴsᴜꜰꜰɪᴄɪᴇɴᴛ {currency.upper()}.</b>", parse_mode=ParseMode.HTML)

    ok = await _deduct(message.from_user.id, amount, currency)
    if not ok:
        return await message.reply(f"❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ {currency.upper()}.</b>", parse_mode=ParseMode.HTML)

    game.add_player(message.from_user.id, _name(message.from_user), _mention(message.from_user))
    await ensure_stats(message.from_user.id, _name(message.from_user))

    m = await message.reply(
        f"👤 <b>{_mention(message.from_user)} ʀᴇɢɪsᴛᴇʀᴇᴅ ꜰᴏʀ ʜᴀᴄᴋ!</b>\n"
        f"<i>(ᴛᴏᴛᴀʟ: {len(game.players)}/{MAX_PLAYERS})</i>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if len(game.players) >= MAX_PLAYERS:
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await app.send_message(
            game.chat_id,
            "🔥 <b>10 ᴘʟᴀʏᴇʀs ʀᴇɢɪsᴛᴇʀᴇᴅ! ɢᴀᴍᴇ sᴛᴀʀᴛɪɴɢ ɴᴏᴡ...</b>",
            parse_mode=ParseMode.HTML,
        )
        await _start_game(game)


# ══════════════════════════════════════════════════════════════════════════════
#  Game start
# ══════════════════════════════════════════════════════════════════════════════
async def _start_game(game: HackGame):
    if game.state != "lobby":
        return
    if len(game.players) < MIN_PLAYERS:
        return await _cancel_game(game, "ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀs")

    game.state = "running"
    game.secret_code = generate_secret(game.code_length)
    game.remaining_guesses = game.max_guesses

    players_line = "\n".join(f"👤 {p['mention']}" for p in game.players)
    pool = game.prize_pool()

    try:
        start_msg = await app.send_message(
            game.chat_id,
            "🛰 <b>ʜᴀᴄᴋ ɢᴀᴍᴇ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"🔢 <b>ᴄᴏᴅᴇ ʟᴇɴɢᴛʜ:</b> <code>{game.code_length}</code> ᴅɪɢɪᴛs\n"
            f"💰 <b>ᴘʀɪᴢᴇ ᴘᴏᴏʟ:</b> <code>{pool}</code> ᴄᴏɪɴs\n"
            f"👥 <b>ᴘʟᴀʏᴇʀs:</b> <code>{len(game.players)}</code>\n\n"
            f"👉 ᴛʏᴘᴇ <code>/guess 123</code> ᴛᴏ ɢᴜᴇss ᴏʀ ɢᴇᴛ ɪᴛ ᴡʀᴏɴɢ.\n\n"
            f"{players_line}\n\n"
            f"<i>📝 ʀᴜʟᴇs: ᴅɪɢɪᴛs 1-9, ɴᴏ 0, ɴᴏ ʀᴇᴘᴇᴀᴛs</i>",
            parse_mode=ParseMode.HTML,
        )
        game.pinned_msg_id = start_msg.id
        try:
            await app.pin_chat_message(game.chat_id, start_msg.id, disable_notification=True)
        except Exception as e:
            print(f"[HACK pin] {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"[HACK start-msg] {type(e).__name__}: {e}", flush=True)

    await _start_turn(game, new_round=True)


async def _start_turn(game: HackGame, new_round: bool = False):
    current = game.current_player()
    if not current:
        return
    if game.remaining_guesses <= 0:
        return await _game_over_elara_wins(game, reason="ɴᴏ ɢᴜᴇssᴇs ʀᴇᴍᴀɪɴɪɴɢ")

    m = await app.send_message(
        game.chat_id,
        f"👉 {current['mention']}, ɪᴛ's ʏᴏᴜʀ ᴛᴜʀɴ!\n"
        f"⏳ ʏᴏᴜ ʜᴀᴠᴇ <code>{TURN_SECONDS}</code> sᴇᴄᴏɴᴅs.\n"
        f"🤖 ᴛʏᴘᴇ <code>/guess &lt;{game.code_length}-ᴅɪɢɪᴛs&gt;</code>\n"
        f"<i>📝 ɴᴏ 0, ɴᴏ ʀᴇᴘᴇᴀᴛs</i>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()
    game.turn_task = asyncio.create_task(_turn_timeout(game, current["user_id"], TURN_SECONDS))


async def _turn_timeout(game: HackGame, user_id: int, seconds: int = TURN_SECONDS):
    try:
        await asyncio.sleep(seconds)
        if game.state != "running":
            return
        current = game.current_player()
        if not current or current["user_id"] != user_id:
            return

        player = game.get_player(user_id)
        if not player:
            return

        # ── Register miss ──
        player["misses"] = player.get("misses", 0) + 1
        miss_count = player["misses"]

        if miss_count == 1:
            # ⚠️ First miss → warning only
            m = await app.send_message(
                game.chat_id,
                f"⚠️ <b>ᴡᴀʀɴɪɴɢ!</b>\n\n"
                f"{player['mention']} ᴛɪᴍᴇᴅ ᴏᴜᴛ — <b>1sᴛ ᴍɪss</b>.\n"
                f"<i>ᴇᴋ ᴀᴜʀ ᴍɪss = sᴇᴇᴅʜᴀ ᴋɪᴄᴋ 👢</i>",
                parse_mode=ParseMode.HTML,
            )
            await _track(game, m)
            game.next_turn()
            await _start_turn(game)
            return

        # ── 2nd miss → kick ──
        kicked = game.kick_player(user_id)
        if not kicked:
            return

        try:
            await app.send_message(
                user_id,
                "👢 <b>ʏᴏᴜ ᴡᴇʀᴇ ᴋɪᴄᴋᴇᴅ!</b>\n\n"
                f"<i>2 ᴛɪᴍᴇᴏᴜᴛs ɪɴ ᴀ ʀᴏᴡ. ʏᴏᴜʀ ᴇɴᴛʀʏ ꜰᴇᴇ sᴛᴀʏs ɪɴ ᴛʜᴇ ᴘᴏᴛ.</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        remaining = len(game.players)
        m = await app.send_message(
            game.chat_id,
            f"👢 <b>ᴋɪᴄᴋᴇᴅ!</b>\n\n"
            f"{kicked['mention']} ʜᴀs ʙᴇᴇɴ ᴋɪᴄᴋᴇᴅ ᴏᴜᴛ — <b>2 ᴛɪᴍᴇᴏᴜᴛs</b>.\n"
            f"💰 ᴛʜᴇɪʀ ᴇɴᴛʀʏ ꜰᴇᴇ sᴛᴀʏs ɪɴ ᴛʜᴇ ᴘᴏᴛ.\n"
            f"👥 <b>ʀᴇᴍᴀɪɴɪɴɢ ᴘʟᴀʏᴇʀs:</b> <code>{remaining}</code>",
            parse_mode=ParseMode.HTML,
        )
        await _track(game, m)

        if remaining == 0:
            return await _game_over_elara_wins(game, reason="ᴀʟʟ ᴘʟᴀʏᴇʀs ᴇʟɪᴍɪɴᴀᴛᴇᴅ")

        if game.remaining_guesses <= 0:
            return await _game_over_elara_wins(game, reason="ɴᴏ ɢᴜᴇssᴇs ʀᴇᴍᴀɪɴɪɴɢ")

        game.turn_index = 0
        await _start_turn(game)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[HACK turn] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  /guess — works in GROUP + DM
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("guess", prefixes=PREFIXES))
async def hack_guess(_, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    game = None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        game = get_game(message.chat.id)
    else:
        for g in list(ACTIVE_GAMES.values()):
            if g.has_player(user_id) and g.state == "running":
                game = g
                break

    if not game or game.state == "finished":
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ʜᴀᴄᴋ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)
    if game.state != "running":
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("❌ <b>ɢᴀᴍᴇ ʜᴀs ɴᴏᴛ sᴛᴀʀᴛᴇᴅ ʏᴇᴛ.</b>", parse_mode=ParseMode.HTML)

    if not game.has_player(user_id):
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʀᴇɢɪsᴛᴇʀᴇᴅ ɪɴ ᴛʜɪs ʜᴀᴄᴋ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)

    current = game.current_player()
    if not current or current["user_id"] != user_id:
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("⏳ <b>ɪᴛ's ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ!</b>", parse_mode=ParseMode.HTML)

    args = list(message.command or [])[1:]
    guess = args[0].strip() if args else ""

    # ✅ Validate guess — specific error messages
    is_valid, reason = is_valid_guess(guess, game.code_length)

    if not is_valid:
        if reason == "not_number":
            err_msg = "❌ <b>ᴇɴᴛᴇʀ ᴀ ɴᴜᴍʙᴇʀ!</b>"
        elif reason == "wrong_length":
            err_msg = (
                f"❌ <b>ᴍᴜsᴛ ʙᴇ ᴇxᴀᴄᴛʟʏ {game.code_length} ᴅɪɢɪᴛs!</b>"
            )
        elif reason == "has_zero":
            err_msg = "❌ <b>0 (ᴢᴇʀᴏ) ɴᴏᴛ ᴀʟʟᴏᴡᴇᴅ!</b>\n<i>ᴏɴʟʏ ᴅɪɢɪᴛs 1-9.</i>"
        elif reason == "repeated":
            err_msg = "❌ <b>ɴᴏ ʀᴇᴘᴇᴀᴛᴇᴅ ᴅɪɢɪᴛs!</b>\n<i>ᴇᴀᴄʜ ᴅɪɢɪᴛ ᴏɴʟʏ ᴏɴᴄᴇ.</i>"
        else:
            err_msg = "❌ <b>ɪɴᴠᴀʟɪᴅ ɢᴜᴇss — ᴛʀʏ ᴀɢᴀɪɴ!</b>"

        if message.chat.type == ChatType.PRIVATE:
            try:
                await message.reply(err_msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return

        return await message.reply(
            err_msg + "\n\n<i>ᴛᴜʀɴ ɴᴏᴛ ʟᴏsᴛ — ᴛʀʏ ᴀɢᴀɪɴ.</i>",
            parse_mode=ParseMode.HTML,
        )

    if guess in game.used_guesses:
        if message.chat.type == ChatType.PRIVATE:
            return
        return await message.reply("⚠️ <b>ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ɢᴜᴇssᴇᴅ ᴛʜᴀᴛ ɴᴜᴍʙᴇʀ.</b>", parse_mode=ParseMode.HTML)

    # ── Valid guess — proceed normally ──
    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    hacks, glitches = score_guess(game.secret_code, guess)
    game.used_guesses.add(guess)
    game.remaining_guesses -= 1
    current["guesses_used"] += 1

    if message.chat.type == ChatType.PRIVATE:
        try:
            await message.reply(f"✅ ɢᴜᴇss ʀᴇᴄᴏʀᴅᴇᴅ: <code>{guess}</code>", parse_mode=ParseMode.HTML)
        except Exception:
            pass

    if guess == game.secret_code:
        return await _winner(game, message.from_user)

    m = await app.send_message(
        game.chat_id,
        f"💻 <b>{current['mention']} ᴀᴛᴛᴇᴍᴘᴛᴇᴅ:</b>\n\n"
        f"👀 <b>ɢᴜᴇss:</b> <code>{guess}</code>\n"
        f"🟩 <b>ʜᴀᴄᴋs:</b> <code>{hacks}</code>\n"
        f"🟨 <b>ɢʟɪᴛᴄʜᴇs:</b> <code>{glitches}</code>\n"
        f"⏳ <b>ɢᴜᴇssᴇs ʟᴇꜰᴛ:</b> <code>{game.remaining_guesses}</code>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if game.remaining_guesses <= 0:
        return await _game_over_elara_wins(game, reason="ɴᴏ ɢᴜᴇssᴇs ʀᴇᴍᴀɪɴɪɴɢ")

    game.next_turn()
    await _start_turn(game)


# ══════════════════════════════════════════════════════════════════════════════
#  /end
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("end", prefixes=PREFIXES) & filters.group)
async def hack_end(_, message: Message):
    if not _is_group(message):
        return
    game = get_game(message.chat.id)
    if not game or game.state == "finished":
        return await message.reply("❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ʜᴀᴄᴋ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)
    if int(message.from_user.id) != int(game.host_id):
        return await message.reply("❌ <b>ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ ʜᴏsᴛ ᴄᴀɴ ᴇɴᴅ ᴛʜᴇ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)

    await _cancel_game(game, "ᴇɴᴅᴇᴅ ʙʏ ʜᴏsᴛ")


# ══════════════════════════════════════════════════════════════════════════════
#  Winner / End states
# ══════════════════════════════════════════════════════════════════════════════
async def _winner(game: HackGame, winner_user):
    if game.state == "finished":
        return
    game.state = "finished"
    game.winner_id = winner_user.id

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    pool = game.prize_pool()
    fee = int(pool * GAME_FEE_PERCENT)
    prize = pool - fee

    if not game.payout_done:
        try:
            await _credit(winner_user.id, prize, game.currency)
        except Exception as e:
            print(f"[HACK payout] {type(e).__name__}: {e}", flush=True)

        await _credit_elara(fee, game.currency)

        try:
            await add_xp(winner_user.id, WINNER_XP)
        except Exception:
            pass
        for p in game.players + game.kicked:
            if p["user_id"] != winner_user.id:
                try:
                    await add_xp(p["user_id"], LOSER_XP)
                except Exception:
                    pass
        game.payout_done = True

    for p in game.players + game.kicked:
        try:
            await record_result(p["user_id"], p["name"], won=(p["user_id"] == winner_user.id))
        except Exception:
            pass

    streak_str = "1/1"
    try:
        from core.hack_engine import _lb_col
        col = _lb_col()
        if col is not None:
            doc = await col.find_one({"_id": int(winner_user.id)}, {"streak": 1, "best_streak": 1})
            if doc:
                streak_str = f"{int(doc.get('streak', 1))}/{int(doc.get('best_streak', 1))}"
    except Exception:
        pass

    players_line = "\n".join(f"👤 {p['mention']}" for p in game.players)

    await _delete_all_game_messages(game)

    group_text = (
        "🎉 <b>ᴡᴇ ʜᴀᴠᴇ ᴀ ᴡɪɴɴᴇʀ!</b>\n\n"
        f"👤 <b>ᴡɪɴɴᴇʀ:</b> {_mention(winner_user)}\n"
        f"🔑 <b>ᴄᴏᴅᴇ ᴡᴀs:</b> <code>{game.secret_code}</code>\n\n"
        f"💰 <b>ᴘᴏᴛ:</b> <code>{pool}</code>\n"
        f"💸 <b>ᴘʀɪᴢᴇ:</b> <code>{prize}</code> <i>(10% ꜰᴇᴇ)</i>\n"
        f"🔥 <b>sᴛʀᴇᴀᴋ:</b> <code>{streak_str}</code>\n"
        f"⚡ <b>xᴘ ɢᴀɪɴᴇᴅ:</b> <code>+{WINNER_XP}</code>\n\n"
        f"👥 <b>ᴘʟᴀʏᴇʀs:</b>\n{players_line}\n\n"
        f"👉 ᴘʟᴀʏ ᴀɢᴀɪɴ ᴜsɪɴɢ:\n"
        f"<code>/hack {game.entry_amount} {game.code_length}</code>"
    )

    winner_photo_path = None
    winner_photo_url = None
    try:
        async for ph in app.get_chat_photos(winner_user.id, limit=1):
            file_id = getattr(ph, "big_file_id", None) or getattr(ph, "file_id", None) or getattr(ph, "small_file_id", None)
            if file_id:
                winner_photo_path = await app.download_media(
                    file_id, file_name="/tmp/elara_hack_winner.jpg"
                )
            break
    except Exception as e:
        print(f"[HACK photo] FAIL: {type(e).__name__}: {e}", flush=True)

    if not winner_photo_path:
        cfg_img = (getattr(config, "HACK_WINNER_IMAGE", "") or "").strip()
        if cfg_img:
            winner_photo_url = cfg_img

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
            print(f"[HACK photo-send] {type(e).__name__}: {e}", flush=True)
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
            print(f"[HACK url-send] {type(e).__name__}: {e}", flush=True)
            final_msg = None

    if final_msg is None:
        try:
            final_msg = await app.send_message(game.chat_id, group_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"[HACK text-send] {type(e).__name__}: {e}", flush=True)

    try:
        if final_msg:
            await app.pin_chat_message(game.chat_id, final_msg.id, disable_notification=True)
    except Exception as e:
        print(f"[HACK pin-final] {type(e).__name__}: {e}", flush=True)

    if winner_photo_path and os.path.exists(winner_photo_path):
        try:
            os.remove(winner_photo_path)
        except Exception:
            pass

    for p in game.players + game.kicked:
        is_winner = p["user_id"] == winner_user.id
        try:
            await app.send_message(
                p["user_id"],
                "🏁 <b>ʜᴀᴄᴋ ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
                f"👑 <b>ᴡɪɴɴᴇʀ:</b> {_mention(winner_user)}\n"
                f"🔑 <b>ᴄᴏᴅᴇ ᴡᴀs:</b> <code>{game.secret_code}</code>\n"
                f"💰 <b>ʏᴏᴜ ᴡᴏɴ:</b> <code>{prize if is_winner else 0}</code>\n"
                f"⚡ <b>xᴘ:</b> <code>+{WINNER_XP if is_winner else LOSER_XP}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    remove_game(game.chat_id)


async def _game_over_elara_wins(game: HackGame, reason: str = ""):
    """Game ends with no winner → Elara takes the whole pot. No refunds."""
    if game.state == "finished":
        return
    game.state = "finished"

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    pool = game.prize_pool()
    if pool > 0:
        await _credit_elara(pool, game.currency)

    await _delete_all_game_messages(game)
    remove_game(game.chat_id)

    players_line = "\n".join(
        f"👤 {p['mention']}" for p in (game.players + game.kicked)
    ) or "—"

    try:
        m = await app.send_message(
            game.chat_id,
            "💀 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ — ɴᴏ ᴡɪɴɴᴇʀ</b>\n\n"
            f"🔑 <b>sᴇᴄʀᴇᴛ ᴄᴏᴅᴇ:</b> <code>{game.secret_code}</code>\n"
            f"💰 <b>ᴛᴏᴛᴀʟ ᴘᴏᴛ:</b> <code>{pool}</code>\n\n"
            f"👑 <b>ᴇʟᴀʀᴀ ᴛᴀᴋᴇs ᴛʜᴇ ᴘᴏᴛ!</b>\n"
            f"<i>{_esc(reason) if reason else 'ɴᴏ ᴏɴᴇ ᴄʀᴀᴄᴋᴇᴅ ᴛʜᴇ ᴄᴏᴅᴇ.'}</i>\n\n"
            f"👥 <b>ᴘʟᴀʏᴇʀs:</b>\n{players_line}",
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(15)
        try:
            await app.delete_messages(game.chat_id, m.id)
        except Exception:
            pass
    except Exception:
        pass

    for p in (game.players + game.kicked):
        try:
            await app.send_message(
                p["user_id"],
                "💀 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ — ɴᴏ ᴡɪɴɴᴇʀ</b>\n\n"
                f"🔑 <b>sᴇᴄʀᴇᴛ ᴄᴏᴅᴇ:</b> <code>{game.secret_code}</code>\n"
                f"💰 <b>ᴘᴏᴛ ɢᴏᴇs ᴛᴏ ᴇʟᴀʀᴀ.</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def _cancel_game(game: HackGame, reason: str):
    """Host ne /end kiya → full refunds to active + kicked players."""
    if game.state == "finished":
        return
    game.state = "finished"

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    for p in game.players + game.kicked:
        try:
            await _credit(p["user_id"], game.entry_amount, game.currency)
        except Exception:
            pass

    await _delete_all_game_messages(game)
    remove_game(game.chat_id)

    try:
        m = await app.send_message(
            game.chat_id,
            f"❌ <b>ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n<i>{_esc(reason)}</i>\n"
            "💰 ᴀʟʟ ᴇɴᴛʀʏ ꜰᴇᴇs ʀᴇꜰᴜɴᴅᴇᴅ.",
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(10)
        try:
            await app.delete_messages(game.chat_id, m.id)
        except Exception:
            pass
    except Exception:
        pass