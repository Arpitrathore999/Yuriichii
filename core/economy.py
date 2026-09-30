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
DAILY_REWARD_MAX = 3000

KILL_REWARD_MIN = 300
KILL_REWARD_MAX = 500
KILL_XP_MIN = 20
KILL_XP_MAX = 50

WALLET_MAX_PERCENT = 0.30

# Rob mechanics are intentionally centralized/configurable.
ROB_SUCCESS_CHANCE = 0.55
ROB_MIN_PERCENT = 0.10
ROB_MAX_PERCENT = 0.30
ROB_MIN_TARGET_BALANCE = 100
ROB_COOLDOWN_SECONDS = 60

CHECK_COST = 500


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
    """Maximum wallet based on liquid coins + current wallet."""
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
        {
            "_id": int(user_id),
            "$or": [
                {"daily_last_claim": {"$exists": False}},
                {"daily_last_claim": {"$ne": today}},
            ],
        },
        {
            "$inc": {"coins": reward},
            "$set": {"daily_last_claim": today, "updated_at": now_utc()},
        },
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

    killer = await get_user(killer_id)
    target = await get_user(target_id)
    if not killer or not target:
        return {"ok": False, "reason": "user"}
    if target.get("status", "alive") == "dead":
        return {"ok": False, "reason": "dead"}
    if killer.get("status", "alive") == "dead":
        return {"ok": False, "reason": "killer_dead"}

    until = target.get("protection_until")
    if until and until > now_utc():
        return {"ok": False, "reason": "protected", "until": until}

    reward = random.randint(KILL_REWARD_MIN, KILL_REWARD_MAX)
    xp_reward = random.randint(KILL_XP_MIN, KILL_XP_MAX)
    client = mongo_client()
    col = users_collection()
    if client is None or col is None:
        return {"ok": False, "reason": "database"}

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                # Conditional target update prevents two simultaneous killers
                # from both receiving a successful kill.
                result = await col.update_one(
                    {
                        "_id": int(target_id),
                        "status": "alive",
                        "$or": [
                            {"protection_until": None},
                            {"protection_until": {"$lte": now_utc()}},
                            {"protection_until": {"$exists": False}},
                        ],
                    },
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


async def rob_user(robber_id: int, target_id: int):
    if robber_id == target_id:
        return {"ok": False, "reason": "self"}

    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}

    robber = await get_user(robber_id)
    target = await get_user(target_id)
    if not robber or not target:
        return {"ok": False, "reason": "user"}
    if robber.get("status", "alive") == "dead":
        return {"ok": False, "reason": "robber_dead"}
    if target.get("status", "alive") == "dead":
        return {"ok": False, "reason": "target_dead"}

    until = target.get("protection_until")
    if until and until > now_utc():
        return {"ok": False, "reason": "protected", "until": until}

    target_coins = int(target.get("coins", 0))
    if target_coins < ROB_MIN_TARGET_BALANCE:
        return {"ok": False, "reason": "insufficient"}

    last = robber.get("rob_last_attempt")
    cutoff = now_utc() - timedelta(seconds=ROB_COOLDOWN_SECONDS)
    if last and last > cutoff:
        return {"ok": False, "reason": "cooldown", "until": last + timedelta(seconds=ROB_COOLDOWN_SECONDS)}

    # Reserve the robber's cooldown atomically.
    reserved = await col.update_one(
        {
            "_id": int(robber_id),
            "$or": [
                {"rob_last_attempt": {"$exists": False}},
                {"rob_last_attempt": {"$lte": cutoff}},
            ],
        },
        {"$set": {"rob_last_attempt": now_utc(), "updated_at": now_utc()}},
    )
    if reserved.modified_count != 1:
        return {"ok": False, "reason": "cooldown"}

    if random.random() > ROB_SUCCESS_CHANCE:
        return {"ok": True, "success": False, "amount": 0}

    amount = max(1, int(target_coins * random.uniform(ROB_MIN_PERCENT, ROB_MAX_PERCENT)))

    client = mongo_client()
    if client is None:
        return {"ok": False, "reason": "database"}

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                stolen = await col.update_one(
                    {
                        "_id": int(target_id),
                        "coins": {"$gte": amount},
                        "status": "alive",
                        "$or": [
                            {"protection_until": None},
                            {"protection_until": {"$lte": now_utc()}},
                            {"protection_until": {"$exists": False}},
                        ],
                    },
                    {"$inc": {"coins": -amount}, "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                if stolen.modified_count != 1:
                    await session.abort_transaction()
                    return {"ok": False, "reason": "not_available"}

                await col.update_one(
                    {"_id": int(robber_id)},
                    {"$inc": {"coins": amount}, "$set": {"updated_at": now_utc()}},
                    session=session,
                )
                await log_transaction(robber_id, "rob_received", amount,
                                      meta={"target": target_id}, session=session)
                await log_transaction(target_id, "robbed", -amount,
                                      meta={"by": robber_id}, session=session)
        return {"ok": True, "success": True, "amount": amount}
    except Exception as exc:
        return {"ok": False, "reason": "transaction_unavailable", "error": str(exc)}


async def protect_user(user_id: int):
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}

    until = now_utc() + PROTECTION_DURATION
    result = await col.update_one(
        {
            "_id": int(user_id),
            "coins": {"$gte": PROTECTION_COST},
            "$or": [
                {"protection_until": None},
                {"protection_until": {"$lte": now_utc()}},
                {"protection_until": {"$exists": False}},
            ],
        },
        {
            "$inc": {"coins": -PROTECTION_COST},
            "$set": {"protection_until": until, "updated_at": now_utc()},
        },
    )
    if result.modified_count != 1:
        user = await get_user(user_id)
        if user and user.get("protection_until") and user["protection_until"] > now_utc():
            return {"ok": False, "reason": "already_protected", "until": user["protection_until"]}
        return {"ok": False, "reason": "insufficient"}

    await log_transaction(user_id, "protection", -PROTECTION_COST,
                          meta={"until": until.isoformat()})
    return {"ok": True, "until": until}


async def check_user(requester_id: int, target_id: int):
    if requester_id == target_id:
        return {"ok": False, "reason": "self"}

    target = await get_user(target_id)
    if not target:
        return {"ok": False, "reason": "user"}

    # Validate target before charging.
    col = users_collection()
    if col is None:
        return {"ok": False, "reason": "database"}

    charged = await col.update_one(
        {"_id": int(requester_id), "coins": {"$gte": CHECK_COST}},
        {"$inc": {"coins": -CHECK_COST}, "$set": {"updated_at": now_utc()}},
    )
    if charged.modified_count != 1:
        return {"ok": False, "reason": "insufficient"}

    protection = target.get("protection_until")
    active = bool(protection and protection > now_utc())
    await log_transaction(requester_id, "check", -CHECK_COST,
                          meta={"target": target_id})
    return {
        "ok": True,
        "target": target,
        "protected": active,
        "protection_until": protection if active else None,
    }
