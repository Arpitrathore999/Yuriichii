# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/shadow_syndicate.py — 🎭 Shadow Syndicate Handlers
#  Commands, callbacks, cinematic scenes
#  ✅ NEW: /shadowhelp with full detailed guide
#  ✅ FIXED: Deep link return instead of StopPropagation
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import os
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
from core.database import add_coins, get_user
from core.shadow_dialogues import (
    get_cross_exchange,
    get_final_interrogation,
    get_interrogation,
    get_mission_start,
    get_monarch_followup,
    get_monarch_line,
    get_reveal,
    get_strategist_line,
)
from core.shadow_engine import (
    ACTIVE_GAMES,
    GUESS_SECONDS,
    LOBBY_SECONDS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    REWARD_MONARCH_ALWAYS,
    REWARD_PHANTOM_CORRECT,
    REWARD_PHANTOM_WRONG,
    REWARD_SENTINEL_ALWAYS,
    REWARD_STRATEGIST_CORRECT,
    REWARD_STRATEGIST_WRONG,
    ROLE_EMOJI,
    ROLE_LABEL,
    ROLE_MONARCH,
    ROLE_PHANTOM,
    ROLE_SENTINEL,
    ROLE_STRATEGIST,
    STATE_ASSIGNED,
    STATE_CANCELLED,
    STATE_FINISHED,
    STATE_GUESSING,
    STATE_INTRO,
    STATE_LOBBY,
    STATE_REVEALING,
    USER_ACTIVE,
    ShadowGame,
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
        print(f"[Shadow send] {type(e).__name__}: {e}", flush=True)
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
        print(f"[Shadow DM] {type(e).__name__}: {e}", flush=True)
        return None


async def _send_tracked(game: ShadowGame, text: str, **kw):
    msg = await _safe_send(game.chat_id, text, **kw)
    if msg and getattr(msg, "id", None):
        game.game_messages.append(msg.id)
    return msg


async def _cleanup_game_messages(game: ShadowGame, keep_ids: list[int] | None = None):
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
    return deleted


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
        print(f"[Shadow ensure_user] {type(e).__name__}: {e}", flush=True)


async def _credit_user(uid: int, amount: int) -> bool:
    if amount <= 0:
        return False
    try:
        ok = await add_coins(int(uid), int(amount))
        if ok:
            return True
    except Exception as e:
        print(f"[Shadow credit] {type(e).__name__}: {e}", flush=True)

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
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  RENDERERS
# ══════════════════════════════════════════════════════════════════════════════
def _render_help() -> str:
    return (
        "🎭 <b>ꜱʜᴀᴅᴏᴡ ꜱʏɴᴅɪᴄᴀᴛᴇ</b> 🎭\n"
        "<i>ᴛʜᴇ ᴍᴏᴅᴇʀɴ ʀᴀᴊᴀ-ᴍᴀɴᴛʀɪ-ᴄʜᴏʀ-ꜱɪᴘᴀʜɪ</i>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📖 <b>ᴛʜᴇ ꜱᴛᴏʀʏ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🌑 <b>OPERATION NIGHTFALL</b>\n\n"
        "The city has gone silent.\n"
        "A classified artifact has vanished from the <b>Monarch's vault</b>.\n"
        "Four suspects. One thief. Zero mercy.\n"
        "Only the <b>Strategist</b> can expose the truth.\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎭 <b>ᴛʜᴇ 4 ꜱᴇᴄʀᴇᴛ ʀᴏʟᴇꜱ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "👑 <b>ᴛʜᴇ ᴍᴏɴᴀʀᴄʜ</b> (Raja)\n"
        "    • ʀᴜʟᴇʀ ᴏꜰ ᴛʜᴇ ꜱʏɴᴅɪᴄᴀᴛᴇ\n"
        "    • ᴀʟᴡᴀʏꜱ ᴇᴀʀɴꜱ <code>+1000</code> ᴄᴏɪɴꜱ\n"
        "    • ᴘᴜʙʟɪᴄʟʏ ʀᴇᴠᴇᴀʟᴇᴅ\n\n"

        "🧠 <b>ᴛʜᴇ ꜱᴛʀᴀᴛᴇɢɪꜱᴛ</b> (Mantri)\n"
        "    • ᴛʜᴇ ᴍɪɴᴅ ᴏꜰ ᴛʜᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ\n"
        "    • ᴍᴜꜱᴛ ᴀᴄᴄᴜꜱᴇ ᴛʜᴇ ᴘʜᴀɴᴛᴏᴍ\n"
        "    • ᴄᴏʀʀᴇᴄᴛ → <code>+800</code> ᴄᴏɪɴꜱ\n"
        "    • ᴡʀᴏɴɢ → <code>0</code> ᴄᴏɪɴꜱ\n"
        "    • ᴘᴜʙʟɪᴄʟʏ ʀᴇᴠᴇᴀʟᴇᴅ\n\n"

        "🛡️ <b>ᴛʜᴇ ꜱᴇɴᴛɪɴᴇʟ</b> (Sipahi)\n"
        "    • ᴛʜᴇ ʟᴏʏᴀʟ ɢᴜᴀʀᴅ\n"
        "    • ᴀʟᴡᴀʏꜱ ᴇᴀʀɴꜱ <code>+500</code> ᴄᴏɪɴꜱ\n"
        "    • ɪᴅᴇɴᴛɪᴛʏ <b>ʜɪᴅᴅᴇɴ</b>\n\n"

        "🃏 <b>ᴛʜᴇ ᴘʜᴀɴᴛᴏᴍ</b> (Chor)\n"
        "    • ᴛʜᴇ ᴛʜɪᴇꜰ ᴏꜰ ᴛʜᴇ ᴀʀᴛɪꜰᴀᴄᴛ\n"
        "    • ᴄᴀᴜɢʜᴛ → <code>0</code> ᴄᴏɪɴꜱ\n"
        "    • ᴇꜱᴄᴀᴘᴇꜱ → <code>+800</code> ᴄᴏɪɴꜱ\n"
        "    • ɪᴅᴇɴᴛɪᴛʏ <b>ʜɪᴅᴅᴇɴ</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 <b>ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "<b>1️⃣ ʟᴏʙʙʏ ᴘʜᴀꜱᴇ</b>\n"
        "• ᴀ ᴘʟᴀʏᴇʀ ꜱᴛᴀʀᴛꜱ ᴡɪᴛʜ <code>/syndicate</code>\n"
        "• 3 ᴍᴏʀᴇ ᴘʟᴀʏᴇʀꜱ ᴊᴏɪɴ ᴡɪᴛʜ <code>/joinsyndicate</code>\n"
        "• ᴛᴏᴛᴀʟ <b>4 ᴘʟᴀʏᴇʀꜱ</b> ɴᴇᴇᴅᴇᴅ\n"
        f"• {LOBBY_SECONDS}ꜱ ʟᴏʙʙʏ ᴛɪᴍᴇ\n\n"

        "<b>2️⃣ ʀᴏʟᴇ ᴀꜱꜱɪɢɴᴍᴇɴᴛ</b>\n"
        "• ʀᴀɴᴅᴏᴍʟʏ ᴀꜱꜱɪɢɴᴇᴅ ᴛᴏ ᴀʟʟ 4 ᴘʟᴀʏᴇʀꜱ\n"
        "• ʀᴏʟᴇꜱ ꜱᴇɴᴛ ᴘʀɪᴠᴀᴛᴇʟʏ ᴠɪᴀ DM\n"
        "• ⚠️ ᴍᴜꜱᴛ /ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ꜰɪʀꜱᴛ\n\n"

        "<b>3️⃣ ᴘᴜʙʟɪᴄ ʀᴇᴠᴇᴀʟ</b>\n"
        "• 👑 ᴍᴏɴᴀʀᴄʜ + 🧠 ꜱᴛʀᴀᴛᴇɢɪꜱᴛ ʀᴇᴠᴇᴀʟᴇᴅ\n"
        "• 🛡️ ꜱᴇɴᴛɪɴᴇʟ + 🃏 ᴘʜᴀɴᴛᴏᴍ ʜɪᴅᴅᴇɴ\n\n"

        "<b>4️⃣ ᴄɪɴᴇᴍᴀᴛɪᴄ ꜱᴄᴇɴᴇꜱ</b>\n"
        "• ᴍᴏɴᴀʀᴄʜ ꜱᴘᴇᴀᴋꜱ\n"
        "• ꜱᴛʀᴀᴛᴇɢɪꜱᴛ ʀᴇꜱᴘᴏɴᴅꜱ\n"
        "• ꜱᴇɴᴛɪɴᴇʟ ᴠꜱ ᴘʜᴀɴᴛᴏᴍ ɪɴᴛᴇʀʀᴏɢᴀᴛɪᴏɴ\n\n"

        f"<b>5️⃣ ᴀᴄᴄᴜꜱᴀᴛɪᴏɴ ᴘʜᴀꜱᴇ</b> ⏱ {GUESS_SECONDS}ꜱ\n"
        "• 2 ꜱᴜꜱᴘᴇᴄᴛꜱ ꜱʜᴏᴡɴ ᴛᴏ ꜱᴛʀᴀᴛᴇɢɪꜱᴛ\n"
        "• ʙᴜᴛᴛᴏɴꜱ:\n"
        "    🃏 ᴀᴄᴄᴜꜱᴇ ᴛʜᴇ ᴘʜᴀɴᴛᴏᴍ\n"
        "    🛡️ ᴀᴄᴄᴜꜱᴇ ᴛʜᴇ ꜱᴇɴᴛɪɴᴇʟ\n"
        "• ᴏɴʟʏ ꜱᴛʀᴀᴛᴇɢɪꜱᴛ ᴄᴀɴ ᴄʟɪᴄᴋ\n"
        "• ᴛɪᴍᴇᴏᴜᴛ = ᴡʀᴏɴɢ ɢᴜᴇꜱꜱ\n\n"

        "<b>6️⃣ ᴅʀᴀᴍᴀᴛɪᴄ ʀᴇᴠᴇᴀʟ</b>\n"
        "• ᴀʟʟ 4 ʀᴏʟᴇꜱ ʀᴇᴠᴇᴀʟᴇᴅ\n"
        "• ᴡɪɴɴᴇʀꜱ ᴘᴀɪᴅ ɪɴꜱᴛᴀɴᴛʟʏ\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>ᴇxᴀᴄᴛ ʀᴇᴡᴀʀᴅ ᴍᴀᴛʀɪx</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "<pre>"
        "ROLE         │ CORRECT │ WRONG  \n"
        "─────────────┼─────────┼────────\n"
        "👑 MONARCH   │ +1000   │ +1000  \n"
        "🧠 STRATEGIST│ +800    │ 0      \n"
        "🛡️ SENTINEL  │ +500    │ +500   \n"
        "🃏 PHANTOM   │ 0       │ +800   \n"
        "</pre>\n"

        "💡 ᴛʜᴇ ᴘʜᴀɴᴛᴏᴍ'ꜱ 800 = ꜱᴛʀᴀᴛᴇɢɪꜱᴛ'ꜱ ꜰᴏʀꜰᴇɪᴛᴇᴅ ʀᴇᴡᴀʀᴅ\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>ᴄᴏᴍᴍᴀɴᴅꜱ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🎮 <b>ɢᴀᴍᴇ</b>\n"
        "• <code>/syndicate</code> — ᴄʀᴇᴀᴛᴇ ɴᴇᴡ ʟᴏʙʙʏ\n"
        "• <code>/joinsyndicate</code> — ᴊᴏɪɴ ᴛʜᴇ ʟᴏʙʙʏ\n"
        "• <code>/leavesyndicate</code> — ʟᴇᴀᴠᴇ ʙᴇꜰᴏʀᴇ ꜱᴛᴀʀᴛ\n"
        "• <code>/syndicateinfo</code> — ᴛʜɪꜱ ᴍᴇꜱꜱᴀɢᴇ\n\n"

        "📊 <b>ꜱᴛᴀᴛꜱ</b>\n"
        "• <code>/syndicatestats</code> — ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ\n"
        "• <code>/syndicatetop</code> — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n\n"

        "📖 <b>ʜᴇʟᴘ</b>\n"
        "• <code>/shadowhelp</code> — ᴛʜɪꜱ ᴍᴇꜱꜱᴀɢᴇ\n"
        "• <code>/syndicatehelp</code> — ᴀʟɪᴀꜱ\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ <b>ꜱᴇᴛᴛɪɴɢꜱ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👥 ᴘʟᴀʏᴇʀꜱ: <code>4</code> ᴇxᴀᴄᴛʟʏ\n"
        f"⏳ ʟᴏʙʙʏ: <code>{LOBBY_SECONDS}s</code>\n"
        f"⏱ ᴀᴄᴄᴜꜱᴀᴛɪᴏɴ ᴛɪᴍᴇʀ: <code>{GUESS_SECONDS}s</code>\n"
        "💰 ᴇɴᴛʀʏ ꜰᴇᴇ: <b>FREE</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>ꜱᴇᴄᴜʀɪᴛʏ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• 🔐 ʀᴏʟᴇꜱ ꜱᴇɴᴛ ᴠɪᴀ <b>ᴘʀɪᴠᴀᴛᴇ DM</b> ᴏɴʟʏ\n"
        "• 🚫 ᴏɴʟʏ ꜱᴛʀᴀᴛᴇɢɪꜱᴛ ᴄᴀɴ ᴀᴄᴄᴜꜱᴇ\n"
        "• 🔒 ꜱᴇɴᴛɪɴᴇʟ + ᴘʜᴀɴᴛᴏᴍ ʜɪᴅᴅᴇɴ ᴜɴᴛɪʟ ʀᴇᴠᴇᴀʟ\n"
        "• ⚡ ᴀᴛᴏᴍɪᴄ ᴘᴀʏᴏᴜᴛꜱ (ɴᴏ ᴅᴜᴘʟɪᴄᴀᴛᴇꜱ)\n"
        "• 🧹 ᴀʟʟ ᴍᴇꜱꜱᴀɢᴇꜱ ᴄʟᴇᴀɴᴇᴅ ᴀꜰᴛᴇʀ ɢᴀᴍᴇ\n\n"

        "💡 <i>ᴛɪᴘ: ᴏᴘᴇɴ ᴛʜᴇ ʙᴏᴛ ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴀɴᴅ ᴘʀᴇꜱꜱ /start ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ʏᴏᴜʀ ꜱᴇᴄʀᴇᴛ ʀᴏʟᴇ!</i>"
    )


def _render_lobby(game: ShadowGame) -> str:
    lines = []
    for i, p in enumerate(game.players, 1):
        lines.append(f"{i}. {p['mention']}")
    lines_txt = "\n".join(lines) if lines else "<i>No players yet</i>"

    return (
        "🎭 <b>SHADOW SYNDICATE — LOBBY</b> 🎭\n\n"
        f"📍 <b>Group:</b> {_esc(game.chat_name or 'this group')}\n"
        f"👥 <b>Players:</b> <code>{len(game.players)}/{MAX_PLAYERS}</code>\n"
        f"⏳ <b>Join window:</b> <code>{LOBBY_SECONDS}s</code>\n\n"
        f"<b>Players Joined:</b>\n{lines_txt}\n\n"
        "👉 <b>Tap JOIN below</b> or use <code>/joinsyndicate</code>\n"
        "🔒 4 players needed to begin."
    )


def _lobby_kb(game: ShadowGame) -> InlineKeyboardMarkup:
    dm_link = f"https://t.me/{BOT_USERNAME}?start=shadow_join_{game.chat_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎭 JOIN SYNDICATE", url=dm_link)],
        [InlineKeyboardButton("📖 How to Play",
                              url=f"https://t.me/{BOT_USERNAME}?start=shadow_help")],
    ])


