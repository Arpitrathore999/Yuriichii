"""Economy database layer.

All MongoDB-specific economy persistence lives here. Existing user fields are
never overwritten when economy data is initialized.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from database.mongo import users as users_collection, db

ECONOMY_DEFAULTS = {
    "coins": 0,
    "gems": 0,
    "wallet": 0,
    "xp": 0,
    "level": 1,
    "kills": 0,
    "status": "alive",
    "protection_until": None,
    "daily_last_claim": None,
    "custom_emoji": "👤",
    "created_at": None,
    "updated_at": None,
}


def xp_needed(level: int) -> int:
    """Return the XP required for the given level."""
    return max(1, int(level)) * 1000


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_user(user: Any):
    """Create/backfill economy fields without overwriting existing values."""
    col = users_collection()
    if col is None or not user:
        return None

    uid = int(user.id)
    now = _now()

    await col.update_one(
        {"_id": uid},
        {
            "$setOnInsert": {
                "_id": uid,
                "joined_at": now,
                "user_id": uid,
                "warnings": 0,
                "banned": False,
            },
            "$set": {
                "username": getattr(user, "username", None) or "",
                "first_name": getattr(user, "first_name", None) or "",
                "last_seen": now,
            },
        },
        upsert=True,
    )

    # Pipeline keeps existing economy values intact while filling fields that
    # were not present in older user documents.
    await col.update_one(
        {"_id": uid},
        [
            {
                "$set": {
                    "user_id": {"$ifNull": ["$user_id", "$_id"]},
                    "coins": {"$ifNull": ["$coins", 0]},
                    "gems": {"$ifNull": ["$gems", 0]},
                    "wallet": {"$ifNull": ["$wallet", 0]},
                    "xp": {"$ifNull": ["$xp", 0]},
                    "level": {"$ifNull": ["$level", 1]},
                    "kills": {"$ifNull": ["$kills", 0]},
                    "status": {"$ifNull": ["$status", "alive"]},
                    "protection_until": {"$ifNull": ["$protection_until", None]},
                    "daily_last_claim": {"$ifNull": ["$daily_last_claim", None]},
                    "custom_emoji": {"$ifNull": ["$custom_emoji", "👤"]},
                    "created_at": {"$ifNull": ["$created_at", now]},
                    "updated_at": now,
                }
            }
        ],
    )
    return await col.find_one({"_id": uid})


async def get_user(user_id: int):
    col = users_collection()
    if col is None:
        return None
    return await col.find_one({"_id": int(user_id)})


async def add_coins(user_id: int, amount: int, *, session=None) -> bool:
    if amount <= 0:
        return False
    col = users_collection()
    if col is None:
        return False
    result = await col.update_one(
        {"_id": int(user_id)},
        {"$inc": {"coins": int(amount)}, "$set": {"updated_at": _now()}},
        session=session,
    )
    return result.modified_count == 1


async def remove_coins(user_id: int, amount: int, *, session=None) -> bool:
    if amount <= 0:
        return False
    col = users_collection()
    if col is None:
        return False
    result = await col.update_one(
        {"_id": int(user_id), "coins": {"$gte": int(amount)}},
        {"$inc": {"coins": -int(amount)}, "$set": {"updated_at": _now()}},
        session=session,
    )
    return result.modified_count == 1


async def add_xp(user_id: int, amount: int, *, session=None) -> dict:
    if amount <= 0:
        return {"ok": False, "levels": 0, "level": 1, "xp": 0, "required": 1000}
    col = users_collection()
    if col is None:
        return {"ok": False, "levels": 0, "level": 1, "xp": 0, "required": 1000}

    # XP is first increased atomically.
    result = await col.update_one(
        {"_id": int(user_id)},
        {"$inc": {"xp": int(amount)}, "$set": {"updated_at": _now()}},
        session=session,
    )
    if result.modified_count != 1:
        return {"ok": False, "levels": 0, "level": 1, "xp": 0, "required": 1000}

    doc = await col.find_one({"_id": int(user_id)}, {"level": 1, "xp": 1}, session=session)
    level = max(1, int(doc.get("level", 1)))
    xp = max(0, int(doc.get("xp", 0)))
    levels = 0

    # Carry XP forward while enough remains for the next level.
    while xp >= xp_needed(level):
        xp -= xp_needed(level)
        level += 1
        levels += 1

    await col.update_one(
        {"_id": int(user_id)},
        {"$set": {"xp": xp, "level": level, "updated_at": _now()}},
        session=session,
    )
    return {
        "ok": True,
        "levels": levels,
        "level": level,
        "xp": xp,
        "required": xp_needed(level),
    }


async def get_coin_rank(user_id: int) -> int | None:
    """Global rank by liquid coins only."""
    col = users_collection()
    if col is None:
        return None
    user = await col.find_one({"_id": int(user_id)}, {"coins": 1})
    if not user:
        return None
    coins = int(user.get("coins", 0))
    return (await col.count_documents({"coins": {"$gt": coins}})) + 1


async def get_kill_rank(user_id: int) -> int | None:
    """Global rank by kills only."""
    col = users_collection()
    if col is None:
        return None
    user = await col.find_one({"_id": int(user_id)}, {"kills": 1})
    if not user:
        return None
    kills = int(user.get("kills", 0))
    return (await col.count_documents({"kills": {"$gt": kills}})) + 1


async def top_rich(limit: int = 10):
    col = users_collection()
    if col is None:
        return []
    docs = await col.aggregate([
        {"$project": {
            "_id": 1,
            "username": 1,
            "first_name": 1,
            "user_id": {"$ifNull": ["$user_id", "$_id"]},
            "coins": {"$ifNull": ["$coins", 0]},
            "wallet": {"$ifNull": ["$wallet", 0]},
            "custom_emoji": {"$ifNull": ["$custom_emoji", "👤"]},
        }},
        {"$set": {"wealth": {"$add": ["$coins", "$wallet"]}}},
        {"$sort": {"wealth": -1, "_id": 1}},
        {"$limit": max(1, int(limit))},
    ]).to_list(length=max(1, int(limit)))
    return docs


async def top_killers(limit: int = 10):
    col = users_collection()
    if col is None:
        return []
    return await col.find(
        {},
        {
            "_id": 1,
            "username": 1,
            "first_name": 1,
            "kills": 1,
            "custom_emoji": {"$ifNull": ["$custom_emoji", "👤"]},
        },
    ).sort([("kills", -1), ("_id", 1)]).limit(max(1, int(limit))).to_list(length=max(1, int(limit)))


async def log_transaction(user_id: int, kind: str, amount: int, *, balance_before=None,
                          balance_after=None, meta=None, session=None):
    if db is None:
        return False
    doc = {
        "user_id": int(user_id),
        "type": str(kind),
        "amount": int(amount),
        "balance_before": balance_before,
        "balance_after": balance_after,
        "meta": meta or {},
        "created_at": _now(),
    }
    await db["economy_transactions"].insert_one(doc, session=session)
    return True


def shop_items():
    return db["economy_shop"] if db is not None else None


def economy_transactions():
    return db["economy_transactions"] if db is not None else None
