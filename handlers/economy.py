"""Telegram handlers for the isolated economy system. (Premium UI + Elara Special)"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from pyrogram import filters, StopPropagation
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.errors import RPCError

from core.bot import app
from database.mongo import db
from core.database import (
    ensure_user,
    get_user,
    get_coin_rank,
    get_kill_rank,
    top_rich,
    top_killers,
)
from core.economy import (
    check_user,
    claim_daily,
    deposit_wallet,
    kill_user,
    net_after_tax,
    protect_user,
    rob_user,
    tax_for,
    transfer,
    withdraw_wallet,
    ELARA_BOT_ID,
)

PREFIXES = ["/", ".", "!"]
OWNER_ID = int(getattr(__import__("config"), "OWNER_ID", 0) or 0)

REVIVE_FEE = 500
SET_EMOJI_FEE = 2000


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _esc(v):
    return escape(str(v or ""))


def _mention(user_id, name):
    return f'<a href="tg://user?id={int(user_id)}">{_esc(name or "User")}</a>'


def _name(user):
    return (
        getattr(user, "first_name", None)
        or getattr(user, "username", None)
        or str(getattr(user, "id", "User"))
    )


def _reply_target(message):
    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user
    return None


async def _ensure_from_message(message):
    if message.from_user:
        await ensure_user(message.from_user)


async def _resolve_private_target(message, token):
    try:
        if token.lstrip("-").isdigit():
            return await app.get_users(int(token))
        return await app.get_users(token.lstrip("@"))
    except Exception:
        return None


async def _is_owner(message):
    return bool(message.from_user and int(message.from_user.id) == OWNER_ID)


def _shop_collection():
    from database.mongo import economy_shop
    return economy_shop()


def _format_remaining(seconds: int) -> str:
    """Format seconds → '23ʜ 45ᴍ 12ꜱ'."""
    if seconds <= 0:
        return "—"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append(f"{h}ʜ")
    if m:
        parts.append(f"{m}ᴍ")
    if s or not parts:
        parts.append(f"{s}ꜱ")
    return " ".join(parts)


# ─── Economy Close/Open per GC ────────────────────────────────────────────────
async def _is_economy_enabled(chat_id):
    if db is None:
        return True
    doc = await db["economy_settings"].find_one({"chat_id": int(chat_id)})
    if not doc:
        return True
    return bool(doc.get("enabled", True))


async def _set_economy(chat_id, enabled):
    if db is None:
        return False
    await db["economy_settings"].update_one(
        {"chat_id": int(chat_id)},
        {"$set": {"chat_id": int(chat_id), "enabled": bool(enabled)}},
        upsert=True,
    )
    return True


@app.on_message(filters.command("close", prefixes=PREFIXES) & filters.group)
async def economy_close(_, message):
    if not message.from_user:
        return
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            if int(message.from_user.id) != OWNER_ID:
                return await message.reply("❌ <b>ᴀᴅᴍɪɴ ᴏɴʟʏ.</b>")
    except Exception:
        return await message.reply("❌ <b>ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ.</b>")

    ok = await _set_economy(message.chat.id, False)
    if not ok:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    await message.reply(
        "🔒 <b>ᴇᴄᴏɴᴏᴍʏ ᴄʟᴏꜱᴇᴅ</b>\n\n"
        "<i>ᴀʟʟ ᴇᴄᴏɴᴏᴍʏ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ɴᴏᴡ ᴅɪꜱᴀʙʟᴇᴅ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.</i>\n\n"
        "🔄 <b>ꜰᴏʀ ʀᴇᴏᴘᴇɴɪɴɢ :</b> <code>/open</code>",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command("open", prefixes=PREFIXES) & filters.group)
async def economy_open(_, message):
    if not message.from_user:
        return
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            if int(message.from_user.id) != OWNER_ID:
                return await message.reply("❌ <b>ᴀᴅᴍɪɴ ᴏɴʟʏ.</b>")
    except Exception:
        return await message.reply("❌ <b>ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ.</b>")

    ok = await _set_economy(message.chat.id, True)
    if not ok:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    await message.reply(
        "🔓 <b>ᴇᴄᴏɴᴏᴍʏ ᴏᴘᴇɴᴇᴅ</b>\n\n"
        "<i>ᴀʟʟ ᴇᴄᴏɴᴏᴍʏ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ɴᴏᴡ ᴇɴᴀʙʟᴇᴅ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.</i>",
        parse_mode=ParseMode.HTML,
    )


# ─── Global Economy Guard ─────────────────────────────────────────────────────
ECONOMY_COMMANDS = {
    "bal", "balance", "daily", "kill", "revive", "rob",
    "wallet", "give", "protect", "check", "setemoji",
    "toprich", "topkillers", "shop", "buy", "gift",
    "inventory", "inv", "items", "sell",
}


@app.on_message(filters.group, group=-50)
async def _economy_guard(_, message):
    if not message.text and not message.caption:
        return
    text = (message.text or message.caption or "").strip()
    if not text or text[0] not in PREFIXES:
        return
    cmd = text[1:].split()[0].split("@")[0].lower()
    if cmd not in ECONOMY_COMMANDS:
        return
    if message.from_user and int(message.from_user.id) == OWNER_ID:
        return
    if not await _is_economy_enabled(message.chat.id):
        try:
            await message.reply(
                "🔒 <b>ᴇᴄᴏɴᴏᴍʏ ᴄʟᴏꜱᴇᴅ</b>\n\n"
                "<i>ᴀʟʟ ᴇᴄᴏɴᴏᴍʏ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ɴᴏᴡ ᴅɪꜱᴀʙʟᴇᴅ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.</i>\n\n"
                "🔄 <b>ꜰᴏʀ ʀᴇᴏᴘᴇɴɪɴɢ :</b> <code>/open</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        raise StopPropagation


# ─── Profile ──────────────────────────────────────────────────────────────────
async def _profile_text(user):
    await ensure_user(user)
    doc = await get_user(user.id)
    coin_rank = await get_coin_rank(user.id)
    kill_rank = await get_kill_rank(user.id)

    inv_count = 0
    if db is not None:
        try:
            inv_count = await db["economy_inventory"].count_documents({"user_id": user.id})
        except Exception:
            inv_count = 0

    level = int(doc.get("level", 1))
    xp = int(doc.get("xp", 0))
    required = level * 1000

    status = str(doc.get("status", "alive"))
    status_icon = "🟢 ᴀʟɪᴠᴇ" if status == "alive" else "☠️ ᴅᴇᴀᴅ"

    emoji = doc.get("custom_emoji") or "👤"

    return (
        f"{emoji} <b>{_esc(_name(user))}</b>\n\n"
        f"<blockquote>"
        f"💰 <b>ᴇᴅᴏʟʟᴇʀꜱ</b> — <code>{int(doc.get('coins', 0))}</code> $\n"
        f"🏆 <b>ɢʟᴏʙᴀʟ ʀᴀɴᴋ</b> — <code>#{coin_rank or '—'}</code>\n"
        f"🎒 <b>ɪɴᴠᴇɴᴛᴏʀʏ</b> — <code>{inv_count}</code> ɪᴛᴇᴍꜱ\n"
        f"🔓 <b>ꜱᴛᴀᴛᴜꜱ</b> — {status_icon}\n"
        f"⚔️ <b>ᴋɪʟʟꜱ</b> — <code>{int(doc.get('kills', 0))}</code> (#{kill_rank or '—'})\n"
        f"💠 <b>ʟᴇᴠᴇʟ</b> — <code>{level}</code> • <code>{xp}/{required}</code> xᴘ"
        f"</blockquote>\n"
        f"<blockquote><i>ᴜꜱᴇ <code>/setemoji</code> ᴛᴏ ᴄᴜꜱᴛᴏᴍɪᴢᴇ ʏᴏᴜʀ ᴇᴍᴏᴊɪ.</i></blockquote>"
    )


# ─── Balance ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command(["bal", "balance"], prefixes=PREFIXES))
async def economy_balance(_, message):
    await _ensure_from_message(message)

    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command or []) > 1:
        return await message.reply(
            "❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/bal</code> ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ.",
            parse_mode=ParseMode.HTML,
        )

    if not target:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ.</b>")

    if target.is_bot:
        if int(target.id) == ELARA_BOT_ID:
            await ensure_user(target)
            await message.reply(await _profile_text(target), parse_mode=ParseMode.HTML)
            return
        return await message.reply(
            "🤖 <b>ᴛʜɪꜱ ᴜꜱᴇʀ ɪꜱ ᴀ ʙᴏᴛ.</b>\n"
            "<i>ʙᴏᴛꜱ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴇᴄᴏɴᴏᴍʏ ᴀᴄᴄᴏᴜɴᴛꜱ.</i>",
            parse_mode=ParseMode.HTML,
        )

    await ensure_user(target)
    await message.reply(await _profile_text(target), parse_mode=ParseMode.HTML)


# ─── Daily ────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("daily", prefixes=PREFIXES))
async def economy_daily(_, message):
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply("❌ <b>ᴅᴀɪʟʏ ᴏɴʟʏ ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ.</b>")
    await _ensure_from_message(message)
    result = await claim_daily(message.from_user.id)
    if not result["ok"]:
        if result["reason"] == "already_claimed":
            return await message.reply(
                "🎁 <b>ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ.</b>\n<i>ᴄᴏᴍᴇ ʙᴀᴄᴋ ᴀꜰᴛᴇʀ ᴍɪᴅɴɪɢʜᴛ.</i>",
                parse_mode=ParseMode.HTML,
            )
        return await message.reply("❌ <b>ᴇᴄᴏɴᴏᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    await message.reply(
        "🎁 <b>ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ ᴄʟᴀɪᴍᴇᴅ</b>\n\n"
        f"<blockquote>"
        f"💰 <b>ʀᴇᴡᴀʀᴅ</b> — <code>+{result['reward']}</code> $\n"
        f"💳 <b>ʙᴀʟᴀɴᴄᴇ</b> — <code>{result['balance']}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Kill ─────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("kill", prefixes=PREFIXES))
async def economy_kill(_, message):
    await _ensure_from_message(message)
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴛᴏ ᴜꜱᴇ /kill.</b>")

    result = await kill_user(message.from_user.id, target.id)
    reason = result.get("reason")

    if reason == "elara_kill_roast":
        return await message.reply(
            f"😎 <b>{result.get('roast', 'Nice try.')}</b>",
            parse_mode=ParseMode.HTML,
        )

    if reason == "protected":
        return await message.reply(
            "🛡️ <b>ᴠɪᴄᴛɪᴍ ɪꜱ ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʀɪɢʜᴛ ɴᴏᴡ.</b>\n\n"
            "🔒 <b>ᴄʜᴇᴄᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴛɪᴍᴇ :</b> <code>/check</code> <i>(reply)</i>",
            parse_mode=ParseMode.HTML,
        )

    if not result["ok"]:
        return await message.reply({
            "self": "❌ ᴋɪʟʟ ʏᴏᴜʀꜱᴇʟꜰ ɴᴀʜɪ ᴋᴀʀ ꜱᴀᴋᴛᴇ.",
            "dead": "☠️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴀʟʀᴇᴀᴅʏ ᴅᴇᴀᴅ.",
            "killer_dead": "☠️ ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ᴋɪʟʟ.",
            "killer_unavailable": "❌ ʏᴏᴜʀ ᴋɪʟʟ ꜰᴀɪʟᴇᴅ.",
            "not_available": "❌ ᴛᴀʀɢᴇᴛ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.",
            "transaction_unavailable": "❌ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ.",
        }.get(reason, "❌ <b>ᴋɪʟʟ ꜰᴀɪʟᴇᴅ.</b>"), parse_mode=ParseMode.HTML)

    level_info = result.get("level", {})
    level_note = f"\n💠 <b>ʟᴇᴠᴇʟ ᴜᴘ</b> — <code>{level_info['level']}</code>" if level_info.get("levels") else ""

    await message.reply(
        "⚔️ <b>ᴋɪʟʟ ꜱᴜᴄᴄᴇꜱꜱ</b>\n\n"
        f"<blockquote>"
        f"💀 <b>ᴛᴀʀɢᴇᴛ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ʀᴇᴡᴀʀᴅ</b> — <code>+{result['coins']}</code> $\n"
        f"✨ <b>xᴘ</b> — <code>+{result['xp']}</code>{level_note}"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Revive ───────────────────────────────────────────────────────────────────
@app.on_message(filters.command("revive", prefixes=PREFIXES))
async def economy_revive(_, message):
    await _ensure_from_message(message)

    target = message.from_user
    is_self = True
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        is_self = (int(target.id) == int(message.from_user.id))

    if not target or target.is_bot:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ.</b>")

    reviver = await get_user(message.from_user.id)
    victim_doc = await get_user(target.id)

    if reviver is None or victim_doc is None:
        return await message.reply("❌ <b>ᴇᴄᴏɴᴏᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    if str(victim_doc.get("status", "alive")).lower() != "dead":
        return await message.reply(
            f"❌ {_mention(target.id, _name(target))} ɪꜱ ɴᴏᴛ ᴅᴇᴀᴅ.",
            parse_mode=ParseMode.HTML,
        )

    if not is_self:
        if str(reviver.get("status", "alive")).lower() != "alive":
            return await message.reply(
                "☠️ <b>ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ʀᴇᴠɪᴠᴇ ᴏᴛʜᴇʀꜱ.</b>\n"
                "<i>ᴘᴇʜʟᴇ ᴋʜᴜᴅ ᴋᴏ ʀᴇᴠɪᴠᴇ ᴋᴀʀᴏ <code>/revive</code> ꜱᴇ.</i>",
                parse_mode=ParseMode.HTML,
            )

    if int(reviver.get("coins", 0)) < REVIVE_FEE:
        return await message.reply(
            f"❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ᴇᴅᴏʟʟᴇʀꜱ.</b>\n"
            f"<i>ʀᴇᴠɪᴠᴇ ꜰᴇᴇ — <code>{REVIVE_FEE}</code> $</i>",
            parse_mode=ParseMode.HTML,
        )

    if db is None:
        return await message.reply("❌ <b>ᴇᴄᴏɴᴏᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    users_col = db["users"]
    deduct = await users_col.update_one(
        {"_id": message.from_user.id, "coins": {"$gte": REVIVE_FEE}},
        {"$inc": {"coins": -REVIVE_FEE}},
    )
    if deduct.modified_count != 1:
        return await message.reply("❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ꜰᴇᴇ.</b>")

    await users_col.update_one(
        {"_id": target.id},
        {"$set": {"status": "alive"}},
    )

    await users_col.update_one(
        {"_id": ELARA_BOT_ID},
        {"$inc": {"coins": REVIVE_FEE}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    new_balance = int(reviver.get("coins", 0)) - REVIVE_FEE
    await message.reply(
        "✨ <b>ʀᴇᴠɪᴠᴇ ꜱᴜᴄᴄᴇꜱꜱ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴜꜱᴇʀ</b> — {_mention(target.id, _name(target))}\n"
        f"🔓 <b>ꜱᴛᴀᴛᴜꜱ</b> — 🟢 ᴀʟɪᴠᴇ\n"
        f"💰 <b>ꜰᴇᴇ</b> — <code>-{REVIVE_FEE}</code> $\n"
        f"💳 <b>ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ</b> — <code>{new_balance}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Rob ──────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("rob", prefixes=PREFIXES))
async def economy_rob(_, message):
    await _ensure_from_message(message)
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴛᴏ ᴜꜱᴇ /rob.</b>")

    requested = None
    if len(message.command or []) == 2:
        try:
            requested = int(message.command[1])
            if requested <= 0:
                requested = None
        except ValueError:
            requested = None

    result = await rob_user(message.from_user.id, target.id, requested)
    reason = result.get("reason")

    if reason == "elara_roast":
        return await message.reply(
            f"😎 <b>{result.get('roast', 'Nice try.')}</b>",
            parse_mode=ParseMode.HTML,
        )

    if reason == "protected":
        return await message.reply(
            "🛡️ <b>ᴠɪᴄᴛɪᴍ ɪꜱ ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʀɪɢʜᴛ ɴᴏᴡ.</b>\n\n"
            "🔒 <b>ᴄʜᴇᴄᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴛɪᴍᴇ :</b> <code>/check</code> <i>(reply)</i>",
            parse_mode=ParseMode.HTML,
        )

    if not result.get("ok"):
        return await message.reply({
            "self": "❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ʀᴏʙ ʏᴏᴜʀꜱᴇʟꜰ.",
            "cooldown": "⏳ ʏᴏᴜ'ʀᴇ ʀᴏʙʙɪɴɢ ᴛᴏᴏ ꜰᴀꜱᴛ.\n<i>ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</i>",
            "insufficient": "❌ ᴛᴀʀɢᴇᴛ ʜᴀꜱ ɴᴏ ʟɪQᴜɪᴅ ᴇᴅᴏʟʟᴇʀꜱ.",
            "not_available": "❌ ᴛᴀʀɢᴇᴛ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.",
            "transaction_unavailable": "❌ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ.",
        }.get(reason, "❌ <b>ʀᴏʙ ꜰᴀɪʟᴇᴅ.</b>"), parse_mode=ParseMode.HTML)

    await message.reply(
        "💸 <b>ʀᴏʙ ꜱᴜᴄᴄᴇꜱꜱ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴛᴀʀɢᴇᴛ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ꜱᴛᴏʟᴇɴ</b> — <code>{result.get('gross', result['amount'])}</code> $\n"
        f"🧾 <b>ᴛᴀx</b> — <code>{result.get('tax', 0)}</code> $\n"
        f"📥 <b>ʀᴇᴄᴇɪᴠᴇᴅ</b> — <code>{result['amount']}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Wallet ───────────────────────────────────────────────────────────────────
@app.on_message(filters.command("wallet", prefixes=PREFIXES))
async def economy_wallet(_, message):
    await _ensure_from_message(message)
    if len(message.command or []) != 2:
        doc = await get_user(message.from_user.id)
        total = int(doc.get("coins", 0)) + int(doc.get("wallet", 0))
        maximum = int(total * 0.30)
        return await message.reply(
            "🏦 <b>ᴡᴀʟʟᴇᴛ</b>\n\n"
            f"<blockquote>"
            f"💰 <b>ʟɪQᴜɪᴅ</b> — <code>{int(doc.get('coins', 0))}</code> $\n"
            f"🔐 <b>ᴡᴀʟʟᴇᴛ</b> — <code>{int(doc.get('wallet', 0))}</code> $\n"
            f"📦 <b>ᴍᴀx ᴄᴀᴘᴀᴄɪᴛʏ</b> — <code>{maximum}</code> $"
            f"</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    raw = message.command[1]
    try:
        amount = int(raw)
    except ValueError:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/wallet +300</code> ᴏʀ <code>/wallet -300</code>", parse_mode=ParseMode.HTML)
    if amount == 0:
        return await message.reply("❌ <b>ᴀᴍᴏᴜɴᴛ ᴢᴇʀᴏ ɴᴀʜɪ.</b>")
    result = (
        await deposit_wallet(message.from_user.id, amount)
        if amount > 0
        else await withdraw_wallet(message.from_user.id, abs(amount))
    )
    if not result["ok"]:
        if result["reason"] == "wallet_limit":
            return await message.reply(f"❌ <b>ᴡᴀʟʟᴇᴛ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ.</b>\n<i>ᴍᴀx — <code>{result['maximum']}</code> $</i>", parse_mode=ParseMode.HTML)
        if result["reason"] == "insufficient":
            return await message.reply("❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ.</b>")
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴡᴀʟʟᴇᴛ ᴏᴘᴇʀᴀᴛɪᴏɴ.</b>")
    await message.reply(
        "🏦 <b>ᴡᴀʟʟᴇᴛ ᴜᴘᴅᴀᴛᴇᴅ</b>\n\n"
        f"<blockquote>"
        f"💰 <b>ʟɪQᴜɪᴅ</b> — <code>{result['coins']}</code> $\n"
        f"🔐 <b>ᴡᴀʟʟᴇᴛ</b> — <code>{result['wallet']}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Give ─────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("give", prefixes=PREFIXES))
async def economy_give(_, message):
    await _ensure_from_message(message)
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ʀᴇᴄɪᴘɪᴇɴᴛ.</b>\n<i>ᴜꜱᴀɢᴇ — <code>/give &lt;amount&gt;</code></i>", parse_mode=ParseMode.HTML)

    if target.is_bot and int(target.id) != ELARA_BOT_ID:
        return await message.reply(
            "🤖 <b>ʏᴏᴜ ᴄᴀɴ'ᴛ ᴛʀᴀɴꜱꜰᴇʀ ᴛᴏ ᴀ ʙᴏᴛ.</b>",
            parse_mode=ParseMode.HTML,
        )

    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/give &lt;amount&gt;</code>", parse_mode=ParseMode.HTML)
    try:
        amount = int(message.command[1])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>")
    result = await transfer(message.from_user.id, target.id, amount)
    if not result["ok"]:
        return await message.reply({
            "self": "❌ ᴋʜᴜᴅ ᴋᴏ ɴᴀʜɪ ᴅᴇ ꜱᴀᴋᴛᴇ.",
            "invalid_amount": "❌ ᴀᴍᴏᴜɴᴛ 0 ꜱᴇ ʙᴀᴅᴀ.",
            "insufficient": "❌ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʟɪQᴜɪᴅ.",
            "transaction_unavailable": "❌ ᴛʀᴀɴꜱꜰᴇʀ ꜰᴀɪʟᴇᴅ.",
        }.get(result.get("reason"), "❌ <b>ᴛʀᴀɴꜱꜰᴇʀ ꜰᴀɪʟᴇᴅ.</b>"), parse_mode=ParseMode.HTML)
    await message.reply(
        "💸 <b>ᴛʀᴀɴꜱꜰᴇʀ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴛᴏ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ꜱᴇɴᴛ</b> — <code>{result['gross']}</code> $\n"
        f"🧾 <b>ᴛᴀx</b> — <code>{result['tax']}</code> $\n"
        f"📥 <b>ʀᴇᴄᴇɪᴠᴇᴅ</b> — <code>{result['net']}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Protect ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("protect", prefixes=PREFIXES))
async def economy_protect(_, message):
    await _ensure_from_message(message)
    if len(message.command or []) != 2 or message.command[1].lower() != "1d":
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/protect 1d</code>", parse_mode=ParseMode.HTML)
    result = await protect_user(message.from_user.id)
    if not result["ok"]:
        if result["reason"] == "already_protected":
            return await message.reply("🛡️ <b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ.</b>")
        if result["reason"] == "insufficient":
            return await message.reply("❌ <b>ʏᴏᴜ ɴᴇᴇᴅ 500 $.</b>")
        return await message.reply("❌ <b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ.</b>")

    until = result["until"].astimezone(timezone.utc).strftime("%d %b %Y, %I:%M %p")
    dm_text = (
        "🛡️ <b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ</b>\n\n"
        f"<blockquote>"
        f"💰 <b>ᴄᴏꜱᴛ</b> — <code>500</code> $\n"
        f"⏳ <b>ᴇxᴘɪʀᴇꜱ</b> — <code>{until}</code>\n"
        f"🔒 <b>ᴘʀᴏᴛᴇᴄᴛᴇᴅ ꜰʀᴏᴍ</b> — /rob & /kill"
        f"</blockquote>"
    )
    try:
        await app.send_message(message.from_user.id, dm_text, parse_mode=ParseMode.HTML)
        dm_note = "ᴅᴇᴛᴀɪʟꜱ ꜱᴇɴᴛ ɪɴ ᴅᴍ."
    except Exception:
        dm_note = "ᴅᴍ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ."
    await message.reply(f"🛡️ <b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.</b>\n<i>{dm_note}</i>", parse_mode=ParseMode.HTML)


# ─── Check ────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("check", prefixes=PREFIXES))
async def economy_check(_, message):
    await _ensure_from_message(message)
    target = None
    if message.chat.type == ChatType.PRIVATE:
        if len(message.command or []) != 2:
            return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/check @username</code> ᴏʀ <code>/check user_id</code>", parse_mode=ParseMode.HTML)
        target = await _resolve_private_target(message, message.command[1])
    else:
        target = _reply_target(message)
        if len(message.command or []) > 1:
            return await message.reply("❌ <b>ɪɴ ɢʀᴏᴜᴘꜱ ʀᴇᴘʟʏ ᴏɴʟʏ.</b>")
    if not target:
        return await message.reply("❌ <b>ᴛᴀʀɢᴇᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
    if target.is_bot:
        return await message.reply("🤖 <b>ʙᴏᴛꜱ ᴄᴀɴɴᴏᴛ ʙᴇ ᴄʜᴇᴄᴋᴇᴅ.</b>")
    if target.id == message.from_user.id:
        return await message.reply("❌ <b>ᴋʜᴜᴅ ᴋᴏ ᴄʜᴇᴄᴋ ɴᴀʜɪ.</b>")

    result = await check_user(message.from_user.id, target.id)
    if not result["ok"]:
        if result["reason"] == "insufficient":
            return await message.reply("❌ <b>ʏᴏᴜ ɴᴇᴇᴅ 500 $.</b>")
        return await message.reply("❌ <b>ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ.</b>")

    doc = result["target"]
    protected = "🟢 ᴀᴄᴛɪᴠᴇ" if result["protected"] else "🔴 ɪɴᴀᴄᴛɪᴠᴇ"

    protection_line = ""
    if result["protected"]:
        secs = int(result.get("protection_remaining", 0))
        if secs > 0:
            protection_line = f"\n⏳ <b>ᴇxᴘɪʀᴇꜱ ɪɴ</b> — <code>{_format_remaining(secs)}</code>"

    details = (
        f"🔎 <b>ᴄʜᴇᴄᴋ — {_esc(_name(target))}</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴜꜱᴇʀ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ᴇᴅᴏʟʟᴇʀꜱ</b> — <code>{int(doc.get('coins', 0))}</code> $\n"
        f"🔐 <b>ᴡᴀʟʟᴇᴛ</b> — <code>{int(doc.get('wallet', 0))}</code> $\n"
        f"💠 <b>ʟᴇᴠᴇʟ</b> — <code>{int(doc.get('level', 1))}</code>\n"
        f"⚔️ <b>ᴋɪʟʟꜱ</b> — <code>{int(doc.get('kills', 0))}</code>\n"
        f"🔓 <b>ꜱᴛᴀᴛᴜꜱ</b> — {_esc(doc.get('status', 'alive')).upper()}\n"
        f"🛡️ <b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ</b> — {protected}"
        f"{protection_line}"
        f"</blockquote>"
    )
    try:
        await app.send_message(message.from_user.id, details, parse_mode=ParseMode.HTML)
        if message.chat.type != ChatType.PRIVATE:
            return await message.reply(
                "🔎 <b>ᴄʜᴇᴄᴋ ᴅᴇᴛᴀɪʟꜱ ꜱᴇɴᴛ ɪɴ ᴅᴍ.</b>\n\n"
                f"<blockquote>💰 <b>ᴄʜᴀʀɢᴇᴅ</b> — <code>500</code> $</blockquote>",
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        return await message.reply(
            "❌ <b>ᴅᴍ ɴᴀʜɪ ʙʜᴇᴊ ꜱᴀᴋᴀ.</b>\n"
            "<i>ᴘʟᴇᴀꜱᴇ ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ɪɴ ᴅᴍ ꜰɪʀꜱᴛ.</i>",
            parse_mode=ParseMode.HTML,
        )


# ─── Set Custom Emoji ─────────────────────────────────────────────────────────
@app.on_message(filters.command(["setemoji", "set_emoji"], prefixes=PREFIXES))
async def economy_setemoji(_, message):
    await _ensure_from_message(message)
    if len(message.command or []) != 2:
        return await message.reply(
            "❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/setemoji 😎</code>\n\n"
            f"<i>ꜰᴇᴇ — <code>{SET_EMOJI_FEE}</code> $</i>",
            parse_mode=ParseMode.HTML,
        )
    emoji = message.command[1].strip()
    if not emoji or len(emoji) > 8:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴇᴍᴏᴊɪ.</b>")

    user = await get_user(message.from_user.id)
    if user is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    if int(user.get("coins", 0)) < SET_EMOJI_FEE:
        return await message.reply(
            f"❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ᴇᴅᴏʟʟᴇʀꜱ.</b>\n"
            f"<i>ꜰᴇᴇ — <code>{SET_EMOJI_FEE}</code> $</i>\n"
            f"<i>ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ — <code>{int(user.get('coins', 0))}</code> $</i>",
            parse_mode=ParseMode.HTML,
        )

    if db is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    users_col = db["users"]
    result = await users_col.update_one(
        {"_id": message.from_user.id, "coins": {"$gte": SET_EMOJI_FEE}},
        {"$inc": {"coins": -SET_EMOJI_FEE}, "$set": {"custom_emoji": emoji}},
    )
    if result.modified_count != 1:
        return await message.reply("❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ꜱᴇᴛ ᴇᴍᴏᴊɪ.</b>")

    await users_col.update_one(
        {"_id": ELARA_BOT_ID},
        {"$inc": {"coins": SET_EMOJI_FEE}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    new_balance = int(user.get("coins", 0)) - SET_EMOJI_FEE
    await message.reply(
        f"{emoji} <b>ᴄᴜꜱᴛᴏᴍ ᴇᴍᴏᴊɪ ꜱᴇᴛ</b>\n\n"
        f"<blockquote>"
        f"✨ <b>ᴇᴍᴏᴊɪ</b> — {emoji}\n"
        f"💰 <b>ꜰᴇᴇ</b> — <code>{SET_EMOJI_FEE}</code> $\n"
        f"💳 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ</b> — <code>{new_balance}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Top Rich ─────────────────────────────────────────────────────────────────
@app.on_message(filters.command("toprich", prefixes=PREFIXES))
async def economy_toprich(_, message):
    await _ensure_from_message(message)
    rows = await top_rich(10)
    if not rows:
        return await message.reply("❌ <b>ɴᴏ ᴇᴄᴏɴᴏᴍʏ ᴜꜱᴇʀꜱ.</b>")
    lines = ["🏆 <b>ɢʟᴏʙᴀʟ ᴛᴏᴘ 10 ʀɪᴄʜᴇꜱᴛ</b>\n"]
    for i, row in enumerate(rows, 1):
        name = row.get("first_name") or row.get("username") or str(row["_id"])
        emoji = row.get("custom_emoji") or "👤"
        wealth = int(row.get("wealth", 0))
        lines.append(f"{i}. {emoji} <b>{_esc(name)}</b> — <code>{wealth}</code> $")
    lines.append("\n<blockquote><i>ᴜꜱᴇ <code>/setemoji</code> ᴛᴏ ᴄᴜꜱᴛᴏᴍɪᴢᴇ ʏᴏᴜʀ ᴇᴍᴏᴊɪ.</i></blockquote>")
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


# ─── Top Killers ──────────────────────────────────────────────────────────────
@app.on_message(filters.command("topkillers", prefixes=PREFIXES))
async def economy_topkillers(_, message):
    await _ensure_from_message(message)
    rows = await top_killers(10)
    if not rows:
        return await message.reply("❌ <b>ɴᴏ ᴇᴄᴏɴᴏᴍʏ ᴜꜱᴇʀꜱ.</b>")
    lines = ["⚔️ <b>ɢʟᴏʙᴀʟ ᴛᴏᴘ 10 ᴋɪʟʟᴇʀꜱ</b>\n"]
    for i, row in enumerate(rows, 1):
        name = row.get("first_name") or row.get("username") or str(row["_id"])
        emoji = row.get("custom_emoji") or "👤"
        kills = int(row.get("kills", 0))
        lines.append(f"{i}. {emoji} <b>{_esc(name)}</b> — <code>{kills}</code> ⚔️")
    lines.append("\n<blockquote><i>ᴜꜱᴇ <code>/kill</code> ᴛᴏ ᴄʟɪᴍʙ ᴛʜᴇ ʀᴀɴᴋꜱ.</i></blockquote>")
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


# ─── Owner: Add/Remove Coins ──────────────────────────────────────────────────
@app.on_message(filters.command(["addcoins", "add_edollers"], prefixes=PREFIXES))
async def economy_addcoins(_, message):
    if not await _is_owner(message):
        return
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ.</b>\n<i>ᴜꜱᴀɢᴇ — <code>/addcoins 500</code></i>", parse_mode=ParseMode.HTML)
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/addcoins 500</code>", parse_mode=ParseMode.HTML)
    try:
        amount = int(message.command[1])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>")
    if amount <= 0:
        return await message.reply("❌ <b>ᴘᴏꜱɪᴛɪᴠᴇ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ.</b>")
    if db is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    users_col = db["users"]
    await users_col.update_one(
        {"_id": target.id},
        {"$inc": {"coins": amount}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    await message.reply(
        f"✅ <b>ᴀᴅᴅᴇᴅ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴜꜱᴇʀ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ᴀᴍᴏᴜɴᴛ</b> — <code>+{amount}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command(["removecoins", "remove_edollers"], prefixes=PREFIXES))
async def economy_removecoins(_, message):
    if not await _is_owner(message):
        return
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ.</b>\n<i>ᴜꜱᴀɢᴇ — <code>/removecoins 500</code></i>", parse_mode=ParseMode.HTML)
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/removecoins 500</code>", parse_mode=ParseMode.HTML)
    try:
        amount = int(message.command[1])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.</b>")
    if amount <= 0:
        return await message.reply("❌ <b>ᴘᴏꜱɪᴛɪᴠᴇ ʜᴏɴᴀ ᴄʜᴀʜɪʏᴇ.</b>")
    if db is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    users_col = db["users"]
    result = await users_col.update_one(
        {"_id": target.id, "coins": {"$gte": amount}},
        {"$inc": {"coins": -amount}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count != 1:
        return await message.reply("❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ᴏʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
    await message.reply(
        f"✅ <b>ʀᴇᴍᴏᴠᴇᴅ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴜꜱᴇʀ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ᴀᴍᴏᴜɴᴛ</b> — <code>-{amount}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Shop ─────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("shop", prefixes=PREFIXES))
async def economy_shop(_, message):
    col = _shop_collection()
    if col is None:
        return await message.reply("❌ <b>ꜱʜᴏᴘ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    rows = await col.find({"enabled": True}).sort("item_id", 1).to_list(length=100)
    if not rows:
        return await message.reply("🛒 <b>ꜱʜᴏᴘ ᴇᴍᴘᴛʏ.</b>")
    lines = ["🛒 <b>ᴇᴄᴏɴᴏᴍʏ ꜱʜᴏᴘ</b>\n"]
    for i, item in enumerate(rows, 1):
        stock = item.get("stock", -1)
        stock_text = "∞" if int(stock) < 0 else str(stock)
        gift = " 🎁" if item.get("gift") else ""
        lines.append(
            f"<b>{i}.</b> <b>{_esc(item.get('item_id'))}</b> — {_esc(item.get('name', 'Item'))}{gift}\n"
            f"   💰 <code>{int(item.get('price', 0))}</code> $  |  📦 <code>{stock_text}</code>\n"
            f"   <i>{_esc(item.get('description', ''))}</i>"
        )
    await message.reply("\n\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command("buy", prefixes=PREFIXES))
async def economy_buy(_, message):
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/buy &lt;item_id&gt;</code>", parse_mode=ParseMode.HTML)
    await _ensure_from_message(message)
    query = message.command[1]
    col = _shop_collection()
    if col is None:
        return await message.reply("❌ <b>ꜱʜᴏᴘ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    item = await col.find_one({"item_id": query, "enabled": True})
    if not item and query.isdigit():
        idx = int(query) - 1
        if idx >= 0:
            all_items = await col.find({"enabled": True}).sort("item_id", 1).to_list(length=100)
            if idx < len(all_items):
                item = all_items[idx]
    if not item:
        return await message.reply("❌ <b>ɪᴛᴇᴍ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
    if int(item.get("stock", -1)) == 0:
        return await message.reply("❌ <b>ᴏᴜᴛ ᴏꜰ ꜱᴛᴏᴄᴋ.</b>")

    item_id = item.get("item_id")
    from database.mongo import mongo_client, users
    client = mongo_client()
    ucol = users()
    if client is None or ucol is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    price = int(item.get("price", 0))
    if price <= 0:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴘʀɪᴄᴇ.</b>")
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                stock_query = {"item_id": item_id, "enabled": True}
                stock_update = {}
                if int(item.get("stock", -1)) >= 0:
                    stock_query["stock"] = {"$gte": 1}
                    stock_update = {"$inc": {"stock": -1}}
                stock_result = (
                    await col.update_one(stock_query, stock_update, session=session)
                    if stock_update else None
                )
                if stock_update and stock_result.modified_count != 1:
                    await session.abort_transaction()
                    return await message.reply("❌ <b>ᴏᴜᴛ ᴏꜰ ꜱᴛᴏᴄᴋ.</b>")
                if (await ucol.update_one(
                    {"_id": message.from_user.id, "coins": {"$gte": price}},
                    {"$inc": {"coins": -price}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    session=session,
                )).modified_count != 1:
                    await session.abort_transaction()
                    return await message.reply("❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ.</b>")

                await ucol.update_one(
                    {"_id": ELARA_BOT_ID},
                    {"$inc": {"coins": price}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    upsert=True, session=session,
                )

                inv = db["economy_inventory"] if db is not None else None
                if inv is not None:
                    await inv.update_one(
                        {"user_id": message.from_user.id, "item_id": item_id},
                        {"$inc": {"quantity": 1},
                         "$set": {"name": item.get("name", item_id), "updated_at": datetime.now(timezone.utc)}},
                        upsert=True, session=session,
                    )
        return await message.reply(
            f"🛒 <b>ᴘᴜʀᴄʜᴀꜱᴇᴅ</b> — <code>{_esc(item.get('name', item_id))}</code>\n"
            f"<i>ᴘᴀɪᴅ — <code>{price}</code> $</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        return await message.reply("❌ <b>ᴘᴜʀᴄʜᴀꜱᴇ ꜰᴀɪʟᴇᴅ.</b>")


# ─── Inventory ────────────────────────────────────────────────────────────────
@app.on_message(filters.command(["inventory", "inv", "items"], prefixes=PREFIXES))
async def economy_inventory(_, message):
    await _ensure_from_message(message)
    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ.</b>")
    if db is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    inv_col = db["economy_inventory"]
    docs = await inv_col.find({"user_id": target.id}).to_list(length=100)

    if not docs:
        return await message.reply(
            f"🎒 <b>ɪɴᴠᴇɴᴛᴏʀʏ — {_esc(_name(target))}</b>\n\n"
            f"<blockquote><i>ᴇᴍᴘᴛʏ. ᴜꜱᴇ <code>/shop</code> ᴛᴏ ʙᴜʏ ɪᴛᴇᴍꜱ.</i></blockquote>",
            parse_mode=ParseMode.HTML,
        )

    shop_col = _shop_collection()
    lines = [f"🎒 <b>ɪɴᴠᴇɴᴛᴏʀʏ — {_esc(_name(target))}</b>\n"]
    for doc in docs:
        item_id = doc.get("item_id", "?")
        name = doc.get("name", item_id)
        qty = int(doc.get("quantity", 1))
        emoji = "📦"
        if shop_col is not None:
            shop_item = await shop_col.find_one({"item_id": item_id})
            if shop_item and shop_item.get("gift"):
                emoji = "🎁"
        lines.append(
            f"{emoji} <b>{_esc(name)}</b>\n"
            f"   🆔 <code>{_esc(item_id)}</code>  |  📦 <code>×{qty}</code>"
        )
    lines.append("\n<blockquote><i>ᴜꜱᴇ <code>/sell &lt;item_id&gt;</code> ᴛᴏ ꜱᴇʟʟ ʙᴀᴄᴋ.</i></blockquote>")
    await message.reply("\n\n".join(lines), parse_mode=ParseMode.HTML)


# ─── Sell ─────────────────────────────────────────────────────────────────────
@app.on_message(filters.command(["sell"], prefixes=PREFIXES))
async def economy_sell(_, message):
    await _ensure_from_message(message)
    if len(message.command or []) != 2:
        return await message.reply(
            "❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/sell &lt;item_id&gt;</code>\n"
            "<i>50% ʀᴇꜰᴜɴᴅ ᴍɪʟᴇɢᴀ.</i>",
            parse_mode=ParseMode.HTML,
        )
    item_id = message.command[1]
    if db is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    inv_col = db["economy_inventory"]
    doc = await inv_col.find_one({"user_id": message.from_user.id, "item_id": item_id})
    if not doc:
        return await message.reply("❌ <b>ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪꜱ ɪᴛᴇᴍ.</b>")

    shop_col = _shop_collection()
    if shop_col is None:
        return await message.reply("❌ <b>ꜱʜᴏᴘ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    shop_item = await shop_col.find_one({"item_id": item_id})
    if not shop_item:
        return await message.reply("❌ <b>ɪᴛᴇᴍ ɴᴏ ʟᴏɴɢᴇʀ ɪɴ ꜱʜᴏᴘ.</b>")

    price = int(shop_item.get("price", 0))
    refund = max(1, int(price * 0.5))
    users_col = db["users"]
    qty = int(doc.get("quantity", 1))

    if qty <= 1:
        await inv_col.delete_one({"user_id": message.from_user.id, "item_id": item_id})
    else:
        await inv_col.update_one(
            {"user_id": message.from_user.id, "item_id": item_id},
            {"$inc": {"quantity": -1}},
        )

    await users_col.update_one(
        {"_id": message.from_user.id},
        {"$inc": {"coins": refund}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    await message.reply(
        "💸 <b>ꜱᴏʟᴅ</b>\n\n"
        f"<blockquote>"
        f"📦 <b>ɪᴛᴇᴍ</b> — <code>{_esc(shop_item.get('name', item_id))}</code>\n"
        f"💰 <b>ʀᴇꜰᴜɴᴅ (50%)</b> — <code>+{refund}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Gift ─────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("gift", prefixes=PREFIXES))
async def economy_gift(_, message):
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ʀᴇᴄɪᴘɪᴇɴᴛ.</b>\n<i>ᴜꜱᴀɢᴇ — <code>/gift &lt;item_id ᴏʀ ɴᴀᴍᴇ&gt;</code></i>", parse_mode=ParseMode.HTML)
    if target.is_bot:
        return await message.reply("🤖 <b>ʏᴏᴜ ᴄᴀɴ'ᴛ ɢɪꜰᴛ ᴀ ʙᴏᴛ.</b>")
    if target.id == message.from_user.id:
        return await message.reply("❌ <b>ᴋʜᴜᴅ ᴋᴏ ɢɪꜰᴛ ɴᴀʜɪ.</b>")
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/gift &lt;item_id ᴏʀ ɴᴀᴍᴇ&gt;</code>", parse_mode=ParseMode.HTML)

    query = message.command[1]
    col = _shop_collection()
    from database.mongo import mongo_client, users
    client = mongo_client()
    ucol = users()
    inv = db["economy_inventory"] if db is not None else None
    if col is None or client is None or ucol is None or inv is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    item = await col.find_one({"item_id": query, "enabled": True, "gift": True})
    if not item and query.isdigit():
        idx = int(query) - 1
        if idx >= 0:
            all_items = await col.find({"enabled": True, "gift": True}).sort("item_id", 1).to_list(length=100)
            if idx < len(all_items):
                item = all_items[idx]
    if not item:
        all_items = await col.find({"enabled": True, "gift": True}).to_list(length=100)
        q_lower = query.lower()
        for it in all_items:
            if str(it.get("name", "")).lower() == q_lower:
                item = it
                break
        if not item:
            for it in all_items:
                if q_lower in str(it.get("name", "")).lower():
                    item = it
                    break

    if not item:
        return await message.reply("❌ <b>ɢɪꜰᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")

    item_id = item.get("item_id")
    price = int(item.get("price", 0))
    if price <= 0:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴘʀɪᴄᴇ.</b>")

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                if int(item.get("stock", -1)) >= 0:
                    stock = await col.update_one(
                        {"item_id": item_id, "enabled": True, "gift": True, "stock": {"$gte": 1}},
                        {"$inc": {"stock": -1}},
                        session=session,
                    )
                    if stock.modified_count != 1:
                        await session.abort_transaction()
                        return await message.reply("❌ <b>ᴏᴜᴛ ᴏꜰ ꜱᴛᴏᴄᴋ.</b>")
                charged = await ucol.update_one(
                    {"_id": message.from_user.id, "coins": {"$gte": price}},
                    {"$inc": {"coins": -price}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    session=session,
                )
                if charged.modified_count != 1:
                    await session.abort_transaction()
                    return await message.reply("❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ.</b>")

                await ucol.update_one(
                    {"_id": ELARA_BOT_ID},
                    {"$inc": {"coins": price}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    upsert=True, session=session,
                )

                await inv.update_one(
                    {"user_id": target.id, "item_id": item_id},
                    {"$inc": {"quantity": 1},
                     "$set": {"name": item.get("name", item_id), "updated_at": datetime.now(timezone.utc)}},
                    upsert=True, session=session,
                )
    except Exception:
        return await message.reply("❌ <b>ɢɪꜰᴛ ꜰᴀɪʟᴇᴅ.</b>")

    custom_text = item.get("gift_text")
    sender_name = _name(message.from_user)
    item_display = str(item.get("name", item_id))

    if custom_text:
        gift_caption = (
            custom_text
            .replace("{sender}", f"<b>{_esc(sender_name)}</b>")
            .replace("{target}", _mention(target.id, _name(target)))
            .replace("{item}", f"<b>{_esc(item_display)}</b>")
        )
    else:
        gift_emojis = {
            "rose": "🌹", "flower": "🌸", "heart": "❤️", "ring": "💍",
            "crown": "👑", "star": "⭐", "diamond": "💎", "teddy": "🧸",
            "chocolate": "🍫", "cake": "🎂", "balloon": "🎈", "gift": "🎁",
            "kiss": "💋", "hug": "🫂", "love": "💖",
        }
        item_lower = item_display.lower()
        emoji = "🎁"
        for key, e in gift_emojis.items():
            if key in item_lower:
                emoji = e
                break
        gift_caption = (
            f"<b>{_esc(sender_name)}</b> ɢɪꜰᴛᴇᴅ "
            f"{emoji} <b>{_esc(item_display)}</b> "
            f"ᴛᴏ {_mention(target.id, _name(target))} 🥰"
        )

    media_file_id = item.get("media_file_id")
    media_type = item.get("media_type")

    sent = False
    try:
        if media_file_id and media_type == "animation":
            await message.reply_animation(animation=media_file_id, caption=gift_caption, parse_mode=ParseMode.HTML)
            sent = True
        elif media_file_id and media_type == "photo":
            await message.reply_photo(photo=media_file_id, caption=gift_caption, parse_mode=ParseMode.HTML)
            sent = True
        elif media_file_id and media_type == "video":
            await message.reply_video(video=media_file_id, caption=gift_caption, parse_mode=ParseMode.HTML)
            sent = True
    except Exception as e:
        print(f"[gift-media] {type(e).__name__}: {e}", flush=True)

    if not sent:
        await message.reply(gift_caption, parse_mode=ParseMode.HTML)


# ─── Set Gift Text ────────────────────────────────────────────────────────────
@app.on_message(filters.command("setgifttext", prefixes=PREFIXES))
async def economy_setgifttext(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) < 3:
        return await message.reply(
            "❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/setgifttext &lt;item_id&gt; &lt;text&gt;</code>\n\n"
            "<b>ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀꜱ:</b>\n"
            "• <code>{sender}</code> — ꜱᴇɴᴅᴇʀ ɴᴀᴍᴇ\n"
            "• <code>{target}</code> — ᴛᴀʀɢᴇᴛ ᴍᴇɴᴛɪᴏɴ\n"
            "• <code>{item}</code> — ɪᴛᴇᴍ ɴᴀᴍᴇ",
            parse_mode=ParseMode.HTML,
        )
    item_id = message.command[1]
    full = message.text or ""
    parts = full.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply("❌ <b>ᴛᴇxᴛ ʀᴇQᴜɪʀᴇᴅ.</b>")
    text = parts[2].strip()
    if not text:
        return await message.reply("❌ <b>ᴛᴇxᴛ ᴇᴍᴘᴛʏ.</b>")

    col = _shop_collection()
    if col is None:
        return await message.reply("❌ <b>ꜱʜᴏᴘ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    await col.update_one(
        {"item_id": item_id},
        {"$set": {"gift_text": text, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    await message.reply(
        f"✅ <b>ɢɪꜰᴛ ᴛᴇxᴛ ꜱᴇᴛ</b>\n\n"
        f"<blockquote>"
        f"📦 <b>ɪᴛᴇᴍ</b> — <code>{_esc(item_id)}</code>\n"
        f"✏️ <b>ᴛᴇxᴛ</b> — {_esc(text)}"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command(["cleargifttext", "resetgifttext"], prefixes=PREFIXES))
async def economy_cleargifttext(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/cleargifttext &lt;item_id&gt;</code>", parse_mode=ParseMode.HTML)
    col = _shop_collection()
    if col is None:
        return
    result = await col.update_one(
        {"item_id": message.command[1]},
        {"$unset": {"gift_text": ""}},
    )
    await message.reply("✅ <b>ɢɪꜰᴛ ᴛᴇxᴛ ʀᴇꜱᴇᴛ.</b>" if result.modified_count else "❌ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)


# ─── Owner: Shop Management ───────────────────────────────────────────────────
@app.on_message(filters.command("shopadd", prefixes=PREFIXES))
async def economy_shopadd(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) < 4:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/shopadd &lt;id&gt; &lt;price&gt; &lt;stock&gt; &lt;name&gt;</code>", parse_mode=ParseMode.HTML)
    try:
        item_id, price, stock = message.command[1], int(message.command[2]), int(message.command[3])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴘʀɪᴄᴇ/ꜱᴛᴏᴄᴋ.</b>")
    name = " ".join(message.command[4:]).strip()
    if not name:
        return await message.reply("❌ <b>ɴᴀᴍᴇ ʀᴇQᴜɪʀᴇᴅ.</b>")
    col = _shop_collection()
    now = datetime.now(timezone.utc)
    await col.update_one(
        {"item_id": item_id},
        {"$set": {"item_id": item_id, "name": name, "description": "",
                  "price": price, "stock": stock, "media_file_id": None,
                  "media_type": None, "gift": False, "enabled": True,
                  "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await message.reply(f"✅ <b>ꜱʜᴏᴘ ɪᴛᴇᴍ ꜱᴀᴠᴇᴅ</b> — <code>{_esc(item_id)}</code>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shopedit", prefixes=PREFIXES))
async def economy_shopedit(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) < 4:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/shopedit &lt;id&gt; &lt;name|description|price|stock&gt; &lt;value&gt;</code>", parse_mode=ParseMode.HTML)
    item_id, field = message.command[1], message.command[2].lower()
    if field not in {"name", "description", "price", "stock"}:
        return await message.reply("❌ <b>ᴇᴅɪᴛᴀʙʟᴇ:</b> name, description, price, stock")
    value = " ".join(message.command[3:]).strip()
    if field in {"price", "stock"}:
        try:
            value = int(value)
        except ValueError:
            return await message.reply("❌ <b>ᴘʀɪᴄᴇ/ꜱᴛᴏᴄᴋ ɪɴᴛᴇɢᴇʀ.</b>")
        if field == "price" and value < 0:
            return await message.reply("❌ <b>ɴᴇɢᴀᴛɪᴠᴇ ɴᴀʜɪ.</b>")
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": item_id},
        {"$set": {field: value, "updated_at": datetime.now(timezone.utc)}},
    )
    await message.reply("✅ <b>ɪᴛᴇᴍ ᴜᴘᴅᴀᴛᴇᴅ.</b>" if result.modified_count else "❌ <b>ɪᴛᴇᴍ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shopmedia", prefixes=PREFIXES))
async def economy_shopmedia(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ᴍᴇᴅɪᴀ ᴡɪᴛʜ</b> <code>/shopmedia &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
    reply = message.reply_to_message
    if not reply:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ᴍᴇᴅɪᴀ.</b>")
    file_id = None
    media_type = None
    if reply.animation:
        file_id, media_type = reply.animation.file_id, "animation"
    elif reply.photo:
        file_id, media_type = reply.photo.file_id, "photo"
    elif reply.video:
        file_id, media_type = reply.video.file_id, "video"
    elif reply.document:
        file_id, media_type = reply.document.file_id, "document"
    if not file_id:
        return await message.reply("❌ <b>ᴜɴꜱᴜᴘᴘᴏʀᴛᴇᴅ ᴍᴇᴅɪᴀ.</b>")
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": message.command[1]},
        {"$set": {"media_file_id": file_id, "media_type": media_type,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    await message.reply("✅ <b>ᴍᴇᴅɪᴀ ᴀᴛᴛᴀᴄʜᴇᴅ.</b>" if result.modified_count else "❌ <b>ɪᴛᴇᴍ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shopremove", prefixes=PREFIXES))
async def economy_shopremove(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/shopremove &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
    col = _shop_collection()
    result = await col.delete_one({"item_id": message.command[1]})
    await message.reply("✅ <b>ʀᴇᴍᴏᴠᴇᴅ.</b>" if result.deleted_count else "❌ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shopstock", prefixes=PREFIXES))
async def economy_shopstock(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 3:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/shopstock &lt;id&gt; &lt;stock&gt;</code>", parse_mode=ParseMode.HTML)
    try:
        stock = int(message.command[2])
    except ValueError:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ꜱᴛᴏᴄᴋ.</b>")
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": message.command[1]},
        {"$set": {"stock": stock, "updated_at": datetime.now(timezone.utc)}},
    )
    await message.reply("✅ <b>ꜱᴛᴏᴄᴋ ᴜᴘᴅᴀᴛᴇᴅ.</b>" if result.modified_count else "❌ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shoptoggle", prefixes=PREFIXES))
async def economy_shoptoggle(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 3 or message.command[2].lower() not in {"on", "off"}:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/shoptoggle &lt;id&gt; &lt;on/off&gt;</code>", parse_mode=ParseMode.HTML)
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": message.command[1]},
        {"$set": {"enabled": message.command[2].lower() == "on"}},
    )
    await message.reply("✅ <b>ᴜᴘᴅᴀᴛᴇᴅ.</b>" if result.modified_count else "❌ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shopgift", prefixes=PREFIXES))
async def economy_shopgift(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 3 or message.command[2].lower() not in {"on", "off"}:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/shopgift &lt;id&gt; &lt;on/off&gt;</code>", parse_mode=ParseMode.HTML)
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": message.command[1]},
        {"$set": {"gift": message.command[2].lower() == "on"}},
    )
    await message.reply("✅ <b>ɢɪꜰᴛ ᴍᴏᴅᴇ ᴜᴘᴅᴀᴛᴇᴅ.</b>" if result.modified_count else "❌ <b>ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)