def _render_guess_prompt(game: ShadowGame, suspect_1: int, suspect_2: int) -> str:
    p1 = game.get_player(suspect_1)
    p2 = game.get_player(suspect_2)
    n1 = p1["mention"] if p1 else str(suspect_1)
    n2 = p2["mention"] if p2 else str(suspect_2)

    strategist = game.get_player(game.strategist_id)
    s_name = strategist["mention"] if strategist else "Strategist"

    return (
        "🔍 <b>THE ACCUSATION PHASE</b>\n\n"
        f"🧠 {s_name}, the Syndicate awaits your judgment.\n\n"
        "<b>Two suspects stand before the Monarch:</b>\n"
        f"• {n1}\n"
        f"• {n2}\n\n"
        f"⏱ You have <code>{GUESS_SECONDS}s</code>.\n\n"
        "👇 Choose wisely. One name will change everything."
    )


def _guess_kb(game: ShadowGame) -> InlineKeyboardMarkup:
    s1, s2 = game.suspects[0], game.suspects[1]
    p1 = game.get_player(s1)
    p2 = game.get_player(s2)
    n1 = p1["name"] if p1 else str(s1)
    n2 = p2["name"] if p2 else str(s2)

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🃏 Accuse {n1}",
            callback_data=f"shadow_guess:{game.chat_id}:{s1}",
        )],
        [InlineKeyboardButton(
            f"🛡️ Accuse {n2}",
            callback_data=f"shadow_guess:{game.chat_id}:{s2}",
        )],
    ])


