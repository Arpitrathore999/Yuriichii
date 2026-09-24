from database.mongo import relationships

async def get_status(a, b):
    col = relationships()
    if col is None:
        return None
    key = f"{min(a,b)}:{max(a,b)}"
    doc = await col.find_one({"_id": key})
    return doc["status"] if doc else None

async def set_status(a, b, status):
    col = relationships()
    if col is None:
        return
    key = f"{min(a,b)}:{max(a,b)}"
    await col.update_one(
        {"_id": key},
        {"$set": {"a": min(a,b), "b": max(a,b), "status": status}},
        upsert=True,
    )

async def clear_status(a, b):
    col = relationships()
    if col is None:
        return
    await col.delete_one({"_id": f"{min(a,b)}:{max(a,b)}"})
