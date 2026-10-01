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
    TURN_SECONDS,
    VALID_LENGTHS,
    WINNER_XP,
    HackGame,
    create_game,
    ensure_stats,
    generate_secret,
    get_game,
    record_result,
    remove_game,
    score_guess,
    top_hackers,
)

PREFIXES = ["/", "!", "."]
MIN_PLAYERS = 2
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
    """✅ Tax → Elara ke paas."""
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
            "❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/hack &lt;amount&gt; &lt;digits&gt;</code>\n"
            "<i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/hack 500 3</code>",
            parse_mode=ParseMode.HTML,
        )
    try:
        amount = int(args[0])
        length = int(args[1])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀꜱ.</b>", parse_mode=ParseMode.HTML)

    if amount < ENTRY_MIN or amount > ENTRY_MAX:
        return await message.reply(
            f"❌ ᴇɴᴛʀʏ ᴍᴜꜱᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ <code>{ENTRY_MIN}</code> ᴀɴᴅ <code>{ENTRY_MAX}</code>.",
            parse_mode=ParseMode.HTML,
        )
    if length not in VALID_LENGTHS:
        return await message.reply(
            "❌ ᴄᴏᴅᴇ ʟᴇɴɢᴛʜ ᴍᴜꜱᴛ ʙᴇ <code>3</code>, <code>4</code>, <code>5</code> ᴏʀ <code>6</code>.",
            parse_mode=ParseMode.HTML,
        )

    existing = get_game(message.chat.id)
    if existing and not existing.is_finished():
        return await message.reply(
            "⚠️ <b>ᴀ ʜᴀᴄᴋ ɢᴀᴍᴇ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ɪɴ ᴛʜɪꜱ ᴄʜᴀᴛ.</b>",
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
        "💻 <b>ʜᴀᴄᴋᴇʀ ʟᴏʙʙʏ ꜱᴛᴀʀᴛᴇᴅ!</b>\n\n"
        f"💰 <b>ᴇɴᴛʀʏ ꜰᴇᴇ:</b> <code>{amount}</code> ᴄᴏɪɴꜱ\n"
        f"🔐 <b>ᴛᴀʀɢᴇᴛ ʟᴇɴɢᴛʜ:</b> <code>{length}</code> ᴅɪɢɪᴛꜱ\n\n"
        f"👉 ʀᴇɢɪꜱᴛᴇʀ ᴜꜱɪɴɢ: <code>/register {amount}</code>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)


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
        return await message.reply("❌ <b>ɢᴀᴍᴇ ʜᴀꜱ ᴀʟʀᴇᴀᴅʏ ꜱᴛᴀʀᴛᴇᴅ.</b>", parse_mode=ParseMode.HTML)

    args = list(message.command or [])[1:]
    if not args:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/register &lt;amount&gt; [coins|gems]</code>", parse_mode=ParseMode.HTML)
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
        return await message.reply("⚠️ <b>ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ʀᴇɢɪꜱᴛᴇʀᴇᴅ.</b>", parse_mode=ParseMode.HTML)

    balance = await _get_balance(message.from_user.id, currency)
    if balance < amount:
        return await message.reply(f"❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ {currency.upper()}.</b>", parse_mode=ParseMode.HTML)

    ok = await _deduct(message.from_user.id, amount, currency)
    if not ok:
        return await message.reply(f"❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ {currency.upper()}.</b>", parse_mode=ParseMode.HTML)

    game.add_player(message.from_user.id, _name(message.from_user), _mention(message.from_user))
    await ensure_stats(message.from_user.id, _name(message.from_user))

    m = await message.reply(
        f"👤 <b>{_mention(message.from_user)} ᴊᴏɪɴᴇᴅ ᴛʜᴇ ʜᴀᴄᴋ ᴛᴇᴀᴍ!</b>\n"
        f"<i>(ᴛᴏᴛᴀʟ: {len(game.players)})</i>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if len(game.players) >= MIN_PLAYERS:
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _start_game(game)


# ══════════════════════════════════════════════════════════════════════════════
#  Game start
# ══════════════════════════════════════════════════════════════════════════════
async def _start_game(game: HackGame):
    if game.state != "lobby":
        return
    if len(game.players) < MIN_PLAYERS:
        return await _cancel_game(game, "ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ")

    game.state = "running"
    game.secret_code = generate_secret(game.code_length)
    game.remaining_guesses = game.max_guesses

    players_line = "\n".join(f"👤 {p['mention']}" for p in game.players)
    pool = game.prize_pool()

    try:
        start_msg = await app.send_message(
            game.chat_id,
            "🚀 <b>ʜᴀᴄᴋ ꜱᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"🔢 <b>ᴄᴏᴅᴇ ʟᴇɴɢᴛʜ:</b> <code>{game.code_length}</code> ᴅɪɢɪᴛꜱ\n"
            f"💰 <b>ᴘʀɪᴢᴇ ᴘᴏᴏʟ:</b> <code>{pool}</code> ᴄᴏɪɴꜱ\n\n"
            f"👉 ᴜꜱᴇ <code>/guess 123</code> ᴏɴ ʏᴏᴜʀ ᴛᴜʀɴ.\n\n"
            f"{players_line}",
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
        return await _game_over_no_winner(game)

    m = await app.send_message(
        game.chat_id,
        f"👉 {current['mention']}, ɪᴛ'ꜱ ʏᴏᴜʀ ᴛᴜʀɴ!\n"
        f"⏳ ʏᴏᴜ ʜᴀᴠᴇ <code>1</code> ᴍɪɴᴜᴛᴇ.\n"
        f"🃏 ᴜꜱᴇ <code>/guess &lt;{game.code_length}-ᴅɪɢɪᴛꜱ&gt;</code>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()
    game.turn_task = asyncio.create_task(_turn_timeout(game, current["user_id"]))


async def _turn_timeout(game: HackGame, user_id: int):
    try:
        await asyncio.sleep(TURN_SECONDS)
        if game.state != "running":
            return
        current = game.current_player()
        if not current or current["user_id"] != user_id:
            return
        m = await app.send_message(
            game.chat_id,
            f"⏰ {current['mention']} ᴛɪᴍᴇᴅ ᴏᴜᴛ! ᴛᴜʀɴ ꜱᴋɪᴘᴘᴇᴅ.",
            parse_mode=ParseMode.HTML,
        )
        await _track(game, m)
        game.next_turn()
        await _start_turn(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[HACK turn] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  /guess
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("guess", prefixes=PREFIXES) & filters.group)
async def hack_guess(_, message: Message):
    if not _is_group(message):
        return
    game = get_game(message.chat.id)
    if not game or game.state == "finished":
        return await message.reply("❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ʜᴀᴄᴋ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)
    if game.state != "running":
        return await message.reply("❌ <b>ɢᴀᴍᴇ ɴᴏᴛ ꜱᴛᴀʀᴛᴇᴅ ʏᴇᴛ.</b>", parse_mode=ParseMode.HTML)

    if not game.has_player(message.from_user.id):
        return await message.reply("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ʀᴇɢɪꜱᴛᴇʀᴇᴅ ɪɴ ᴛʜɪꜱ ʜᴀᴄᴋ ɢᴀᴍᴇ.", parse_mode=ParseMode.HTML)

    current = game.current_player()
    if not current or current["user_id"] != message.from_user.id:
        return await message.reply("⏳ <b>ɪᴛ'ꜱ ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ!</b>", parse_mode=ParseMode.HTML)

    args = list(message.command or [])[1:]
    guess = args[0].strip() if args else ""
    if len(guess) != game.code_length or not guess.isdigit():
        return await message.reply(
            f"❌ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴅᴇ!</b>\n🔢 ᴇɴᴛᴇʀ ᴇxᴀᴄᴛʟʏ <code>{game.code_length}</code> ᴅɪɢɪᴛꜱ.",
            parse_mode=ParseMode.HTML,
        )

    if guess in game.used_guesses:
        return await message.reply("⚠️ <b>ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴜꜱᴇᴅ ᴛʜɪꜱ ɢᴜᴇꜱꜱ.</b>", parse_mode=ParseMode.HTML)

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    hacks, glitches = score_guess(game.secret_code, guess)
    game.used_guesses.add(guess)
    game.remaining_guesses -= 1
    current["guesses_used"] += 1

    if guess == game.secret_code:
        return await _winner(game, message.from_user)

    m = await app.send_message(
        game.chat_id,
        f"💻 <b>{current['mention']} ᴀᴛᴛᴀᴄᴋ:</b>\n\n"
        f"👀 <b>ɢᴜᴇꜱꜱ:</b> <code>{guess}</code>\n"
        f"🟩 <b>ʜᴀᴄᴋꜱ:</b> <code>{hacks}</code>\n"
        f"🟨 <b>ɢʟɪᴛᴄʜᴇꜱ:</b> <code>{glitches}</code>\n"
        f"⏳ <b>ɢᴜᴇꜱꜱᴇꜱ ʟᴇꜰᴛ:</b> <code>{game.remaining_guesses}</code>",
        parse_mode=ParseMode.HTML,
    )
    await _track(game, m)

    if game.remaining_guesses <= 0:
        return await _game_over_no_winner(game)

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
        return await message.reply("❌ <b>ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ ʜᴏꜱᴛ ᴄᴀɴ ᴇɴᴅ ᴛʜɪꜱ ɢᴀᴍᴇ.</b>", parse_mode=ParseMode.HTML)

    await _cancel_game(game, "ᴇɴᴅᴇᴅ ʙʏ ʜᴏꜱᴛ")


# ══════════════════════════════════════════════════════════════════════════════
#  End states
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
        # ✅ Winner → prize
        try:
            await _credit(winner_user.id, prize, game.currency)
        except Exception as e:
            print(f"[HACK payout] {type(e).__name__}: {e}", flush=True)

        # ✅ Tax (10% fee) → Elara
        await _credit_elara(fee, game.currency)

        # ✅ XP
        try:
            await add_xp(winner_user.id, WINNER_XP)
        except Exception:
            pass
        for p in game.players:
            if p["user_id"] != winner_user.id:
                try:
                    await add_xp(p["user_id"], LOSER_XP)
                except Exception:
                    pass
        game.payout_done = True

    for p in game.players:
        try:
            await record_result(p["user_id"], p["name"], won=(p["user_id"] == winner_user.id))
        except Exception:
            pass

    # Streak fetch
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
        "💀 <b>ᴘᴀꜱꜱᴡᴏʀᴅ ʜᴀᴄᴋᴇᴅ</b>\n\n"
        f"👤 <b>ᴡɪɴɴᴇʀ:</b> {_mention(winner_user)}\n"
        f"🔑 <b>ᴄᴏᴅᴇ ᴡᴀꜱ:</b> <code>{game.secret_code}</code>\n\n"
        f"💰 <b>ᴡᴏɴ:</b> <code>{prize}</code> (👤 10% ꜰᴇᴇ)\n"
        f"🔥 <b>ꜱᴛʀᴇᴀᴋ:</b> <code>{streak_str}</code>\n"
        f"⚡ <b>xᴘ ɢᴀɪɴᴇᴅ:</b> <code>+{WINNER_XP}</code>\n\n"
        f"👥 <b>ᴘʟᴀʏᴇʀꜱ:</b>\n{players_line}\n\n"
        f"👉 ᴘʟᴀʏ ᴀɢᴀɪɴ ᴜꜱɪɴɢ:\n"
        f"<code>/hack {game.entry_amount} {game.code_length}</code>"
    )

    # ✅ Try with winner pfp
    winner_photo_path = None
    winner_photo_url = None
    try:
        async for ph in app.get_chat_photos(winner_user.id, limit=1):
            winner_photo_path = await app.download_media(
                ph.file_id, file_name="/tmp/elara_hack_winner.jpg"
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

    # ✅ Pin final
    try:
        if final_msg:
            await app.pin_chat_message(game.chat_id, final_msg.id, disable_notification=True)
    except Exception as e:
        print(f"[HACK pin-final] {type(e).__name__}: {e}", flush=True)

    # Cleanup temp
    if winner_photo_path and os.path.exists(winner_photo_path):
        try:
            os.remove(winner_photo_path)
        except Exception:
            pass

    # DM results
    for p in game.players:
        is_winner = p["user_id"] == winner_user.id
        try:
            await app.send_message(
                p["user_id"],
                "🏁 <b>ʜᴀᴄᴋ ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
                f"👑 <b>ᴡɪɴɴᴇʀ:</b> {_mention(winner_user)}\n"
                f"🔑 <b>ᴄᴏᴅᴇ ᴡᴀꜱ:</b> <code>{game.secret_code}</code>\n"
                f"💰 <b>ʏᴏᴜ ᴡᴏɴ:</b> <code>{prize if is_winner else 0}</code>\n"
                f"⚡ <b>xᴘ:</b> <code>+{WINNER_XP if is_winner else LOSER_XP}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    remove_game(game.chat_id)


async def _game_over_no_winner(game: HackGame):
    if game.state == "finished":
        return
    game.state = "finished"

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    # Refund all players
    for p in game.players:
        try:
            await _credit(p["user_id"], game.entry_amount, game.currency)
        except Exception:
            pass

    await _delete_all_game_messages(game)
    remove_game(game.chat_id)

    try:
        m = await app.send_message(
            game.chat_id,
            "💀 <b>ɢᴀᴍᴇ ᴏᴠᴇʀ!</b>\n\n"
            f"🔑 ᴄᴏᴅᴇ ᴡᴀꜱ: <code>{game.secret_code}</code>\n"
            "😔 ɴᴏ ᴏɴᴇ ꜱᴏʟᴠᴇᴅ ɪᴛ. ᴀʟʟ ᴇɴᴛʀʏ ꜰᴇᴇꜱ ʀᴇꜰᴜɴᴅᴇᴅ.",
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(10)
        try:
            await app.delete_messages(game.chat_id, m.id)
        except Exception:
            pass
    except Exception:
        pass


async def _cancel_game(game: HackGame, reason: str):
    if game.state == "finished":
        return
    game.state = "finished"

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    for p in game.players:
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
            "💰 ᴀʟʟ ᴇɴᴛʀʏ ꜰᴇᴇꜱ ʀᴇꜰᴜɴᴅᴇᴅ.",
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
#  /hackleaders — leaderboard
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["hackleaders", "hacktop"], prefixes=PREFIXES))
async def hack_leaders(_, message: Message):
    rows = await top_hackers(10)
    if not rows:
        return await message.reply("❌ ɴᴏ ʜᴀᴄᴋ ɢᴀᴍᴇ ꜱᴛᴀᴛꜱ ʏᴇᴛ.", parse_mode=ParseMode.HTML)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>ᴇʟᴀʀᴀ ʜᴀᴄᴋ ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀꜱ</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        name = row.get("name") or str(row["_id"])
        won = int(row.get("won", 0))
        streak = int(row.get("streak", 0))
        lines.append(
            f"{rank} <b>{_esc(name)}</b> — <code>{won}</code> ᴡɪɴꜱ • 🔥 <code>{streak}</code>"
        )
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)