def _render_reveal(game: ShadowGame) -> str:
    correct = game.guess_result == "correct"

    lines = []
    for p in game.players:
        role = p["role"]
        emoji = ROLE_EMOJI.get(role, "❔")
        label = ROLE_LABEL.get(role, "?")
        reward = game.rewards.get(p["user_id"], 0)
        lines.append(
            f"{emoji} {p['mention']} — <b>{label}</b>\n"
            f"    💰 <code>+{reward}</code> coins"
        )

    header = get_reveal(correct)

    return (
        f"{header}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎭 <b>FULL REVEAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(lines) +
        "\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Strategist's guess: {'✅ Correct' if correct else '❌ Wrong'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  DEEP LINK HANDLER
#  🚨 FIXED: return instead of StopPropagation to not block normal /start
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("start", prefixes=PREFIXES) & filters.private, group=-15)
async def shadow_deeplink(_, message: Message):
    if not message.command or len(message.command) < 2:
        return  # 🚨 FIX: StopPropagation ko return kiya

    payload = message.command[1].strip()

    if payload == "shadow_help":
        await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)
        raise StopPropagation

    if not payload.startswith("shadow_join_"):
        return  # 🚨 FIX: StopPropagation ko return kiya

    try:
        chat_id = int(payload[len("shadow_join_"):])
    except ValueError:
        await _safe_reply(message, "❌ Invalid join link.", parse_mode=ParseMode.HTML)
        raise StopPropagation

    game = get_game(chat_id)
    user = message.from_user

    if not game:
        await _safe_reply(
            message, "❌ <b>No active Shadow Syndicate lobby.</b>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    if game.state != STATE_LOBBY:
        await _safe_reply(
            message, "❌ <b>The lobby has already closed.</b>",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    if game.has_player(user.id):
        await _safe_reply(
            message,
            f"⚠️ <b>You're already in the game in</b> <b>{_esc(game.chat_name)}</b>!",
            parse_mode=ParseMode.HTML,
        )
        raise StopPropagation

    ok, reason = await _process_join(game, user.id, _name(user), _mention(user.id, _name(user)))
    if not ok:
        await _safe_reply(message, f"❌ {_esc(reason)}", parse_mode=ParseMode.HTML)
        raise StopPropagation

    await _safe_reply(
        message,
        f"✅ <b>You joined the Syndicate!</b>\n\n"
        f"📍 Group: <b>{_esc(game.chat_name)}</b>\n"
        f"👥 Players: <code>{len(game.players)}/{MAX_PLAYERS}</code>\n\n"
        "🎭 Your secret role will arrive here once the game starts.\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.HTML,
    )

    await _send_tracked(
        game,
        f"🎭 {_mention(user.id, _name(user))} joined the Syndicate!",
        parse_mode=ParseMode.HTML,
    )

    if game.lobby_message_id:
        await _safe_edit(
            game.chat_id, game.lobby_message_id,
            _render_lobby(game),
            parse_mode=ParseMode.HTML, reply_markup=_lobby_kb(game),
        )

    if game.is_full():
        if game.lobby_task and not game.lobby_task.done():
            game.lobby_task.cancel()
        await _begin_match(game)

    raise StopPropagation


# ══════════════════════════════════════════════════════════════════════════════
#  /syndicate — CREATE
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["syndicate"], prefixes=PREFIXES) & filters.group)
async def shadow_create(_, message: Message):
    if not _is_group(message) or not message.from_user:
        return

    existing = get_game(message.chat.id)
    if existing and not existing.is_terminal():
        return await _safe_reply(
            message,
            "⚠️ <b>A Shadow Syndicate game is already running here.</b>",
            parse_mode=ParseMode.HTML,
        )

    user_game = get_user_game(message.from_user.id)
    if user_game and user_game.chat_id != message.chat.id:
        return await _safe_reply(
            message,
            "⚠️ <b>You are in another Shadow Syndicate game.</b>",
            parse_mode=ParseMode.HTML,
        )

    await _ensure_user_record(message.from_user.id, _name(message.from_user))

    game = create_game(
        chat_id=message.chat.id,
        host_id=message.from_user.id,
        host_name=_name(message.from_user),
        host_mention=_mention(message.from_user.id, _name(message.from_user)),
    )
    game.chat_name = getattr(message.chat, "title", "") or f"Group {message.chat.id}"
    game.state = STATE_LOBBY

    game.add_player(message.from_user.id, _name(message.from_user),
                    _mention(message.from_user.id, _name(message.from_user)))

    try:
        await ensure_stats(message.from_user.id, _name(message.from_user))
    except Exception:
        pass

    sent = await _safe_send(
        message.chat.id,
        _render_lobby(game),
        parse_mode=ParseMode.HTML,
        reply_markup=_lobby_kb(game),
    )
    if sent and getattr(sent, "id", None):
        game.lobby_message_id = sent.id
        game.game_messages.append(sent.id)

    await persist_game(game)
    game.lobby_task = asyncio.create_task(_lobby_timer(game))


