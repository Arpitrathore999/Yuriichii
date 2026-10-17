# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/pixelbattle.py — 🎨 PIXEL BATTLE v3
#  ✅ Auto-eliminate stuck players
#  ✅ 4 skips = kick
#  ✅ Deep link join (fix /start interception)
#  ✅ Easy / Medium / Hard modes
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import os
import random
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
from core.pixelbattle_engine import (
    ACTIVE_GAMES,
    DEFAULT_MODE,
    EMPTY,
    ENTRY_MAX,
    ENTRY_MIN,
    GAME_FEE_PERCENT,
    LOBBY_SECONDS,
    LOSER_XP,
    MAX_PLAYERS,
    MAX_SKIPS_PER_PLAYER,
    MIN_PLAYERS,
    MODE_CONFIG,
    MODE_EASY,
    MODE_HARD,
    MODE_MEDIUM,
    STATE_CANCELLED,
    STATE_FINISHED,
    STATE_LOBBY,
    STATE_PLAYING,
    TURN_SECONDS,
    USER_ACTIVE,
    WINNER_XP,
    PixelGame,
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
        print(f"[Pixel send] {type(e).__name__}: {e}", flush=True)
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


async def _send_tracked(game: PixelGame, text: str, **kw):
    msg = await _safe_send(game.chat_id, text, **kw)
    if msg and getattr(msg, "id", None):
        game.game_messages.append(msg.id)
    return msg


async def _cleanup_game_messages(game: PixelGame, keep_ids: list[int] | None = None):
    keep_set = set(int(x) for x in (keep_ids or []) if x)
    to_delete = [int(mid) for mid in game.game_messages if int(mid) not in keep_set]
    if not to_delete:
        return 0

    deleted = 0
    for i in range(0, len(to_delete), 100):
        chunk = to_delete[i:i+100]
        try:
            await app.delete_messages(game.chat_id, chunk)
            deleted += len(chunk)
        except Exception:
            for mid in chunk:
                try:
                    await app.delete_messages(game.chat_id, mid)
                    deleted += 1
                except Exception:
                    pass
    game.game_messages.clear()
    print(f"[Pixel cleanup] Deleted {deleted} messages", flush=True)
    return deleted


async def _get_group_name(chat_id: int) -> str:
    try:
        chat = await app.get_chat(chat_id)
        return getattr(chat, "title", "") or f"Group {chat_id}"
    except Exception:
        return f"Group {chat_id}"


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
        print(f"[Pixel ensure_user] {type(e).__name__}: {e}", flush=True)


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
        print(f"[Pixel tax] {type(e).__name__}: {e}", flush=True)
        return False


async def _payout_winner(uid: int, amount: int) -> bool:
    if amount <= 0:
        return False
    try:
        ok = await add_coins(int(uid), int(amount))
        if ok:
            return True
    except Exception as e:
        print(f"[Pixel payout] add_coins {type(e).__name__}: {e}", flush=True)

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
        print(f"[Pixel payout fallback] {type(e).__name__}: {e}", flush=True)
        return False


async def _fetch_user_photo(uid: int) -> str | None:
    try:
        user = await app.get_users(int(uid))
        photo = getattr(user, "photo", None)
        if photo:
            file_id = (getattr(photo, "big_file_id", None) or
                       getattr(photo, "small_file_id", None))
            if file_id:
                path = await app.download_media(file_id, file_name=f"/tmp/pixel_winner_{uid}.jpg")
                if path and os.path.exists(path):
                    return path
    except Exception as e:
        print(f"[Pixel PFP get_users] {type(e).__name__}: {e}", flush=True)

    try:
        async for ph in app.get_chat_photos(int(uid), limit=1):
            file_id = (getattr(ph, "big_file_id", None) or
                       getattr(ph, "file_id", None) or
                       getattr(ph, "small_file_id", None))
            if file_id:
                path = await app.download_media(file_id, file_name=f"/tmp/pixel_winner_{uid}.jpg")
                if path and os.path.exists(path):
                    return path
            break
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  RENDERERS
# ══════════════════════════════════════════════════════════════════════════════
def _render_help() -> str:
    return (
        "🎨 <b>PIXEL BATTLE — The Territory War</b>\n\n"
        "Ek khali grid hai. Har player apne rang se cells bharta hai.\n"
        "Sabse zyada cells ka malik = WINNER! 🏆\n\n"
        "<b>🎮 QUICK START:</b>\n"
        "• <code>/pixel free</code> — Medium free game\n"
        "• <code>/pixel 500</code> — Medium paid game\n"
        "• <code>/pixel free easy</code> — Easy (5×10)\n"
        "• <code>/pixel free hard</code> — Hard (10×10)\n"
        "• <code>/joinpixel</code> — Join the lobby\n\n"
        "📖 Full rules & commands: <code>/pixelhelp</code>\n"
    )


def _render_help_full() -> str:
    return (
        "🎨 <b>PIXEL BATTLE — HOW TO PLAY & COMMANDS</b> 🎨\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📖 <b>HOW TO PLAY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "<b>1️⃣ LOBBY</b>\n"
        "• <code>/pixel free</code> or <code>/pixel 500</code> starts a lobby\n"
        "• Others join with <code>/joinpixel</code> or the JOIN button\n"
        "• 2–6 players required (60s to fill)\n\n"

        "<b>2️⃣ MODES</b>\n"
        "🟢 <b>Easy</b> — 5×10 grid (50 cells)\n"
        "🟡 <b>Medium</b> — 7×10 grid (70 cells)\n"
        "🔴 <b>Hard</b> — 10×10 grid (100 cells)\n"
        "• Add mode after amount: <code>/pixel 500 hard</code>\n\n"

        "<b>3️⃣ TURNS</b>\n"
        "• Pick 1 empty cell per turn\n"
        "• After 1st move: only cells adjacent to your own\n"
        "• 20 seconds per turn\n"
        "• Timeout = auto-random move (counts as SKIP)\n\n"

        "<b>4️⃣ SKIP RULE</b> ⏭️\n"
        f"• {MAX_SKIPS_PER_PLAYER} skips = <b>KICKED</b> from game\n"
        "• Last remaining player wins!\n\n"

        "<b>5️⃣ STUCK RULE</b> 🚫\n"
        "• If you have NO valid moves (fully blocked)\n"
        "• → You're <b>ELIMINATED</b> automatically\n"
        "• Others keep playing\n\n"

        "<b>6️⃣ GAME OVER</b>\n"
        "• Grid full OR 1 player left\n"
        "• Most cells = WINNER 🏆\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>MODES (paid)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Entry: {ENTRY_MIN}–{ENTRY_MAX} coins\n"
        "• Tax: 10%\n"
        "• Winner takes the net pool\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>COMMANDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎮 <b>Game</b>\n"
        "• <code>/pixel free</code> — Free Medium\n"
        "• <code>/pixel &lt;amount&gt;</code> — Paid Medium\n"
        "• <code>/pixel free easy</code> — Free Easy\n"
        "• <code>/pixel 500 hard</code> — Paid Hard\n"
        "• <code>/joinpixel</code> · <code>/pixelinfo</code> · <code>/pixelcancel</code>\n\n"
        "📊 <b>Stats</b>\n"
        "• <code>/pixelstats</code> · <code>/pixeltop</code>\n\n"
        "📖 <b>Help</b>\n"
        "• <code>/pixelhelp</code> · <code>/phelp</code>\n"
    )


def _render_lobby(game: PixelGame, secs_left: int) -> str:
    mode = f"💰 PAID — <code>{game.entry_fee}</code> coins/player" if game.is_paid else "🎮 FREE MODE"
    mode_badge = game.cfg["label"]
    grid_info = f"{game.rows}×{game.cols} ({game.total_cells()} cells)"

    lines = []
    for i, p in enumerate(game.players, 1):
        lines.append(f"{i}. {p['color']} {p['mention']}")
    lines_txt = "\n".join(lines) or "<i>No players yet — be the first!</i>"

    return (
        "🎨 <b>PIXEL BATTLE — LOBBY OPEN!</b> 🎨\n\n"
        f"📍 <b>Group:</b> {_esc(game.chat_name or 'this group')}\n"
        f"🎮 <b>Mode:</b> {mode}\n"
        f"🎯 <b>Difficulty:</b> {mode_badge}\n"
        f"📐 <b>Grid:</b> <code>{grid_info}</code>\n"
        f"👥 <b>Players:</b> <code>{len(game.players)}/{MAX_PLAYERS}</code> "
        f"<i>(min {MIN_PLAYERS})</i>\n"
        f"⏳ <b>Join time:</b> <code>{max(0, secs_left)}s</code>\n\n"
        f"👤 <b>Players:</b>\n{lines_txt}\n\n"
        "👉 <b>Tap JOIN below</b> (opens bot DM) or use <code>/joinpixel</code>"
    )


def _lobby_kb(game: PixelGame) -> InlineKeyboardMarkup:
    join_label = (f"➕ JOIN GAME ({game.entry_fee} coins)"
                  if game.is_paid else "➕ JOIN GAME (Free)")
    dm_link = f"https://t.me/{BOT_USERNAME}?start=pixel_join_{game.chat_id}"
    help_link = f"https://t.me/{BOT_USERNAME}?start=pixel_help"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(join_label, url=dm_link)],
        [InlineKeyboardButton("How to Play", url=help_link)],
    ])


