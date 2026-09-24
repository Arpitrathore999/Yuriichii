import time
from .mongo import ai_history

async def get_history(user_id, limit=8):
    col = ai_history()
    if col is None:
        return []
    rows = await col.find({"user_id": int(user_id)}).sort("ts", -1).limit(limit).to_list(length=limit)
    return [{"role": x["role"], "content": x["content"]} for x in reversed(rows)]

async def save_exchange(user_id, user_text, answer):
    col = ai_history()
    if col is None:
        return
    now = time.time()
    await col.insert_many([
        {"user_id": int(user_id), "role": "user", "content": user_text, "ts": now},
        {"user_id": int(user_id), "role": "assistant", "content": answer, "ts": now},
    ])
    await col.delete_many({"user_id": int(user_id), "ts": {"$lt": now - 86400 * 30}})