# ══════════════════════════════════════════════════════════════════════════════
#  JOIN / LEAVE
# ══════════════════════════════════════════════════════════════════════════════
async def _process_join(game: ShadowGame, uid: int, name: str, mention: str) -> tuple[bool, str]:
    if game.state != STATE_LOBBY:
        return False, "Lobby is closed."
    if game.has_player(uid):
        return False, "Already in game."
    if game.is_full():
        return False, "Lobby is full."

    other = get_user_game(uid)
    if other and other.chat_id != game.chat_id:
        return False, "You're in another game."

    await _ensure_user_record(uid, name)

    if not game.add_player(uid, name, mention):
        return False, "Could not join."

    USER_ACTIVE[int(uid)] = game.chat_id
    try:
        await ensure_stats(uid, name)
    except Exception:
        pass
    await persist_game(game)
    return True, "ok"


@app.on_message(filters.command(["joinsyndicate"], prefixes=PREFIXES) & filters.group)
async def shadow_join(_, message: Message):
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
            _render_lobby(game),
            parse_mode=ParseMode.HTML, reply_markup=_lobby_kb(game),
        )

    await _send_tracked(
        game,
        f"🎭 {_mention(message.from_user.id, _name(message.from_user))} joined the Syndicate!",
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


@app.on_message(filters.command(["leavesyndicate"], prefixes=PREFIXES) & filters.group)
async def shadow_leave(_, message: Message):
    if not _is_group(message) or not message.from_user:
        return
    game = get_game(message.chat.id)
    if not game or game.state != STATE_LOBBY:
        return
    if not game.has_player(message.from_user.id):
        return await _safe_reply(message, "⚠️ You're not in the lobby.", parse_mode=ParseMode.HTML)

    game.remove_player(message.from_user.id)
    USER_ACTIVE.pop(int(message.from_user.id), None)

    if game.lobby_message_id:
        await _safe_edit(
            game.chat_id, game.lobby_message_id,
            _render_lobby(game),
            parse_mode=ParseMode.HTML, reply_markup=_lobby_kb(game),
        )
    await _safe_reply(message, "👋 You left the Syndicate lobby.", parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  LOBBY TIMER
# ══════════════════════════════════════════════════════════════════════════════
async def _lobby_timer(game: ShadowGame):
    try:
        await asyncio.sleep(LOBBY_SECONDS)
        if game.state != STATE_LOBBY:
            return
        if not game.can_start():
            await _cancel_game(game, reason=f"Not enough players (need {MAX_PLAYERS})")
            return
        await _begin_match(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Shadow lobby] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MATCH FLOW — CINEMATIC
# ══════════════════════════════════════════════════════════════════════════════
async def _begin_match(game: ShadowGame):
    if game.state != STATE_LOBBY:
        return
    if not game.can_start():
        return await _cancel_game(game, reason="Not enough players")

    game.assign_roles()
    game.state = STATE_INTRO
    await persist_game(game)

    # ── Scene 1: Mission Start ──────────────────────────────────────────
    await _send_tracked(game, get_mission_start(), parse_mode=ParseMode.HTML)
    await asyncio.sleep(2)

    # ── Send roles privately ────────────────────────────────────────────
    dm_failed = []
    for p in game.players:
        role = p["role"]
        ok = await _send_role_dm(p["user_id"], role, p["name"])
        if not ok:
            dm_failed.append(p["name"])

    if dm_failed:
        await _send_tracked(
            game,
            f"⚠️ <b>Could not DM:</b> {', '.join(_esc(n) for n in dm_failed)}\n"
            "<i>These players must open the bot and press /start.</i>",
            parse_mode=ParseMode.HTML,
        )
        return await _cancel_game(game, reason="Some players could not receive DM")

    await asyncio.sleep(1)

    # ── Public reveal: Monarch + Strategist ─────────────────────────────
    monarch = game.get_player(game.monarch_id)
    strategist = game.get_player(game.strategist_id)

    await _send_tracked(
        game,
        "🎭 <b>PUBLIC REVEAL</b>\n\n"
        f"👑 <b>THE MONARCH:</b> {monarch['mention']}\n"
        f"🧠 <b>THE STRATEGIST:</b> {strategist['mention']}\n\n"
        "🔒 The Sentinel and Phantom remain hidden.",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(2)

    # ── Scene 2: Monarch speaks ────────────────────────────────────────
    await _send_tracked(
        game,
        f"👑 <b>THE MONARCH:</b>\n\"{_esc(get_monarch_line())}\"",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(2)

    await _send_tracked(
        game,
        f"👑 <b>THE MONARCH:</b>\n\"{_esc(get_monarch_followup())}\"",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(2)

    # ── Scene 3: Strategist responds ───────────────────────────────────
    await _send_tracked(
        game,
        f"🧠 <b>THE STRATEGIST:</b>\n\"{_esc(get_strategist_line())}\"",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(2)

    # ── Scene 4: Interrogation (Sentinel vs Phantom) ───────────────────
    for line in get_interrogation():
        await _send_tracked(game, line, parse_mode=ParseMode.HTML)
        await asyncio.sleep(2)

    # ── Scene 5: Cross exchange ────────────────────────────────────────
    for line in get_cross_exchange():
        await _send_tracked(game, line, parse_mode=ParseMode.HTML)
        await asyncio.sleep(2)

    game.state = STATE_ASSIGNED
    await persist_game(game)

    # ── Scene 6: Final interrogation + guess buttons ───────────────────
    await asyncio.sleep(1)
    await _send_tracked(game, get_final_interrogation(), parse_mode=ParseMode.HTML)

    game.state = STATE_GUESSING
    await persist_game(game)

    s1, s2 = game.suspects[0], game.suspects[1]
    prompt = _render_guess_prompt(game, s1, s2)

    sent = await _send_tracked(
        game, prompt,
        parse_mode=ParseMode.HTML,
        reply_markup=_guess_kb(game),
    )
    if sent and getattr(sent, "id", None):
        game.guess_message_id = sent.id

    game.guess_task = asyncio.create_task(_guess_timer(game))


async def _send_role_dm(uid: int, role: str, name: str) -> bool:
    emoji = ROLE_EMOJI.get(role, "❔")
    label = ROLE_LABEL.get(role, "?")

    descriptions = {
        ROLE_MONARCH: "You are the ruler. Your vault was breached. You demand justice.",
        ROLE_STRATEGIST: "You are the mind. You have 30 seconds to accuse the Phantom.",
        ROLE_SENTINEL: "You are the shield. You're loyal, but currently a suspect.",
        ROLE_PHANTOM: "You are the thief. Stay hidden. If the Strategist guesses wrong, you walk free.",
    }

    text = (
        f"🎭 <b>YOUR SECRET ROLE</b>\n\n"
        f"{emoji} <b>{label}</b>\n\n"
        f"<i>{_esc(descriptions.get(role, ''))}</i>\n\n"
        "🤫 <b>Do not reveal this to anyone.</b>"
    )

    sent = await _safe_dm(uid, text, parse_mode=ParseMode.HTML)
    return sent is not None


# ══════════════════════════════════════════════════════════════════════════════
#  GUESS TIMER
# ══════════════════════════════════════════════════════════════════════════════
async def _guess_timer(game: ShadowGame):
    try:
        await asyncio.sleep(GUESS_SECONDS)
        if game.state != STATE_GUESSING:
            return
        game.handle_timeout()
        await _resolve_game(game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Shadow guess timer] {type(e).__name__}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  GUESS CALLBACK
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^shadow_guess:"))
async def shadow_guess_cb(_, q: CallbackQuery):
    try:
        _, cid_str, target_str = q.data.split(":", 2)
        chat_id = int(cid_str)
        target_uid = int(target_str)
    except (ValueError, IndexError):
        return await q.answer()

    game = get_game(chat_id)
    if not game or game.state != STATE_GUESSING:
        return await q.answer("Guessing phase is over.", show_alert=True)

    ok, reason = game.submit_guess(q.from_user.id, target_uid)
    if not ok:
        return await q.answer(reason, show_alert=True)

    await q.answer("✅ Accusation locked!")

    if game.guess_task and not game.guess_task.done():
        game.guess_task.cancel()

    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _resolve_game(game)


# ══════════════════════════════════════════════════════════════════════════════
#  RESOLVE GAME
# ══════════════════════════════════════════════════════════════════════════════
async def _resolve_game(game: ShadowGame):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    if game.payout_done:
        return

    game.state = STATE_REVEALING
    game.cancel_timers()
    game.calculate_rewards()

    for uid, amount in game.rewards.items():
        if amount > 0:
            await _ensure_user_record(uid)
            await _credit_user(uid, amount)

    game.payout_done = True
    game.state = STATE_FINISHED
    game.finished_at = datetime.now(timezone.utc)

    reveal_text = _render_reveal(game)

    reveal_msg = await _safe_send(
        game.chat_id,
        reveal_text,
        parse_mode=ParseMode.HTML,
    )
    reveal_id = getattr(reveal_msg, "id", None)

    correct = (game.guess_result == "correct")
    for p in game.players:
        role = p["role"]
        coins = game.rewards.get(p["user_id"], 0)

        won = False
        correct_guess = None
        if role == ROLE_MONARCH:
            won = True
        elif role == ROLE_STRATEGIST:
            won = correct
            correct_guess = correct
        elif role == ROLE_SENTINEL:
            won = True
        elif role == ROLE_PHANTOM:
            won = not correct
            correct_guess = not correct

        try:
            await record_result(
                p["user_id"], p["name"], role=role,
                won=won, correct_guess=correct_guess, coins_won=coins,
            )
        except Exception:
            pass

    await persist_game(game)

    keep_ids = [reveal_id] if reveal_id else []
    try:
        await _cleanup_game_messages(game, keep_ids=keep_ids)
    except Exception:
        pass

    remove_game(game.chat_id)
    try:
        await remove_persisted_game(game.chat_id)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  CANCEL
# ══════════════════════════════════════════════════════════════════════════════
async def _cancel_game(game: ShadowGame, reason: str):
    if game.state in (STATE_FINISHED, STATE_CANCELLED):
        return
    game.state = STATE_CANCELLED
    game.cancel_timers()
    game.finished_at = datetime.now(timezone.utc)

    await _send_tracked(
        game,
        f"🚫 <b>SHADOW SYNDICATE CANCELLED</b>\n\n<i>{_esc(reason)}</i>",
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
#  HELP / INFO / STATS / TOP
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["shadowhelp", "syndicatehelp"], prefixes=PREFIXES))
async def shadow_help_cmd(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["syndicateinfo"], prefixes=PREFIXES))
async def shadow_info(_, message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await _safe_reply(message, _render_help(), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["syndicatestats"], prefixes=PREFIXES))
async def shadow_stats(_, message: Message):
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
            f"📊 <b>{_esc(name)}'s Shadow Syndicate stats</b>\n\n❌ No games yet.",
            parse_mode=ParseMode.HTML,
        )

    played = int(doc.get("games_played", 0))
    correct_g = int(doc.get("correct_guesses", 0))
    wrong_g = int(doc.get("wrong_guesses", 0))
    total_guesses = correct_g + wrong_g
    wr = (correct_g / total_guesses * 100) if total_guesses else 0.0

    await _safe_reply(
        message,
        f"📊 <b>{_esc(name)}'s Shadow Syndicate stats</b>\n\n"
        f"🎮 Games: <code>{played}</code>\n"
        f"✅ Correct guesses: <code>{correct_g}</code>\n"
        f"❌ Wrong guesses: <code>{wrong_g}</code>\n"
        f"📈 Guess accuracy: <code>{wr:.1f}%</code>\n\n"
        f"👑 Wins as Monarch: <code>{int(doc.get('wins_as_monarch', 0))}</code>\n"
        f"🧠 Wins as Strategist: <code>{int(doc.get('wins_as_strategist', 0))}</code>\n"
        f"🛡️ Wins as Sentinel: <code>{int(doc.get('wins_as_sentinel', 0))}</code>\n"
        f"🃏 Wins as Phantom: <code>{int(doc.get('wins_as_phantom', 0))}</code>\n\n"
        f"💰 Total coins won: <code>{int(doc.get('total_coins_won', 0))}</code>",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command(["syndicatetop"], prefixes=PREFIXES))
async def shadow_top(_, message: Message):
    try:
        rows = await top_players(10)
    except Exception:
        rows = []

    if not rows:
        return await _safe_reply(
            message,
            "🏆 <b>Shadow Syndicate Leaderboard</b>\n\n❌ No games yet.",
            parse_mode=ParseMode.HTML,
        )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>Shadow Syndicate Leaderboard</b>\n"]
    for i, row in enumerate(rows, 1):
        rank = medals.get(i, f"{i}.")
        nm = row.get("name") or str(row["_id"])
        coins = int(row.get("total_coins_won", 0))
        correct = int(row.get("correct_guesses", 0))
        lines.append(
            f"{rank} <b>{_esc(nm)}</b> — 💰 <code>{coins}</code> • "
            f"✅ <code>{correct}</code>"
        )
    await _safe_reply(message, "\n".join(lines), parse_mode=ParseMode.HTML)
