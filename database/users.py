from datetime import datetime, timezone
from .mongo import users

async def ensure_user(user):
    """Create/update a user record. Returns False when DB is unavailable."""
    col = users()
    if col is None or not user:
        return False
    await col.update_one(
        {"_id": int(user.id)},
        {"$setOnInsert": {
            "_id": int(user.id),
            "joined_at": datetime.now(timezone.utc),
            "warnings": 0,
            "banned": False,
        }, "$set": {
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_seen": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return True

async def is_user_banned(user_id: int) -> bool:
    col = users()
    if col is None:
        return False
    doc = await col.find_one({"_id": int(user_id)}, {"banned": 1})
    return bool(doc and doc.get("banned", False))

async def set_user_banned(user_id: int, banned: bool, admin_id: int | None = None):
    col = users()
    if col is None:
        return False
    now = datetime.now(timezone.utc)
    update = {
        "$set": {
            "banned": bool(banned),
            "banned_at": now if banned else None,
            "banned_by": int(admin_id) if banned and admin_id else None,
        }
    }
    await col.update_one(
        {"_id": int(user_id)},
        {"$setOnInsert": {"_id": int(user_id), "joined_at": now, "warnings": 0},
         **update},
        upsert=True,
    )
    return True

async def get_user(user_id: int):
    col = users()
    if col is None:
        return None
    return await col.find_one({"_id": int(user_id)})

async def get_user_stats():
    col = users()
    if col is None:
        return {"total": 0, "banned": 0, "active": 0}
    total = await col.count_documents({})
    banned = await col.count_documents({"banned": True})
    return {"total": total, "banned": banned, "active": total - banned}

async def get_users_page(page: int = 0, page_size: int = 8, banned_only=False):
    col = users()
    if col is None:
        return [], 0
    query = {"banned": True} if banned_only else {}
    total = await col.count_documents(query)
    docs = await (
        col.find(query)
        .sort("last_seen", -1)
        .skip(max(0, int(page)) * page_size)
        .limit(page_size)
        .to_list(length=page_size)
    )
    return docs, total
