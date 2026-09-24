from datetime import datetime, timezone
from .mongo import users

async def ensure_user(user):
    col = users()
    if col is None or not user:
        return
    await col.update_one(
        {"_id": int(user.id)},
        {"$setOnInsert": {
            "_id": int(user.id),
            "joined_at": datetime.now(timezone.utc),
            "warnings": 0,
        }, "$set": {
            "username": user.username or "",
            "first_name": user.first_name or "",
        }},
        upsert=True,
    )
