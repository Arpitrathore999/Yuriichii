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
    try:
        return social_settings()
    except Exception as e:
        print(f"[SOCIAL DB INIT ERROR] {type(e).__name__}: {e}", flush=True)
        return None

async def get_social_data(command):
    fallback = {"gifs": [], "captions": list(DEFAULT_CAPTIONS.get(command, []))}
    col = _col()
    if col is None:
        return fallback
    try:
        doc = await col.find_one({"_id": command})
        if not doc:
            return fallback
        return {"gifs": list(doc.get("gifs") or []),
                "captions": list(doc.get("captions") or []) or fallback["captions"]}
    except Exception as e:
        print(f"[SOCIAL SETTINGS ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return fallback

async def add_gif(command, file_id):
    col = _col()
    if col is None: return False
    try:
        await col.update_one({"_id": command}, {"$addToSet": {"gifs": file_id}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ADD GIF ERROR] {type(e).__name__}: {e}", flush=True); return False

async def add_caption(command, caption):
    col = _col()
    if col is None: return False
    try:
        await col.update_one({"_id": command}, {"$addToSet": {"captions": caption}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ADD CAPTION ERROR] {type(e).__name__}: {e}", flush=True); return False

async def clear_gifs(command):
    col = _col()
    if col is None: return False
    try:
        await col.update_one({"_id": command}, {"$set": {"gifs": []}}, upsert=True); return True
    except Exception as e:
        print(f"[CLEAR GIF ERROR] {type(e).__name__}: {e}", flush=True); return False

async def clear_captions(command):
    col = _col()
    if col is None: return False
    try:
        await col.update_one({"_id": command}, {"$set": {"captions": []}}, upsert=True); return True
    except Exception as e:
        print(f"[CLEAR CAPTION ERROR] {type(e).__name__}: {e}", flush=True); return False