def _render_grid(game: PixelGame) -> str:
    lines = []
    for row in game.grid:
        lines.append("".join(row))
    return "\n".join(lines)


def _render_board(game: PixelGame) -> str:
    current = game.current_player()
    grid_txt = _render_grid(game)

    sorted_players = sorted(game.players, key=lambda p: -p["cell_count"])
    score_lines = []
    for p in sorted_players:
        skips = p.get("skips", 0)
        skip_txt = f" ⏭️{skips}/{MAX_SKIPS_PER_PLAYER}" if skips > 0 else ""
        score_lines.append(f"{p['color']} {_esc(p['name'])}: <code>{p['cell_count']}</code>{skip_txt}")

    # Eliminated section
    elim_txt = ""
    if game.eliminated_players:
        elim_lines = []
        for p in game.eliminated_players:
            reason = p.get("elimination_reason", "eliminated")
            elim_lines.append(f"• {p['color']} {_esc(p['name'])} — <i>{_esc(reason)}</i>")
        elim_txt = f"\n\n💀 <b>Eliminated:</b>\n" + "\n".join(elim_lines)

    total = game.total_cells_claimed()
    total_cells = game.total_cells()

    current_txt = ""
    if current:
        current_txt = (
            f"\n\n👇 <b>It's {current['color']} {current['mention']}'s turn!</b>\n"
            f"⏱ <code>{TURN_SECONDS}s</code> to choose a cell."
        )

    return (
        f"🎨 <b>PIXEL BATTLE — Turn {game.turn_count + 1}</b>\n"
        f"<i>{game.cfg['label']} · {game.rows}×{game.cols}</i>\n\n"
        f"{grid_txt}\n\n"
        f"📊 <b>Scoreboard:</b>\n" + "\n".join(score_lines) +
        f"\n\n🎯 <b>Progress:</b> <code>{total}/{total_cells}</code>"
        f"{elim_txt}"
        f"{current_txt}"
    )


