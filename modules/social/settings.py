from database.mongo import social_settings

DEFAULT_CAPTIONS = {
    "hug": [
        "🫂 <b>{a} finally got the hug they were begging {b} for!</b> 😭",
        "💀 <b>Plot twist: {a} attacked {b} with a hug!</b> 🫂❤️",
        "🥺 <b>{a} hugged {b} like rent was due tomorrow.</b> 🫂",
    ],
    "kiss": [
        "💋 <b>{a} stole a kiss from {b} and ran away!</b> 😭",
        "👀 <b>Someone's getting suspiciously romantic… {a} → {b}</b> 💋",
        "💀 <b>{a} kissed {b}. No witnesses. Probably.</b> 💋",
    ],
    "bite": [
        "🧛 <b>{a} just decided {b} looked delicious.</b> 😭",
        "🦷 <b>{a} launched a surprise bite attack on {b}!</b> 💀",
        "😈 <b>{b} should've run… {a} was hungry.</b> 🩸",
    ],
    "slap": [
        "💀 <b>{a} slapped {b} back to reality.</b> 👋",
        "😭 <b>{b} really thought {a} would let that slide.</b> 👋",
        "🔥 <b>Critical hit! {a} just humbled {b}.</b> 💀",
    ],
    "kick": [
        "🚀 <b>{a} sent {b} on a free trip to the moon.</b> 💀",
        "🦵 <b>{b} has officially been kicked out of {a}'s patience.</b> 😭",
        "💀 <b>And there goes {b}… flying at 120 km/h.</b> 🦵",
    ],
    "cuddle": [
        "🫂 <b>{a} kidnapped {b} for mandatory cuddles.</b> 😭",
        "🥹 <b>No escaping. {a} has locked {b} in the cuddle zone.</b> 🫂",
        "💀 <b>{a} + {b} = professional cuddle criminals.</b> 🫂",
    ],
    "pat": [
        "😭 <b>{a} patted {b} like a well-behaved little gremlin.</b> 🫳",
        "🥹 <b>Good job, {b}. Here's your emotional-support pat.</b> 🫳",
        "🫳 <b>{a}: “Who's my favorite idiot?” — {b}: 😭❤️</b>",
    ],
    "highfive": [
        "✋ <b>{a} and {b} just hit a perfect high five!</b> 🔥",
        "🙌 <b>{a} high-fived {b} like they just won the finals.</b> 😭",
        "🔥 <b>That high five had more chemistry than most couples.</b> ✋",

    ],
    "flirt": [
        "😏 <b>{a} is flirting with {b} like there isn't a whole group watching.</b> 👀",
        "🚨 <b>{b}, careful… {a} is dangerously smooth today.</b> 😏🔥",
        "👀 <b>Warning: {a} has entered flirt mode. {b} is the target.</b> ❤️",
    ],
    "love": [
        "😭❤️ <b>{a} and {b} are giving everyone else trust issues.</b>",
        "👀 <b>The chemistry between {a} and {b} is getting suspicious.</b> 💕",
        "💀 <b>{a} ❤️ {b} — somebody check the wedding calendar.</b>",
    ],
    "crush": [
        "👀 <b>{a} has a crush on {b}. Pretend you didn't see this.</b> 💘",
        "😭 <b>Breaking news: {a}'s heart belongs to {b}.</b> 💘",
        "💀 <b>{a} looked at {b} once and forgot how to act.</b> ❤️",
    ],
    "couple": [
        "💀 <b>{a} and {b} are giving suspiciously strong couple vibes.</b> 💕",
        "👀 <b>Everyone saw it. {a} × {b} is a thing now.</b> 💞",
        "😭 <b>{a} + {b} = the duo nobody asked for but everyone ships.</b> ❤️",

    ],
    "propose": [
        "💍 <b>{a} just dropped the biggest question on {b}.</b> 😭❤️",
        "👀 <b>{a} got down on one knee for {b}. This is getting serious.</b> 💍",
        "💀 <b>{a} proposed to {b}. Someone hide the wedding planner.</b> 💒",

    ],
    "marriage": [
        "💒 <b>{a} and {b} really said “let’s make it official.”</b> 😭❤️",
        "💍 <b>Congratulations! {a} and {b} are officially stuck together.</b> 💀",
        "🥂 <b>{a} × {b} — somehow this wedding actually happened.</b> 💒",

    ],
    "divorce": [
        "💀 <b>{a} and {b} have officially left the group chat… emotionally.</b> 💔",
        "😭 <b>It was fun while it lasted. {a} × {b} is officially over.</b> 🥀",
        "🚨 <b>Breaking news: {a} filed for freedom from {b}.</b> 💀💔",

    ],
}

COMMANDS = tuple(DEFAULT_CAPTIONS)


def _col():
    return social_settings()


async def get_social_data(command):
    fallback = {"gifs": [], "captions": DEFAULT_CAPTIONS.get(command, [])}
    col = _col()
    if col is None:
        return fallback

    try:
        doc = await col.find_one({"_id": command})
        if not doc:
            return fallback
        captions = list(doc.get("captions") or []) or fallback["captions"]
        gifs = list(doc.get("gifs") or [])
        return {"gifs": gifs, "captions": captions}
    except Exception as e:
        print(f"[SOCIAL SETTINGS ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return fallback


async def add_gif(command, file_id):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$addToSet": {"gifs": file_id}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ADD GIF ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return False


async def add_caption(command, caption):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$addToSet": {"captions": caption}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ADD CAPTION ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return False


async def clear_gifs(command):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$set": {"gifs": []}}, upsert=True)
        return True
    except Exception:
        return False


async def clear_captions(command):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$set": {"captions": []}}, upsert=True)
        return True
    except Exception:
        return False
