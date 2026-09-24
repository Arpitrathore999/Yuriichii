from database.mongo import social_settings

DEFAULT_CAPTIONS = {
    "hug": ["🫂 <b>{a} just hugged {b} tightly!</b> ❤️"],
    "kiss": ["💋 <b>{a} just stole a kiss from {b}!</b> 😘"],
    "bite": ["🧛 <b>{a} just bit {b}!</b> 😭"],
    "slap": ["👋 <b>{a} gave {b} a reality check!</b> 💀"],
    "kick": ["🦵 <b>{a} kicked {b} into another dimension!</b> 😭"],
    "cuddle": ["🫂 <b>{a} cuddled with {b}.</b> 🥰"],
    "pat": ["🫳 <b>{a} patted {b}'s head.</b> 🥹"],
    "highfive": ["✋ <b>{a} high-fived {b}!</b> 🔥"],
    "flirt": ["😏 <b>{a} is flirting with {b}.</b> 👀❤️"],
    "love": ["❤️ <b>{a} × {b} — Love Match: {pct}%</b> 💕"],
    "crush": ["💘 <b>{a}'s secret crush is {b}!</b> 👀"],
    "couple": ["💞 <b>Today's couple: {a} × {b} — {pct}%</b>"],
    "propose": ["💍 <b>{a} proposed to {b}!</b> Will you say yes? 🥹"],
    "marriage": ["💒 <b>{a} ❤️ {b} — Officially married!</b>"],
    "divorce": ["💔 <b>{a} × {b} — Marriage ended.</b> 😭"],
}

COMMANDS = tuple(DEFAULT_CAPTIONS)


def _col():
    return social_settings()


async def get_social_data(command):
    col = _col()
    if col is None:
        return {"gifs": [], "captions": DEFAULT_CAPTIONS.get(command, [])}
    doc = await col.find_one({"_id": command})
    return {
        "gifs": list((doc or {}).get("gifs", [])),
        "captions": list((doc or {}).get("captions", [])) or DEFAULT_CAPTIONS.get(command, []),
    }


async def add_gif(command, file_id):
    col = _col()
    if col is None:
        return False
    await col.update_one(
        {"_id": command},
        {"$addToSet": {"gifs": file_id}},
        upsert=True,
    )
    return True


async def add_caption(command, caption):
    col = _col()
    if col is None:
        return False
    await col.update_one(
        {"_id": command},
        {"$addToSet": {"captions": caption}},
        upsert=True,
    )
    return True


async def clear_gifs(command):
    col = _col()
    if col is None:
        return False
    await col.update_one({"_id": command}, {"$set": {"gifs": []}}, upsert=True)
    return True


async def clear_captions(command):
    col = _col()
    if col is None:
        return False
    await col.update_one({"_id": command}, {"$set": {"captions": []}}, upsert=True)
    return True