def _valid_moves_kb(game: PixelGame) -> InlineKeyboardMarkup:
    current = game.current_player()
    if not current:
        return InlineKeyboardMarkup([])

    valid = game.get_valid_moves(current["user_id"])
    if not valid:
        return InlineKeyboardMarkup([])

    random.shuffle(valid)
    shown = valid[:16]  # 4x4 buttons

    rows = []
    row = []
    for (r, c) in shown:
        row.append(InlineKeyboardButton(
            f"({r},{c})",
            callback_data=f"pixel_move:{game.chat_id}:{r}:{c}",
        ))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if len(valid) > 16:
        rows.append([InlineKeyboardButton(
            f"ℹ️ {len(valid) - 16} more cells available",
            callback_data=f"pixel_noop:{game.chat_id}",
        )])

    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  ✅ DEEP LINK — registered at group=-10 so it runs FIRST
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("start", prefixes=PREFIXES) & filters.private, group=-10)
async def pixel_deeplink(_, message: Message):
    if not message.command or len(message.command) < 2:
        raise StopPropagation  # let other handlers process normal /start

    payload = message.command[1].strip()

    # ── Help deep link ─────────────────────────────────────────────────────
    if payload == "pixel_help":
        await _safe_reply(message, _render_help_full(), parse_mode=ParseMode.HTML)
        raise StopPropagation

    # ── Join deep link ─────────────────────────────────────────────────────
    if not payload.startswith("pixel_join_"):
        raise StopPropagation  # let other handlers process

    try:
        chat_id = int(payload[len("pixel_join_"):])
    except ValueError:
        await _safe_reply(message, "❌ Invalid join link.", parse_mode=ParseMode.HTML)
        raise StopPropagation

    game = get_game(chat_id)
    user = message.from_user

    group_name = await _get_group_name(chat_id) if chat_id else "Unknown"
    if game and game.chat_name:
        group_name = game.chat_name

    if not game:
        await _safe_reply(
            message,
            f"❌ <b>No active Pixel Battle in</b> <b>{_esc(group_name)}</b>.\n"
            "<i>The lobby may have closed.</i>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    if game.state != STATE_LOBBY:
        await _safe_reply(
            message,
            f"❌ <b>The lobby in {_esc(group_name)} has already closed.</b>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    if game.has_player(user.id):
        await _safe_reply(
            message,
            f"⚠️ <b>You're already in the game in {_esc(group_name)}!</b>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    ok, reason = await _process_join(
        game, user.id, _name(user), _mention(user.id, _name(user)),
    )

    if not ok:
        await _safe_reply(message, f"❌ <b>Could not join:</b> {_esc(reason)}",
                          parse_mode=ParseMode.HTML)
        raise StopPropagation

    await _safe_reply(
        message,
        f"✅ <b>You joined Pixel Battle!</b>\n\n"
        f"📍 Group: <b>{_esc(group_name)}</b>\n"
        f"🎯 Mode: {game.cfg['label']}\n"
        f"👥 Players: <code>{len(game.players)}/{MAX_PLAYERS}</code>\n\n"
        "🎨 Your color will be assigned when the game starts.\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.HTML,
    )

    await _send_tracked(
        game,
        f"🔥 {_mention(user.id, _name(user))} joined the battle!",
        parse_mode=ParseMode.HTML,
    )

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
#  /pixelhelp /phelp
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["pixelhelp", "phelp"], prefixes=PREFIXES))
async def pixel_help_cmd(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await _safe_reply(message, _render_help_full(), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  /pixel [amount|free] [mode]
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["pixel"], prefixes=PREFIXES) & filters.group)
async def pixel_cmd(_, message: Message):
    if not _is_group(message) or not message.from_user:
        return

    args = list(message.command or [])[1:]
    if not args:
        return await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)

    is_paid = True
    entry_fee = 0
    mode = DEFAULT_MODE

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
                "Use <code>/pixel free [mode]</code> or <code>/pixel 500 [mode]</code>.",
                parse_mode=ParseMode.HTML,
            )
        if entry_fee < ENTRY_MIN or entry_fee > ENTRY_MAX:
            return await _safe_reply(
                message,
                f"❌ Entry must be between <code>{ENTRY_MIN}</code> and <code>{ENTRY_MAX}</code>.",
                parse_mode=ParseMode.HTML,
            )

    # ✅ Parse mode (2nd arg)
    if len(args) >= 2:
        m = args[1].lower().strip()
        if m in ("easy", "e"):
            mode = MODE_EASY
        elif m in ("medium", "med", "m"):
            mode = MODE_MEDIUM
        elif m in ("hard", "h"):
            mode = MODE_HARD
        else:
            return await _safe_reply(
                message,
                "❌ Invalid mode. Use <code>easy</code>, <code>medium</code>, or <code>hard</code>.",
                parse_mode=ParseMode.HTML,
            )

    existing = get_game(message.chat.id)
    if existing and not existing.is_terminal():
        return await _safe_reply(
            message,
            "⚠️ <b>A Pixel Battle is already running here.</b>",
            parse_mode=ParseMode.HTML,
        )

    user_game = get_user_game(message.from_user.id)
    if user_game and user_game.chat_id != message.chat.id:
        return await _safe_reply(
            message,
            "⚠️ <b>You are in another Pixel Battle.</b>",
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
        mode=mode,
    )
    game.state = STATE_LOBBY
    game.chat_name = getattr(message.chat, "title", "") or f"Group {message.chat.id}"

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
    if sent and getattr(sent, "id", None):
        game.lobby_message_id = sent.id
        game.game_messages.append(sent.id)
    await persist_game(game)

    game.lobby_task = asyncio.create_task(_lobby_timer(game))


