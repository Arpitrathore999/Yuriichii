"""Telegram handlers for the isolated economy system. (Premium UI + GC Close/Open)"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from pyrogram import filters
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
    if reply and reply.from_user and not reply.from_user.is_bot:
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


def _protection_active(user):
    until = user.get("protection_until") if user else None
    return bool(until and until > datetime.now(timezone.utc))


async def _is_owner(message):
    return bool(message.from_user and int(message.from_user.id) == OWNER_ID)


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
        "<i>ᴀʟʟ ᴇᴄᴏɴᴏᴍʏ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ɴᴏᴡ ᴅɪꜱᴀʙʟᴇᴅ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.</i>",
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
                "🔒 <b>ᴇᴄᴏɴᴏᴍʏ ɪꜱ ᴄʟᴏꜱᴇᴅ.</b>\n"
                "<i>ᴜꜱᴇ <code>/open</code> ᴛᴏ ᴇɴᴀʙʟᴇ ɪᴛ.</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


# ─── Profile ──────────────────────────────────────────────────────────────────
async def _profile_text(user):
    await ensure_user(user)
    doc = await get_user(user.id)
    coin_rank = await get_coin_rank(user.id)
    kill_rank = await get_kill_rank(user.id)

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
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/bal</code> ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ.", parse_mode=ParseMode.HTML)

    if not target or target.is_bot:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ.</b>")

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
    if not result["ok"]:
        return await message.reply({
            "self": "❌ ᴋɪʟʟ ʏᴏᴜʀꜱᴇʟꜰ ɴᴀʜɪ ᴋᴀʀ ꜱᴀᴋᴛᴇ.",
            "dead": "☠️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴀʟʀᴇᴀᴅʏ ᴅᴇᴀᴅ.",
            "target_dead": "☠️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴀʟʀᴇᴀᴅʏ ᴅᴇᴀᴅ.",
            "protected": "🛡️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴘʀᴏᴛᴇᴄᴛᴇᴅ.",
            "killer_dead": "☠️ ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ᴋɪʟʟ.",
            "robber_dead": "☠️ ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ᴋɪʟʟ.",
            "killer_unavailable": "❌ ʏᴏᴜʀ ᴋɪʟʟ ꜰᴀɪʟᴇᴅ ꜱᴀꜰᴇʟʏ.",
            "not_available": "❌ ᴛᴀʀɢᴇᴛ ᴀʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇꜱꜱᴇᴅ.",
            "transaction_unavailable": "❌ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ.",
        }.get(reason, f"❌ <b>ᴋɪʟʟ ꜰᴀɪʟᴇᴅ.</b>\n<i>ʀᴇᴀꜱᴏɴ — <code>{reason or 'unknown'}</code></i>"), parse_mode=ParseMode.HTML)

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
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user

    if not target or target.is_bot:
        return await message.reply("❌ <b>ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ.</b>")

    reviver = await get_user(message.from_user.id)
    victim_doc = await get_user(target.id)

    if reviver is None or victim_doc is None:
        return await message.reply("❌ <b>ᴇᴄᴏɴᴏᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")

    if str(victim_doc.get("status", "alive")).lower() != "dead":
        return await message.reply(f"❌ {_mention(target.id, _name(target))} ɪꜱ ɴᴏᴛ ᴅᴇᴀᴅ.")

    if str(reviver.get("status", "alive")).lower() != "alive":
        return await message.reply("☠️ <b>ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ʀᴇᴠɪᴠᴇ.</b>")

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

    result = await rob_user(message.from_user.id, target.id)
    reason = result.get("reason")
    print(f"[ROB DEBUG] {result}", flush=True)

    if not result.get("ok"):
        return await message.reply({
            "self": "❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ʀᴏʙ ʏᴏᴜʀꜱᴇʟꜰ.",
            "dead": "☠️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴅᴇᴀᴅ.",
            "target_dead": "☠️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴅᴇᴀᴅ.",
            "killer_dead": "☠️ ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ʀᴏʙ.",
            "robber_dead": "☠️ ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ ᴄᴀɴɴᴏᴛ ʀᴏʙ.",
            "protected": "🛡️ ᴛʜᴀᴛ ᴜꜱᴇʀ ɪꜱ ᴘʀᴏᴛᴇᴄᴛᴇᴅ.",
            "cooldown": "⏳ ʏᴏᴜ'ʀᴇ ʀᴏʙʙɪɴɢ ᴛᴏᴏ ꜰᴀꜱᴛ.\n<i>ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</i>",
            "insufficient": "❌ ᴛᴀʀɢᴇᴛ ʜᴀꜱ ɴᴏ ʟɪQᴜɪᴅ ᴇᴅᴏʟʟᴇʀꜱ.",
            "not_available": "❌ ᴛᴀʀɢᴇᴛ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.",
            "transaction_unavailable": "❌ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ꜰᴀɪʟᴇᴅ.",
        }.get(reason, f"❌ <b>ʀᴏʙ ꜰᴀɪʟᴇᴅ.</b>\n<i>ʀᴇᴀꜱᴏɴ — <code>{reason or 'unknown'}</code></i>"), parse_mode=ParseMode.HTML)

    if not result.get("success"):
        return await message.reply("🚨 <b>ʀᴏʙ ꜰᴀɪʟᴇᴅ!</b>\n<i>ʏᴏᴜ ɢᴏᴛ ɴᴏᴛʜɪɴɢ.</i>", parse_mode=ParseMode.HTML)

    await message.reply(
        "💸 <b>ʀᴏʙ ꜱᴜᴄᴄᴇꜱꜱ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴛᴀʀɢᴇᴛ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ꜱᴛᴏʟᴇɴ</b> — <code>{result['amount']}</code> $"
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
    if target.id == message.from_user.id:
        return await message.reply("❌ <b>ᴋʜᴜᴅ ᴋᴏ ᴄʜᴇᴄᴋ ɴᴀʜɪ.</b>")

    result = await check_user(message.from_user.id, target.id)
    if not result["ok"]:
        if result["reason"] == "insufficient":
            return await message.reply("❌ <b>ʏᴏᴜ ɴᴇᴇᴅ 500 $.</b>")
        return await message.reply("❌ <b>ᴄʜᴇᴄᴋ ꜰᴀɪʟᴇᴅ.</b>")

    doc = result["target"]
    protected = "🟢 ᴀᴄᴛɪᴠᴇ" if result["protected"] else "🔴 ɪɴᴀᴄᴛɪᴠᴇ"
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
        f"</blockquote>"
    )
    try:
        await app.send_message(message.from_user.id, details, parse_mode=ParseMode.HTML)
        if message.chat.type != ChatType.PRIVATE:
            return await message.reply("🔎 <b>ᴄʜᴇᴄᴋ ᴅᴇᴛᴀɪʟꜱ ꜱᴇɴᴛ ɪɴ ᴅᴍ.</b>")
    except Exception:
        return await message.reply("❌ <b>ᴅᴍ ɴᴀʜɪ ʙʜᴇᴊ ꜱᴀᴋᴀ.</b>")


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

    new_balance = int(user.get("coins", 0)) - SET_EMOJI_FEE
    await message.reply(
        f"{emoji} <b>ᴄᴜꜱᴛᴏᴍ ᴇᴍᴏᴊɪ ꜱᴇᴛ</b>\n\n"
        f"<blockquote>"
        f"✨ <b>ᴇᴍᴏᴊɪ</b> — {emoji}\n"
        f"💰 <b>ꜰᴇᴇ</b> — <code>{SET_EMOJI_FEE}</code> $\n"
        f"💳 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ</b> — <code>{new_balance}</code> $"
        f"</blockquote>\n"
        f"<blockquote><i>ᴜꜱᴇ <code>/bal</code> ᴛᴏ ꜱᴇᴇ ɪᴛ ɪɴ ᴀᴄᴛɪᴏɴ.</i></blockquote>",
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
    result = await users_col.update_one(
        {"_id": target.id},
        {"$inc": {"coins": amount}},
    )
    if result.modified_count != 1:
        return await message.reply("❌ <b>ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
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
        {"$inc": {"coins": -amount}},
    )
    if result.modified_count != 1:
        return await message.reply("❌ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ᴏʀ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
    await message.reply(
        f"✅ <b>ʀᴇᴍᴏᴠᴇᴅ</b>\n\n"
        f"<blockquote>"
        f"👤 <b>ᴜꜱᴇʀ</b> — {_mention(target.id, _name(target))}\n"
        f"💰 <b>ᴀᴍᴏᴜɴᴛ</b> — <code>-{amount}</code> $"
        f"</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Shop & Gifts ─────────────────────────────────────────────────────────────
def _shop_collection():
    from database.mongo import economy_shop
    return economy_shop()


@app.on_message(filters.command("shop", prefixes=PREFIXES))
async def economy_shop(_, message):
    col = _shop_collection()
    if col is None:
        return await message.reply("❌ <b>ꜱʜᴏᴘ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    rows = await col.find({"enabled": True}).sort("item_id", 1).to_list(length=100)
    if not rows:
        return await message.reply("🛒 <b>ꜱʜᴏᴘ ᴇᴍᴘᴛʏ.</b>")
    lines = ["🛒 <b>ᴇᴄᴏɴᴏᴍʏ ꜱʜᴏᴘ</b>\n"]
    for item in rows:
        stock = item.get("stock", -1)
        stock_text = "∞" if int(stock) < 0 else str(stock)
        gift = " 🎁" if item.get("gift") else ""
        lines.append(
            f"• <b>{_esc(item.get('item_id'))}</b> — {_esc(item.get('name', 'Item'))}{gift}\n"
            f"  💰 <code>{int(item.get('price', 0))}</code> $  |  📦 <code>{stock_text}</code>\n"
            f"  <i>{_esc(item.get('description', ''))}</i>"
        )
    await message.reply("\n\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command("buy", prefixes=PREFIXES))
async def economy_buy(_, message):
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/buy &lt;item_id&gt;</code>", parse_mode=ParseMode.HTML)
    await _ensure_from_message(message)
    item_id = message.command[1]
    col = _shop_collection()
    if col is None:
        return await message.reply("❌ <b>ꜱʜᴏᴘ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    item = await col.find_one({"item_id": item_id, "enabled": True})
    if not item:
        return await message.reply("❌ <b>ɪᴛᴇᴍ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
    if int(item.get("stock", -1)) == 0:
        return await message.reply("❌ <b>ᴏᴜᴛ ᴏꜰ ꜱᴛᴏᴄᴋ.</b>")
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


@app.on_message(filters.command("gift", prefixes=PREFIXES))
async def economy_gift(_, message):
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ <b>ʀᴇᴘʟʏ ᴛᴏ ʀᴇᴄɪᴘɪᴇɴᴛ.</b>\n<i>ᴜꜱᴀɢᴇ — <code>/gift &lt;item_id&gt;</code></i>", parse_mode=ParseMode.HTML)
    if target.id == message.from_user.id:
        return await message.reply("❌ <b>ᴋʜᴜᴅ ᴋᴏ ɢɪꜰᴛ ɴᴀʜɪ.</b>")
    if len(message.command or []) != 2:
        return await message.reply("❌ <b>ᴜꜱᴀɢᴇ:</b> <code>/gift &lt;item_id&gt;</code>", parse_mode=ParseMode.HTML)
    item_id = message.command[1]
    col = _shop_collection()
    from database.mongo import mongo_client, users
    client = mongo_client()
    ucol = users()
    inv = db["economy_inventory"] if db is not None else None
    if col is None or client is None or ucol is None or inv is None:
        return await message.reply("❌ <b>ᴅᴀᴛᴀʙᴀꜱᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</b>")
    item = await col.find_one({"item_id": item_id, "enabled": True, "gift": True})
    if not item:
        return await message.reply("❌ <b>ɢɪꜰᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>")
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
                await inv.update_one(
                    {"user_id": target.id, "item_id": item_id},
                    {"$inc": {"quantity": 1},
                     "$set": {"name": item.get("name", item_id), "updated_at": datetime.now(timezone.utc)}},
                    upsert=True, session=session,
                )
        return await message.reply(
            f"🎁 <b>ɢɪꜰᴛ ꜱᴇɴᴛ</b>\n\n"
            f"<blockquote>"
            f"🎁 <b>ɪᴛᴇᴍ</b> — <code>{_esc(item.get('name', item_id))}</code>\n"
            f"👤 <b>ᴛᴏ</b> — {_mention(target.id, _name(target))}\n"
            f"💰 <b>ᴘᴀɪᴅ</b> — <code>{price}</code> $"
            f"</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        return await message.reply("❌ <b>ɢɪꜰᴛ ꜰᴀɪʟᴇᴅ.</b>")


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
