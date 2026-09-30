"""Business logic for the Telegram economy system.

This module intentionally contains no Pyrogram handlers. Games may call these
functions, but social commands do not modify economy state.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import config
from database.mongo import users as users_collection, mongo_client, db
from .database import (
    ensure_user,
    get_user,
    add_coins,
    remove_coins,
    add_xp,
    log_transaction,
)

TAX_RATE = 0.10
PROTECTION_COST = 500
PROTECTION_DURATION = timedelta(days=1)

DAILY_REWARD_MIN = 2000
DAILY_REWARD_MAX = 2000

KILL_REWARD_MIN = 300
KILL_REWARD_MAX = 500
KILL_XP_MIN = 20
KILL_XP_MAX = 50

WALLET_MAX_PERCENT = 0.30

ROB_SUCCESS_CHANCE = 1.0
ROB_MIN_PERCENT = 0.10
ROB_MAX_PERCENT = 0.30
ROB_MIN_TARGET_BALANCE = 100
ROB_COOLDOWN_SECONDS = 60

CHECK_COST = 500

# ─── Elara Constants ──────────────────────────────────────────────────────────
ELARA_BOT_ID = 8899359004
OWNER_ID = int(getattr(config, "OWNER_ID", 0) or 0)


# ─── Rob Roast Messages ───────────────────────────────────────────────────────
ELARA_ROASTS = [
    "ᴀʀʀᴇ ʙʜᴀɪ, ᴀᴘɴᴀ ʜɪ ʙᴀʟᴀɴᴄᴇ ᴅᴇᴋʜ ʟᴇ ᴘᴇʜʟᴇ 😭",
    "ᴛᴜ ᴍᴜᴊʜᴇ ʀᴏʙ ᴋᴀʀᴇɢᴀ? ꜱᴀᴘɴᴇ ᴍᴇ ʙʜɪ ɴᴀʜɪ 💀",
    "ɪᴛɴɪ ʜɪᴍᴍᴀᴛ ᴋɪꜱ ᴋᴀᴀᴍ ᴋɪ, ᴊᴀʙ ʙᴀʟᴀɴᴄᴇ ʜɪ ᴢᴇʀᴏ ʜᴀɪ 🥱",
    "ʀᴏʙʙɪɴɢ ᴍᴇ ᴇxᴘᴇʀᴛ ʙᴀɴ ɢᴀʏᴀ, ᴘᴀʀ ᴀᴍᴇᴇʀ ɴᴀʜɪ 🤡",
    "ᴍᴇʀᴀ ᴡᴀʟʟᴇᴛ ᴛᴇʀᴇ ʜᴀᴀᴛʜ ɴᴀʜɪ ᴀᴀᴛᴀ 💅",
    "ᴛᴜ ʀᴏʙ ᴋᴀʀ, ᴍᴀɪ ᴛᴇʀᴀ ꜰᴜᴛᴜʀᴇ ʀᴏʙ ᴋᴀʀ ʟᴜɴɢᴀ 😏",
    "ʙᴇᴛᴀ, ᴘᴇʜʟᴇ ᴋʜᴜᴅ ᴋᴏ ʀᴇᴠɪᴠᴇ ᴋᴀʀ ʟᴇ 💀",
    "ɪꜱᴋɪ ᴀᴜᴋᴀᴀᴛ ɴᴀʜɪ ʜᴀɪ ᴍᴇʀᴇ ᴘᴀɪꜱᴇ ᴋɪ 😎",
    "ᴛᴇʀᴇ ᴊᴀɪꜱᴇ 100 ᴀᴀʏᴇ, 100 ɢᴀʏᴇ 🚶",
    "ʀᴏʙʙɪɴɢ ꜱᴋɪʟʟ ᴀᴄʜʜɪ ʜᴀɪ, ᴘᴀʀ ʟᴜᴄᴋ ᴋʜᴀʀᴀʙ ʜᴀɪ 🎭",
    "ɴɪᴄᴇ ᴛʀʏ, ʙᴜᴛ ɪ ᴅᴏɴ'ᴛ ɢᴇᴛ ʀᴏʙʙᴇᴅ 😏",
    "ʙʀᴏ ʀᴇᴀʟʟʏ ᴛʜᴏᴜɢʜᴛ ʜᴇ ᴄᴏᴜʟᴅ ʀᴏʙ ᴍᴇ 💀",
    "ᴛʜᴀᴛ ᴡᴀꜱ ᴄᴜᴛᴇ. ᴛʀʏ ᴀɢᴀɪɴ ɴᴇᴠᴇʀ 💅",
    "ʏᴏᴜ ᴄᴀɴ'ᴛ ᴀꜰꜰᴏʀᴅ ᴍᴇ, ʟᴇᴛ ᴀʟᴏɴᴇ ʀᴏʙ ᴍᴇ 💰",
    "ᴍᴏɴᴇʏ ᴅᴏᴇꜱɴ'ᴛ ɢʀᴏᴡ ᴏɴ ᴛʀᴇᴇꜱ. ᴀɴᴅ ᴅᴇꜰɪɴɪᴛᴇʟʏ ɴᴏᴛ ꜰʀᴏᴍ ᴍᴇ 🌳🚫",
    "ʀᴏʙʙᴇᴅ ᴍᴇ? ɴᴀʜ, ʏᴏᴜ ʀᴏʙʙᴇᴅ ʏᴏᴜʀꜱᴇʟꜰ ᴏꜰ ᴅɪɢɴɪᴛʏ 🤡",
    "ʟ + ʀᴀᴛɪᴏ + ɴᴏ ᴇᴅᴏʟʟᴇʀꜱ 🥱",
    "ꜱᴋɪʟʟ ɪꜱꜱᴜᴇ, ᴍʏ ꜰʀɪᴇɴᴅ 💀",
    "ᴇᴠᴇɴ ᴍʏ ꜱʜᴀᴅᴏᴡ ʜᴀꜱ ᴍᴏʀᴇ ᴍᴏɴᴇʏ ᴛʜᴀɴ ʏᴏᴜ 😭",
    "ᴛᴏᴜᴄʜ ꜱᴏᴍᴇ ɢʀᴀꜱꜱ, ɴᴏᴛ ᴍʏ ᴡᴀʟʟᴇᴛ 🌱🚫",
    "ꜱᴋɪʟʟ: 0 | ᴄᴏɴꜰɪᴅᴇɴᴄᴇ: 100 | ʀᴇꜱᴜʟᴛ: ꜰᴀɪʟᴇᴅ 💀",
    "ʏᴏᴜ ᴠꜱ ᴍᴇ = ʏᴏᴜ ʟᴏꜱᴇ, ᴀʟᴡᴀʏꜱ 💪",
    "ʙʜᴀɪ ᴛᴜ ʀᴏʙʙɪɴɢ ᴄʜʜᴏᴅ, ᴄᴏᴅɪɴɢ ꜱᴇᴇᴋʜ ʟᴇ 🤡",
    "ʀᴏʙʙɪɴɢ ᴀ ʙᴏᴛ? ᴛʜᴀᴛ'ꜱ ᴀ ɴᴇᴡ ʟᴇᴠᴇʟ ᴏꜰ ᴅᴇꜱᴘᴇʀᴀᴛᴇ 🥴",
    "ᴄᴏɴɢʀᴀᴛꜱ! ʏᴏᴜ ᴊᴜꜱᴛ ᴜɴʟᴏᴄᴋᴇᴅ: 'ᴄʟᴏᴡɴ ᴏꜰ ᴛʜᴇ ᴅᴀʏ' 🤡",
    "ᴛʀʏ ᴀɢᴀɪɴ... ᴏʀ ᴅᴏɴ'ᴛ. ᴘʟᴇᴀꜱᴇ ᴅᴏɴ'ᴛ. 💅",
    "ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴇᴅᴏʟʟᴇʀꜱ. ɪ ʜᴀᴠᴇ ꜱᴛᴀɴᴅᴀʀᴅꜱ 😎",
    "ʀᴏʙʙɪɴɢ ᴀ ʙᴏᴛ ɪꜱ ʟɪᴋᴇ ꜰɪɢʜᴛɪɴɢ ᴀ ᴍɪʀʀᴏʀ. ʏᴏᴜ ʟᴏꜱᴇ ᴇɪᴛʜᴇʀ ᴡᴀʏ 🪞",
    "ʙʜᴀɪ ɪᴛɴᴀ ᴛɪᴍᴇ ᴛʜᴀ ᴛᴏʜ ᴘᴀᴅʜᴀɪ ᴋᴀʀ ʟᴇᴛᴀ 📚",
    "ɴᴇxᴛ ᴛɪᴍᴇ ʙʀɪɴɢ ᴀ ʟᴀᴅᴅᴇʀ, ʏᴏᴜ'ʀᴇ ᴛᴏᴏ ꜱʜᴏʀᴛ ᴛᴏ ʀᴇᴀᴄʜ ᴍʏ ᴡᴀʟʟᴇᴛ 🪜😏",
]


# ─── Kill Roast Messages ──────────────────────────────────────────────────────
ELARA_KILL_ROASTS = [
    "ᴛᴜ ᴍᴜᴊʜᴇ ᴋɪʟʟ ᴋᴀʀᴇɢᴀ? ᴍᴀɪ ᴛᴏ ᴛᴇʀᴇ ꜱᴀᴘɴᴏ ᴍᴇ ʙʜɪ ᴢɪɴᴅᴀ ʜᴏᴏɴ 💀",
    "ᴋɪʟʟ ᴋᴀʀɴᴇ ꜱᴇ ᴘᴇʜʟᴇ ᴛᴜ ᴋʜᴜᴅ ᴋᴏ ᴋɪʟʟ ᴋᴀʀ ʟᴇ 🤡",
    "ɪ ᴀᴍ ɪᴍᴍᴏʀᴛᴀʟ, ʙʀᴏ. ɴɪᴄᴇ ᴛʀʏ ᴛʜᴏᴜɢʜ 😏",
    "ᴛᴇʀᴀ ᴋɪʟʟ ꜱᴋɪʟʟ ʟᴇᴠᴇʟ: ɴᴇɢᴀᴛɪᴠᴇ 📉",
    "ᴍᴜᴊʜᴇ ᴋɪʟʟ ᴋᴀʀɴᴇ ᴋɪ 괜ᴋᴀᴛ ɴᴀʜɪ ʜᴀɪ ᴛᴇʀɪ 🥱",
    "ᴡᴏᴡ, ʏᴏᴜ ᴛʀɪᴇᴅ ᴛᴏ ᴋɪʟʟ ᴀ ʙᴏᴛ. ʙʀᴀɪɴ ᴇɴɢᴀɢᴇᴅ? 🧠❌",
    "ᴛᴇʀᴇ ʜᴀᴀᴛʜ ɴᴀʜɪ ʟᴀɢᴇɢᴀ ᴍᴇʀᴇ ʜᴀᴛʜ 🚫",
    "ʟ + ʀᴀᴛɪᴏ + ɴᴏ ᴋɪʟʟ ꜰᴏʀ ʏᴏᴜ 💀",
    "ꜱᴋɪʟʟ ɪꜱꜱᴜᴇ, ᴄᴀɴ'ᴛ ᴋɪʟʟ ᴛʜᴇ ᴜɴᴋɪʟʟᴀʙʟᴇ 💪",
    "ᴛᴜ ᴛᴏ ꜱᴀᴘɴᴇ ᴍᴇ ʙʜɪ ᴋɪʟʟ ɴᴀʜɪ ᴋᴀʀ ꜱᴀᴋᴛᴀ ᴍᴜᴊʜᴇ 😴",
    "ᴍᴇʀᴀ ʜᴇᴀʟᴛʜ ᴘᴏɪɴᴛ: ∞ | ᴛᴇʀᴀ ᴅᴀᴍᴀɢᴇ: 0 📊",
    "ᴀᴛᴛᴇᴍᴘᴛ ꜰᴀɪʟᴇᴅ. ᴛʀʏ ɢᴇᴛᴛɪɴɢ ᴀ ʟɪꜰᴇ 🎮",
    "ʙʜᴀɪ ᴋɪʟʟ ᴋʀɴᴇ ꜱᴇ ᴘᴇʜʟᴇ ʀᴇᴠɪᴠᴇ ᴋᴀʀ ʟᴇᴛᴀ ᴋʜᴜᴅ ᴋᴏ 💀",
    "ɪ ᴀᴍ ᴛʜᴇ ʙᴏᴛ, ʏᴏᴜ ᴀʀᴇ ᴛʜᴇ ᴊᴏᴋᴇ 🤡",
    "ᴄᴏɴɢʀᴀᴛꜱ! ʏᴏᴜ ᴊᴜꜱᴛ ᴛʀɪᴇᴅ ᴋɪʟʟɪɴɢ ᴛʜᴇ ᴜɴᴋɪʟʟᴀʙʟᴇ 😂",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_protected(target: dict) -> bool:
    """Safe protection check — handles both naive and aware datetimes from MongoDB."""
    until = target.get("protection_until")
    if not until:
        return False
    if isinstance(until, datetime):
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        try:
            return until > now_utc()
        except Exception:
            return False
    return False


def economy_timezone():
    name = getattr(config, "ECONOMY_TZ", "Asia/Kolkata") or "Asia/Kolkata"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def tax_for(amount: int) -> int:
    amount = int(amount)
    return max(0, int(amount * TAX_RATE))


def net_after_tax(amount: int) -> int:
    amount = int(amount)
    return amount - tax_for(amount)


def wallet_limit(coins: int) -> int:
    return int(max(0, coins) / (1 - WALLET_MAX_PERCENT))


async def deposit_wallet(user_id: int, amount: int):
    if amount <= 0:
        return {"ok": False, "reason": "invalid_amount"}
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}
    user = await col.find_one({"_id": int(user_id)})
    if not user:
        return {"ok": False, "reason": "user"}
    coins = int(user.get("coins", 0))
    wallet = int(user.get("wallet", 0))
    maximum = int((coins + wallet) * WALLET_MAX_PERCENT)
    if wallet + amount > maximum:
        return {"ok": False, "reason": "wallet_limit", "maximum": maximum, "wallet": wallet}
    result = await col.update_one(
        {"_id": int(user_id), "coins": {"$gte": amount}, "wallet": {"$gte": 0}},
        {"$inc": {"coins": -amount, "wallet": amount}, "$set": {"updated_at": now_utc()}},
    )
    if result.modified_count != 1:
        return {"ok": False, "reason": "insufficient"}
    await log_transaction(user_id, "wallet_deposit", amount,
                           balance_before=coins, balance_after=coins - amount)
    return {"ok": True, "amount": amount, "wallet": wallet + amount, "coins": coins - amount}


async def withdraw_wallet(user_id: int, amount: int):
    if amount <= 0:
        return {"ok": False, "reason": "invalid_amount"}
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}
    user = await col.find_one({"_id": int(user_id)})
    if not user:
        return {"ok": False, "reason": "user"}
    coins = int(user.get("coins", 0))
    wallet = int(user.get("wallet", 0))
    if wallet < amount:
        return {"ok": False, "reason": "insufficient"}
    result = await col.update_one(
        {"_id": int(user_id), "wallet": {"$gte": amount}},
        {"$inc": {"coins": amount, "wallet": -amount}, "$set": {"updated_at": now_utc()}},
    )
    if result.modified_count != 1:
        return {"ok": False, "reason": "insufficient"}
    await log_transaction(user_id, "wallet_withdraw", amount,
                           balance_before=coins, balance_after=coins + amount)
    return {"ok": True, "amount": amount, "wallet": wallet - amount, "coins": coins + amount}


async def transfer(sender_id: int, recipient_id: int, amount: int):
    if amount <= 0:
        return {"ok": False, "reason": "invalid_amount"}
    if sender_id == recipient_id:
        return {"ok": False, "reason": "self"}
    sender = await get_user(sender_id)
    recipient = await get_user(recipient_id)
    if not sender or not recipient:
        return {"ok": False, "reason": "user"}
    if int(recipient_id) <= 0:
        return {"ok": False, "reason": "user"}
    client = mongo_client()
    col = users_collection()
    if client is None or col is None:
        return {"ok": False, "reason": "database"}
    tax = tax_for(amount)
    net = amount - tax
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                result = await col.update_one(
                    {"_id": int(sender_id), "coins": {"$gte": amount}},
                    {"$inc": {"coins": -amount}, "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                if result.modified_count != 1:
                    await session.abort_transaction()
                    return {"ok": False, "reason": "insufficient"}
                await col.update_one(
                    {"_id": int(recipient_id)},
                    {"$inc": {"coins": net}, "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                if tax > 0:
                    await col.update_one(
                        {"_id": ELARA_BOT_ID},
                        {"$inc": {"coins": tax}, "$set": {"updated_at": now_utc()}},
                        upsert=True, session=session,
                    )
                await log_transaction(sender_id, "transfer_sent", -amount,
                                      balance_before=int(sender.get("coins", 0)),
                                      balance_after=int(sender.get("coins", 0)) - amount,
                                      meta={"to": recipient_id, "tax": tax},
                                      session=session)
                await log_transaction(recipient_id, "transfer_received", net,
                                      meta={"from": sender_id, "gross": amount, "tax": tax},
                                      session=session)
        return {"ok": True, "gross": amount, "tax": tax, "net": net}
    except Exception as exc:
        return {"ok": False, "reason": "transaction_unavailable", "error": str(exc)}


async def claim_daily(user_id: int):
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}
    tz = economy_timezone()
    today = datetime.now(tz).date().isoformat()
    reward = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
    result = await col.update_one(
        {"_id": int(user_id),
         "$or": [
             {"daily_last_claim": {"$exists": False}},
             {"daily_last_claim": {"$ne": today}},
         ]},
        {"$inc": {"coins": reward},
         "$set": {"daily_last_claim": today, "updated_at": now_utc()}},
    )
    if result.modified_count != 1:
        return {"ok": False, "reason": "already_claimed", "date": today}
    await log_transaction(user_id, "daily", reward)
    user = await get_user(user_id)
    return {"ok": True, "reward": reward, "balance": int(user.get("coins", 0))}


async def kill_user(killer_id: int, target_id: int):
    if killer_id == target_id:
        return {"ok": False, "reason": "self"}
    if killer_id <= 0 or target_id <= 0:
        return {"ok": False, "reason": "invalid"}
    if int(target_id) == ELARA_BOT_ID:
        return {"ok": False, "reason": "elara_kill_roast",
                "roast": random.choice(ELARA_KILL_ROASTS)}
    killer = await get_user(killer_id)
    target = await get_user(target_id)
    if not killer or not target:
        return {"ok": False, "reason": "user"}
    if target.get("status", "alive") == "dead":
        return {"ok": False, "reason": "dead"}
    if killer.get("status", "alive") == "dead":
        return {"ok": False, "reason": "killer_dead"}

    # ✅ Safe protection check
    if _is_protected(target):
        return {"ok": False, "reason": "protected"}

    reward = random.randint(KILL_REWARD_MIN, KILL_REWARD_MAX)
    xp_reward = random.randint(KILL_XP_MIN, KILL_XP_MAX)
    client = mongo_client()
    col = users_collection()
    if client is None or col is None:
        return {"ok": False, "reason": "database"}
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                result = await col.update_one(
                    {"_id": int(target_id), "status": "alive"},
                    {"$set": {"status": "dead", "updated_at": now_utc()}},
                    session=session,
                )
                if result.modified_count != 1:
                    await session.abort_transaction()
                    return {"ok": False, "reason": "not_available"}
                killer_update = await col.update_one(
                    {"_id": int(killer_id), "status": "alive"},
                    {"$inc": {"kills": 1, "coins": reward},
                     "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                if killer_update.modified_count != 1:
                    await session.abort_transaction()
                    return {"ok": False, "reason": "killer_unavailable"}
                xp = await add_xp(killer_id, xp_reward, session=session)
                await log_transaction(killer_id, "kill_reward", reward,
                                      meta={"target": target_id}, session=session)
        return {"ok": True, "coins": reward, "xp": xp_reward, "level": xp}
    except Exception as exc:
        return {"ok": False, "reason": "transaction_unavailable", "error": str(exc)}


async def rob_user(robber_id: int, target_id: int, requested_amount: int = None):
    if robber_id == target_id:
        return {"ok": False, "reason": "self"}
    if int(target_id) == ELARA_BOT_ID:
        if int(robber_id) == OWNER_ID:
            pass
        else:
            return {"ok": False, "reason": "elara_roast",
                    "roast": random.choice(ELARA_ROASTS)}
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}
    robber = await get_user(robber_id)
    target = await get_user(target_id)
    if not robber or not target:
        return {"ok": False, "reason": "user"}

    # ✅ Safe protection check
    if _is_protected(target):
        return {"ok": False, "reason": "protected"}

    target_coins = int(target.get("coins", 0))
    if target_coins < ROB_MIN_TARGET_BALANCE:
        return {"ok": False, "reason": "insufficient"}

    last = robber.get("rob_last_attempt")
    cutoff = now_utc() - timedelta(seconds=ROB_COOLDOWN_SECONDS)
    if last:
        if isinstance(last, datetime) and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        try:
            if last > cutoff:
                return {"ok": False, "reason": "cooldown",
                        "until": last + timedelta(seconds=ROB_COOLDOWN_SECONDS)}
        except Exception:
            pass

    reserved = await col.update_one(
        {"_id": int(robber_id),
         "$or": [
             {"rob_last_attempt": {"$exists": False}},
             {"rob_last_attempt": {"$lte": cutoff}},
         ]},
        {"$set": {"rob_last_attempt": now_utc(), "updated_at": now_utc()}},
    )
    if reserved.modified_count != 1:
        return {"ok": False, "reason": "cooldown"}

    if requested_amount and requested_amount > 0:
        amount = min(requested_amount, target_coins)
    else:
        amount = max(1, int(target_coins * random.uniform(ROB_MIN_PERCENT, ROB_MAX_PERCENT)))

    tax = tax_for(amount)
    net = amount - tax
    client = mongo_client()
    if client is None:
        return {"ok": False, "reason": "database"}
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                stolen = await col.update_one(
                    {"_id": int(target_id), "coins": {"$gte": amount}},
                    {"$inc": {"coins": -amount}, "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                if stolen.modified_count != 1:
                    await session.abort_transaction()
                    return {"ok": False, "reason": "not_available"}
                await col.update_one(
                    {"_id": int(robber_id)},
                    {"$inc": {"coins": net}, "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                if tax > 0:
                    await col.update_one(
                        {"_id": ELARA_BOT_ID},
                        {"$inc": {"coins": tax}, "$set": {"updated_at": now_utc()}},
                        upsert=True, session=session,
                    )
                await log_transaction(robber_id, "rob_received", net,
                                      meta={"target": target_id, "gross": amount, "tax": tax},
                                      session=session)
                await log_transaction(target_id, "robbed", -amount,
                                      meta={"by": robber_id}, session=session)
        return {"ok": True, "success": True, "amount": net, "gross": amount, "tax": tax}
    except Exception as exc:
        return {"ok": False, "reason": "transaction_unavailable", "error": str(exc)}


async def protect_user(user_id: int):
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}
    user = await get_user(user_id)
    if user and _is_protected(user):
        return {"ok": False, "reason": "already_protected"}

    until = now_utc() + PROTECTION_DURATION
    result = await col.update_one(
        {"_id": int(user_id), "coins": {"$gte": PROTECTION_COST}},
        {"$inc": {"coins": -PROTECTION_COST},
         "$set": {"protection_until": until, "updated_at": now_utc()}},
    )
    if result.modified_count != 1:
        return {"ok": False, "reason": "insufficient"}
    await col.update_one(
        {"_id": ELARA_BOT_ID},
        {"$inc": {"coins": PROTECTION_COST}, "$set": {"updated_at": now_utc()}},
        upsert=True,
    )
    await log_transaction(user_id, "protection", -PROTECTION_COST,
                          meta={"until": until.isoformat()})
    return {"ok": True, "until": until}


async def check_user(requester_id: int, target_id: int):
    if requester_id == target_id:
        return {"ok": False, "reason": "self"}
    target = await get_user(target_id)
    if not target:
        return {"ok": False, "reason": "user"}
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}
    charged = await col.update_one(
        {"_id": int(requester_id), "coins": {"$gte": CHECK_COST}},
        {"$inc": {"coins": -CHECK_COST}, "$set": {"updated_at": now_utc()}},
    )
    if charged.modified_count != 1:
        return {"ok": False, "reason": "insufficient"}
    await col.update_one(
        {"_id": ELARA_BOT_ID},
        {"$inc": {"coins": CHECK_COST}, "$set": {"updated_at": now_utc()}},
        upsert=True,
    )

    # ✅ Protection details with expire time
    until = target.get("protection_until")
    active = _is_protected(target)

    if until and isinstance(until, datetime) and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)

    remaining_seconds = 0
    if active and until:
        try:
            remaining_seconds = max(0, int((until - now_utc()).total_seconds()))
        except Exception:
            remaining_seconds = 0

    await log_transaction(requester_id, "check", -CHECK_COST,
                          meta={"target": target_id})
    return {
        "ok": True,
        "target": target,
        "protected": active,
        "protection_until": until if active else None,
        "protection_remaining": remaining_seconds,
    }