# ══════════════════════════════════════════════════════════════════════════════
#  JOIN
# ══════════════════════════════════════════════════════════════════════════════
async def _process_join(game: PixelGame, uid: int, name: str, mention: str) -> tuple[bool, str]:
    if game.state != STATE_LOBBY:
        return False, "Lobby closed."
    if game.has_player(uid):
        return False, "Already in game."
    if game.is_full():
        return False, "Game is full."

    other = get_user_game(uid)
    if other and other.chat_id != game.chat_id:
        return False, "You are in another Pixel Battle."

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


@app.on_message(filters.command(["joinpixel"], prefixes=PREFIXES) & filters.group)
async def pixel_join_cmd(_, message: Message):
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
    await _send_tracked(
        game,
        f"🔥 {_mention(message.from_user.id, _name(message.from_user))} joined the battle!",
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
async def _lobby_timer(game: PixelGame):
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
        print(f"[Pixel lobby] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MATCH FLOW
# ══════════════════════════════════════════════════════════════════════════════
async def _begin_match(game: PixelGame):
    if game.state != STATE_LOBBY:
        return
    if not game.can_start():
        return await _cancel_and_refund(game, reason="Not enough players")

    game.init_grid()
    game.state = STATE_PLAYING
    game.turn_index = random.randint(0, len(game.players) - 1)
    game.turn_count = 0

    if game.is_paid:
        game.gross_pool = game.entry_fee * len(game.players)
        game.tax_amount = int(game.gross_pool * GAME_FEE_PERCENT)
        game.net_prize  = game.gross_pool - game.tax_amount

    await persist_game(game)

    lines = "\n".join(
        f"{i+1}. {p['color']} {p['mention']}" for i, p in enumerate(game.players)
    )
    await _send_tracked(
        game,
        "🎨 <b>PIXEL BATTLE — START!</b> 🎨\n\n"
        f"🎯 <b>Difficulty:</b> {game.cfg['label']}\n"
        f"📐 <b>Grid:</b> {game.rows}×{game.cols} = {game.total_cells()} cells\n"
        f"👥 <b>Players ({len(game.players)}):</b>\n{lines}\n\n"
        f"💰 <b>Pool:</b> {game.gross_pool if game.is_paid else 'Free'}\n\n"
        "🎯 <b>Goal:</b> Capture the most cells!\n"
        f"⚠️ <b>Rules:</b> {MAX_SKIPS_PER_PLAYER} skips = kicked. Stuck = eliminated.\n\n"
        "🔥 Let's go!",
        parse_mode=ParseMode.HTML,
    )

    await asyncio.sleep(2)
    await _start_turn(game)


async def _start_turn(game: PixelGame):
    if game.state != STATE_PLAYING:
        return

    if game.check_game_over():
        return await _finish_game(game)

    current = game.current_player()
    if not current:
        return await _finish_game(game)

    valid = game.get_valid_moves(current["user_id"])
    if not valid:
        # ✅ Player stuck → eliminate
        eliminated = game.eliminate_player(current["user_id"], reason="🚫 No valid moves (blocked)")
        name = eliminated["name"] if eliminated else str(current["user_id"])
        color = eliminated["color"] if eliminated else "⬜"

        await _send_tracked(
            game,
            f"🚫 {color} <b>{_esc(name)}</b> is <b>STUCK</b> — no valid moves!\n"
            f"❌ <b>Eliminated!</b>",
            parse_mode=ParseMode.HTML,
        )

        # Check if only 1 left
        if len(game.players) <= 1:
            return await _finish_game(game)

        # Reset turn_index safely and continue
        if game.players:
            game.turn_index = game.turn_index % len(game.players)
        await persist_game(game)
        await asyncio.sleep(1)
        return await _start_turn(game)

    board_text = _render_board(game)
    kb = _valid_moves_kb(game)

    if game.board_message_id:
        edited = await _safe_edit(
            game.chat_id, game.board_message_id,
            board_text, parse_mode=ParseMode.HTML, reply_markup=kb,
        )
        if not edited:
            sent = await _send_tracked(game, board_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            if sent and getattr(sent, "id", None):
                game.board_message_id = sent.id
    else:
        sent = await _send_tracked(game, board_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        if sent and getattr(sent, "id", None):
            game.board_message_id = sent.id

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()
    game.turn_task = asyncio.create_task(_turn_timer(game, current["user_id"]))


async def _turn_timer(game: PixelGame, expected_uid: int):
    try:
        await asyncio.sleep(TURN_SECONDS)
        if game.state != STATE_PLAYING:
            return
        current = game.current_player()
        if not current or current["user_id"] != expected_uid:
            return

        # ✅ Increment skip counter
        skips = game.increment_skip(expected_uid)

        # Check kick threshold
        if skips >= MAX_SKIPS_PER_PLAYER:
            eliminated = game.eliminate_player(expected_uid,
                                                reason=f"⏭️ {MAX_SKIPS_PER_PLAYER} skips")
            name = eliminated["name"] if eliminated else str(expected_uid)
            color = eliminated["color"] if eliminated else "⬜"

            await _send_tracked(
                game,
                f"👢 {color} <b>{_esc(name)}</b> was <b>KICKED</b> for "
                f"{MAX_SKIPS_PER_PLAYER} skips!\n"
                f"❌ Eliminated.",
                parse_mode=ParseMode.HTML,
            )

            if len(game.players) <= 1:
                await persist_game(game)
                return await _finish_game(game)

            if game.players:
                game.turn_index = game.turn_index % len(game.players)
            await persist_game(game)
            await asyncio.sleep(1)
            return await _start_turn(game)

        # Otherwise: auto-pick random valid move
        valid = game.get_valid_moves(expected_uid)
        if valid:
            r, c = random.choice(valid)
            ok, _ = game.claim_cell(expected_uid, r, c)
            if ok:
                await _send_tracked(
                    game,
                    f"⏰ {current['color']} {current['mention']} timed out "
                    f"(<b>skip {skips}/{MAX_SKIPS_PER_PLAYER}</b>) — "
                    f"auto-picked <b>({r}, {c})</b>.",
                    parse_mode=ParseMode.HTML,
                )
                game.next_turn()
                await persist_game(game)
                return await _start_turn(game)

        game.next_turn()
        await _start_turn(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Pixel turn timer] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MOVE CALLBACK
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^pixel_move:"))
async def pixel_move_cb(_, q: CallbackQuery):
    try:
        _, cid_str, r_str, c_str = q.data.split(":", 3)
        chat_id = int(cid_str)
        r = int(r_str)
        c = int(c_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_PLAYING:
        return await q.answer("Game not active.", show_alert=True)

    current = game.current_player()
    if not current or current["user_id"] != q.from_user.id:
        return await q.answer("It's not your turn!", show_alert=True)

    ok, reason = game.claim_cell(q.from_user.id, r, c)
    if not ok:
        msg = {
            "cell_taken": "Cell already taken!",
            "not_adjacent": "Must be adjacent to your own cells!",
            "not_player": "You're not a player.",
            "out_of_bounds": "Invalid cell.",
        }.get(reason, reason)
        return await q.answer(msg, show_alert=True)

    await q.answer(f"✅ ({r}, {c}) claimed!")

    if game.turn_task and not game.turn_task.done():
        game.turn_task.cancel()

    if game.check_game_over():
        await persist_game(game)
        return await _finish_game(game)

    game.next_turn()
    await persist_game(game)
    await asyncio.sleep(0.3)
    await _start_turn(game)


@app.on_callback_query(filters.regex(r"^pixel_noop:"))
async def pixel_noop_cb(_, q: CallbackQuery):
    await q.answer("More cells available — first 16 shown.", show_alert=False)


# ══════════════════════════════════════════════════════════════════════════════
#  FINISH
# ══════════════════════════════════════════════════════════════════════════════
async def _finish_game(game: PixelGame):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.payout_done:
        return

    game.state = STATE_FINISHED
    game.finished_at = datetime.now(timezone.utc)
    game.cancel_timers()

    winner_id = game.determine_winner()
    if not winner_id:
        return await _cancel_and_refund(game, reason="No winner determined")

    game.winner_id = winner_id
    game.winner_ids = [winner_id]

    grid_txt = _render_grid(game)
    sorted_players = sorted(game.players, key=lambda p: -p["cell_count"])

    ranking_lines = []
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    for i, p in enumerate(sorted_players):
        rank = medals.get(i, f"{i+1}.")
        ranking_lines.append(f"{rank} {p['color']} {p['mention']} — <code>{p['cell_count']}</code> cells")

    # Eliminated section
    elim_lines = []
    for p in game.eliminated_players:
        reason = p.get("elimination_reason", "eliminated")
        elim_lines.append(f"• {p['color']} {_esc(p['name'])} — <i>{_esc(reason)}</i>")
    elim_txt = "\n\n💀 <b>Eliminated:</b>\n" + "\n".join(elim_lines) if elim_lines else ""

    # Final scoreboard (KEEP)
    scoreboard_msg = await _safe_send(
        game.chat_id,
        "🎨 <b>PIXEL BATTLE — FINAL BOARD</b>\n\n"
        f"{grid_txt}\n\n"
        "📊 <b>Final Scores:</b>\n" + "\n".join(ranking_lines) +
        elim_txt,
        parse_mode=ParseMode.HTML,
    )
    scoreboard_id = getattr(scoreboard_msg, "id", None)

    # Payout
    share = 0
    if game.is_paid and game.net_prize > 0:
        share = await _payout_paid_game(game)
    else:
        await _award_xp_only(game)

    # Winner card (KEEP)
    winner_msg_id = await _send_winner_card(game, share)

    # Stats
    for p in game.players + game.eliminated_players:
        won = (p["user_id"] == winner_id)
        try:
            await record_result(
                p["user_id"], p["name"], won=won, cells=p["cell_count"],
                wagered=(game.entry_fee if game.is_paid else 0),
                gross_won=(game.net_prize if (won and game.is_paid) else 0),
                tax_paid=(game.tax_amount if won else 0),
            )
        except Exception:
            pass

    game.payout_done = True
    await persist_game(game)

    keep_ids = [x for x in (scoreboard_id, winner_msg_id) if x]
    try:
        await _cleanup_game_messages(game, keep_ids=keep_ids)
    except Exception:
        pass

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


async def _payout_paid_game(game: PixelGame) -> int:
    pool = game.net_prize
    if pool <= 0 or not game.winner_id:
        return 0

    await _ensure_user_record(game.winner_id)
    await _payout_winner(game.winner_id, pool)
    await _credit_elara(game.tax_amount)
    return pool


async def _award_xp_only(game: PixelGame):
    for p in game.players + game.eliminated_players:
        won = (p["user_id"] == game.winner_id)
        try:
            await add_xp(p["user_id"], WINNER_XP if won else LOSER_XP)
        except Exception:
            pass


async def _send_winner_card(game: PixelGame, share: int) -> int | None:
    if not game.winner_id:
        return None

    winner = game.get_player(game.winner_id)
    winner_name = winner["name"] if winner else str(game.winner_id)
    winner_color = winner["color"] if winner else "🎨"
    winner_cells = winner["cell_count"] if winner else 0

    total_cells = game.total_cells()
    percent = (winner_cells / total_cells) * 100 if total_cells else 0

    others = sorted([p for p in game.players if p["user_id"] != game.winner_id],
                    key=lambda p: -p["cell_count"])
    runner_up_line = ""
    if others:
        ru = others[0]
        runner_up_line = f"🥈 <b>Runner-up:</b> {ru['color']} {_esc(ru['name'])} — <code>{ru['cell_count']}</code> cells\n"

    players_line = ", ".join(f"{p['color']} {_esc(p['name'])}" for p in game.players)

    card_text = (
        "👑 <b>PIXEL BATTLE — WINNER!</b> 👑\n\n"
        f"🎯 <b>Mode:</b> {game.cfg['label']}\n"
        f"🏆 <b>Winner:</b> {winner_color} {_esc(winner_name)}\n"
        f"🎯 <b>Cells:</b> <code>{winner_cells}/{total_cells}</code> ({percent:.1f}%)\n"
        f"{runner_up_line}"
        f"💰 <b>Prize:</b> <code>{game.net_prize if game.is_paid else 0}</code> coins\n"
        f"⚡ <b>XP gained:</b> <code>+{WINNER_XP}</code>\n\n"
        f"👥 <b>Players:</b> {players_line}\n\n"
        + (f"👉 Play again: <code>/pixel {game.entry_fee} {game.mode}</code>"
           if game.is_paid else f"👉 Play again: <code>/pixel free {game.mode}</code>")
    )

    photo_path = await _fetch_user_photo(game.winner_id)
    msg = None

    if photo_path and os.path.exists(photo_path):
        try:
            msg = await app.send_photo(
                game.chat_id,
                photo=photo_path,
                caption=card_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"[Pixel winner photo send] {type(e).__name__}: {e}", flush=True)
            msg = await _safe_send(game.chat_id, card_text, parse_mode=ParseMode.HTML)
        finally:
            try:
                os.remove(photo_path)
            except Exception:
                pass
    else:
        msg = await _safe_send(game.chat_id, card_text, parse_mode=ParseMode.HTML)

    return getattr(msg, "id", None)


async def _cancel_and_refund(game: PixelGame, reason: str):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.refund_done:
        return

    game.state = STATE_CANCELLED
    game.cancel_timers()

    refunded = 0
    if game.is_paid and game.entry_fee > 0:
        for p in game.players + game.eliminated_players:
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

    await _send_tracked(
        game,
        f"🚫 <b>PIXEL BATTLE CANCELLED</b>\n\n"
        f"<i>{_esc(reason)}</i>\n"
        + (f"💰 Refunded: <code>{refunded}</code> player(s)" if game.is_paid else ""),
        parse_mode=ParseMode.HTML,
    )

    try:
        await _cleanup_game_messages(game, keep_ids=[])
    except Exception:
        pass

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  /pixelcancel /pixelinfo /pixelstats /pixeltop
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["pixelcancel"], prefixes=PREFIXES) & filters.group)
async def pixel_cancel(_, message: Message):
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


@app.on_message(filters.command(["pixelinfo"], prefixes=PREFIXES) & filters.group)
async def pixel_info(_, message: Message):
    game = get_game(message.chat.id)
    if not game:
        return await _safe_reply(message, "❌ No active game.", parse_mode=ParseMode.HTML)

    if game.state == STATE_LOBBY:
        await _safe_reply(message, _render_lobby(game, LOBBY_SECONDS), parse_mode=ParseMode.HTML)
    else:
        await _safe_reply(message, _render_board(game), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["pixelstats"], prefixes=PREFIXES))
async def pixel_stats_cmd(_, message: Message):
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
            f"📊 <b>{_esc(name)}'s Pixel Battle stats</b>\n\n❌ No games yet.",
            parse_mode=ParseMode.HTML,
        )

    played = int(doc.get("games_played", 0))
    wins = int(doc.get("wins", 0))
    wr = (wins / played * 100) if played else 0.0

    await _safe_reply(
        message,
        f"📊 <b>{_esc(name)}'s Pixel Battle stats</b>\n\n"
        f"🎮 Games: <code>{played}</code>\n"
        f"🏆 Wins: <code>{wins}</code> ({wr:.1f}%)\n"
        f"❌ Losses: <code>{int(doc.get('losses', 0))}</code>\n"
        f"🎯 Total cells: <code>{int(doc.get('total_cells', 0))}</code>\n"
        f"🔥 Best game: <code>{int(doc.get('best_cells', 0))}</code> cells\n"
        f"💰 Wagered: <code>{int(doc.get('coins_wagered', 0))}</code>\n"
        f"📊 Net: <code>{int(doc.get('net_coins', 0)):+d}</code>\n"
        f"🔥 Streak: <code>{int(doc.get('win_streak', 0))}</code> "
        f"(best <code>{int(doc.get('best_streak', 0))}</code>)",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command(["pixeltop", "pixelleaderboard"], prefixes=PREFIXES))
async def pixel_top(_, message: Message):
    try:
        rows = await top_players(10)
    except Exception:
        rows = []

    if not rows:
        return await _safe_reply(
            message, "🏆 <b>Pixel Battle Leaderboard</b>\n\n❌ No games yet.",
            parse_mode=ParseMode.HTML,
        )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>Pixel Battle Leaderboard</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        nm = row.get("name") or str(row["_id"])
        wins = int(row.get("wins", 0))
        net = int(row.get("net_coins", 0))
        best = int(row.get("best_cells", 0))
        lines.append(
            f"{rank} <b>{_esc(nm)}</b> — 🏆 <code>{wins}</code> • "
            f"🎯 <code>{best}</code> • 📊 <code>{net:+d}</code>"
        )
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)
