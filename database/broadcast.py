from datetime import datetime, timezone
from .mongo import db


def _collection():
    return db["broadcast_chats"] if db is not None else None


async def register_chat(chat):
    col = _collection()
    if col is None or not chat:
        return False
    chat_id = int(chat.id)
    chat_type = str(getattr(chat, "type", "")).lower()
    kind = "private" if "private" in chat_type else "group"
    await col.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "chat_id": chat_id,
            "type": kind,
            "title": getattr(chat, "title", "") or "",
            "username": getattr(chat, "username", "") or "",
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return True


async def get_broadcast_chats():
    col = _collection()
    if col is None:
        return []
    return await col.find({}).to_list(length=None)


async def remove_broadcast_chat(chat_id):
    col = _collection()
    if col is not None:
        await col.delete_one({"chat_id": int(chat_id)})


async def get_broadcast_count():
    col = _collection()
    if col is None:
        return {"total": 0, "groups": 0, "private": 0}
    return {
        "total": await col.count_documents({}),
        "groups": await col.count_documents({"type": "group"}),
        "private": await col.count_documents({"type": "private"}),
    }
