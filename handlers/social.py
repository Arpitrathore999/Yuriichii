# Outlaw Music Social System — FIXED
# 15 commands | reply-only actions | random captions | relationship state
import random
import time
from pathlib import Path
from typing import Optional

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

try:
    from ShizuMusic import bot as app
except Exception:
    app = None

try:
    from config import MONGO_DB_URI
except Exception:
    MONGO_DB_URI = None

# ---------- Storage ----------
_relationships = {}
_pending = {}          # key -> (proposer_id, target_id, timestamp)
PENDING_TTL = 600      # 10 minutes

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    _mongo = AsyncIOMotorClient(MONGO_DB_URI) if MONGO_DB_URI else None
    _db = _mongo["outlaw_music"] if _mongo else None
    _rel_col = _db["social_relationships"] if _db else None
except Exception:
    _mongo = _db = _rel_col = None

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "social_gifs"

# ---------- Clean Captions ----------
CAPTIONS = {
    "hug": [
        "🫂 **{a} just hugs {b} tightly...**\n*\"Yeah... you're not escaping this one. 😏❤️\"*",
        "🫂 **A little hug? Nope. {a} is not letting go of {b}. 🥰💕**\n*\"Stay right here.\"*",
        "🤗 **{a} just found the perfect excuse to hold {b} close. 🫶🏻**",
    ],
    "kiss": [
        "💋 **Oops... {a} just stole a kiss from {b}.**\n*\"Don't look at me like that... you'll make me do it again. 😘\"*",
        "😘 **That was supposed to be a quick kiss...**\n*\"Well, that didn't go as planned. 🤭❤️\"*",
        "💋 **{a} just left {b} with a kiss and a lot of questions. 😏**",
    ],
    "bite": [
        "😲 **{a} just bit {b}... and didn't even apologize.**\n*\"You looked too tempting. 🤭\"*",
        "🧛 **{b} was just minding their own business...**\n*Then {a} happened. 😭*",
        "😏 **Warning: {a} has developed {b} looks too tasty. 🫦**",
    ],
    "slap": [
        "👋 **{b} just received a little reality check from {a}. 💥**",
        "👋 **{a} said \"wake up.\"**\n*{b} understood this time. 😭*",
        "💥 **Slow down. No refunds.**",
    ],
    "punch": [
        "🦵 **{a} just sent {b} on a one-way trip to the floor. 🚀😭**",
        "💥 **{b} was too close... {a} fixed that.**",
        "🦵 **Punch!**\n*\"Nothing personal, babe. 😭❤️\"*",
    ],
    "cuddle": [
        "🫶 **{a} just claimed {b} for a cuddle.**\n*\"Come here... you're mine for the next few hours. 🫶🏻\"*",
        "🧸 **Cuddle mode: Activated. 💕**\n*{a} × {b} = too cute.*",
        "🤗 **No words. Just {a} and {b} enjoying the moment. 🫂**",
    ],
    "pat": [
        "🫳 **{a} gently patted {b}'s head. 🥰💕**\n*\"Good job, cutie.\"*",
        "🐾 **Pat pat...**\n*{a} has decided {b} is too cute to leave alone. 🤭*",
        "🫶🏻 **{a}'s patting has unlocked premium cuteness. ✨**",
    ],
    "highfive": [
        "✋ **{a} high-fives {b} like they just won the lottery. 🔥**",
        "✋💥 **High five!**\n*That slap was louder than their chat. 😂*",
        "✨ **{a} + {b} = dangerous good teamwork. 🤝❤️**",
    ],
    "flirt": [
        "😏 **{a} just dropped some serious flirt on {b}.**\n*\"Are you always this attractive, or is today special? 👀❤️\"*",
        "👀 **{a} was looking at {b}...**\n*\"Why are you making it so hard to behave? 😏\"*",
        "💘 **Flirting with {b} has been added to {a}'s daily schedule. 😌**",
    ],
    "love": [
        "❤️ **Love Check** ❤️\n**{a} × {b}**\n💕 **Compatibility: {pct}%**\n*\"Okay... this is getting suspiciously romantic. 👀💗\"*",
        "💗 **Heart Sync Completed**\n**{a} ❤️ {b}**\n✨ **Match: {pct}%**\n*\"The chemistry is doing a little too much. 😏\"*",
        "💞 **Love Alert!**\n**{a} + {b} = {pct}%**\n*\"Someone's heart is definitely acting suspicious. 🤭❤️\"*",
    ],
}

SPECIAL = {
    "crush": [
        "💘 **Secret Crush Detected... 👀**\n**{a}'s secret crush is {b}!** 💕\n💘 **Crush Level: {pct}%**\n*\"Don't tell them... this is supposed to be a secret. 🤫❤️\"*",
        "👀 **We just uncovered {a}'s secret...**\n💗 **It's {b}!**\n✨ **Crush Power: {pct}%**\n*\"Your secret is out. Oops. 🤭\"*",
        "💌 **Secret crush pending for {a}...**\n💞 **{b}**\n💘 **Heart level: {pct}%**\n*\"The heart knows something the brain doesn't. 😏❤️\"*",
    ],
    "couple": [
        "💞 **Today's Cutest Couple** 💞\n**{a} × {b}**\n💘 **Match: {pct}%**\n*\"Okay... someone explain this chemistry. 👀❤️\"*",
        "💗 **Couple Alert!**\n**{a} 💕 {b}**\n✨ **Love Sync: {pct}%**\n*\"This pairing is dangerously cute. 🤭\"*",
        "💘 **Random Couple Selected!**\n**{a} ❤️ {b}**\n💞 **Chemistry: {pct}%**\n*\"The GC did not see this coming. 😏\"*",
    ],
    "propose": [
        "💍 **Wait... This is Serious. 😳**\n**{a}** just got down on one knee for **{b}**. 💍\n*\"I don't need forever... just say yes to me. 💍🫶\"*",
        "💍 **Someone Just Got Brave... 😭❤️**\n**{a} → {b}**\n*\"Will you be mine? 👉👈💗\"*",
        "🥹 **The Big Question is Here...**\n**{a} wants {b} to say yes with forever. 💍**\n*\"One little yes could change everything. ❤️\"*",
    ],
    "marriage": [
        "💒 **Well... They actually did it. 😳❤️**\n**{a} × {b}**\n💍 **Officially Married. 💞**\n*\"From one little yes... to forever. 🥹💗\"*",
        "💍 **It's Official!**\n**{a} ❤️ {b}**\n💒 **Married!**\n*\"The GC has a new power couple. 😎💕\"*",
        "🥂 **Marriage Confirmed!**\n**{a} & {b}** 💞\n*\"Two hearts, one beautiful mess. 😭❤️\"*",
    ],
    "divorce": [
        "💔 **So... This Is Really Happening? 🥺**\n**{a} × {b}**\n*\"Some stories don't get their forever... 💔\"*\n💔 **Marriage Ended**",
        "🥺 **The Forever Plan has ended...**\n**{a} 💔 {b}**\n*\"And just like that, it's over. 😭\"*",
        "💔 **Divorce Filed... and Approved. 🥺**\n**{a} ≠ {b}**\n*\"Love story status: archived. 😭\"*",
    ],
}

COMMANDS = ["hug","kiss","bite","slap","punch","cuddle","pat","highfive","flirt",
            "love","crush","couple","propose","marriage","divorce"]
ACTION_COMMANDS = ["hug","kiss","bite","slap","punch","cuddle","pat","highfive",
                   "flirt","love","propose","marriage","divorce"]


# ---------- Helpers ----------
def mention(user):
    name = (user.first_name or "Someone").replace("<", "").replace(">", "")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def target_from_reply(message):
    return message.reply_to_message.from_user if message.reply_to_message else None


async def members_from_chat(client, chat_id, exclude_ids=()):
    ids = set(exclude_ids)
    result = []
    try:
        async for m in client.get_chat_members(chat_id):
            u = m.user
            if not u or u.is_bot or u.id in ids:
                continue
            result.append(u)
            if len(result) >= 100:   # cap for performance
                break
    except Exception:
        pass
    return result


async def get_rel(a, b):
    key = tuple(sorted((a, b)))
    if _rel_col:
        try:
            doc = await _rel_col.find_one({"_id": f"{key[0]}:{key[1]}"})
            return doc["status"] if doc else None
        except Exception:
            pass
    return _relationships.get(key)


async def set_rel(a, b, status):
    key = tuple(sorted((a, b)))
    if _rel_col:
        try:
            await _rel_col.update_one(
                {"_id": f"{key[0]}:{key[1]}"},
                {"$set": {"a": key[0], "b": key[1], "status": status}},
                upsert=True,
            )
        except Exception:
            pass
    _relationships[key] = status


async def clear_rel(a, b):
    key = tuple(sorted((a, b)))
    if _rel_col:
        try:
            await _rel_col.delete_one({"_id": f"{key[0]}:{key[1]}"})
        except Exception:
            pass
    _relationships.pop(key, None)


def _cleanup_pending():
    """Remove expired proposals."""
    now = time.time()
    expired = [k for k, v in _pending.items() if now - v[2] > PENDING_TTL]
    for k in expired:
        _pending.pop(k, None)


def pick(pool, **kwargs):
    return random.choice(pool).format(**kwargs)


async def send_random_media(message, command, caption, reply_markup=None):
    folder = ASSET_ROOT / command
    files = [p for p in folder.glob("*") if p.is_file()] if folder.exists() else []
    if not files:
        return await message.reply_text(caption, parse_mode="html", reply_markup=reply_markup)
    chosen = random.choice(files)
    ext = chosen.suffix.lower()
    try:
        if ext == ".gif":
            return await message.reply_animation(str(chosen), caption=caption,
                                                 parse_mode="html", reply_markup=reply_markup)
        if ext in {".mp4", ".webm"}:
            return await message.reply_video(str(chosen), caption=caption,
                                             parse_mode="html", reply_markup=reply_markup)
        return await message.reply_photo(str(chosen), caption=caption,
                                         parse_mode="html", reply_markup=reply_markup)
    except Exception:
        # fallback to text if media send fails
        return await message.reply_text(caption, parse_mode="html", reply_markup=reply_markup)


# ---------- Core Handler ----------
async def generic_handler(client, message):
    cmd = (message.command or [""])[0].lower()
    if cmd not in ACTION_COMMANDS:
        return None

    target = target_from_reply(message)
    if not target:
        return await message.reply_text(
            "❌ **Reply to a user's message first.**\n*Social commands use reply-only targeting. 💕*",
            parse_mode="html",
        )
    if target.is_bot:
        return await message.reply_text(
            "🤖 **Bots don't have feelings... pick a real human. 😭**",
            parse_mode="html",
        )
    if target.id == message.from_user.id:
        return await message.reply_text(
            "❌ **You can't use this on yourself. 😏**",
            parse_mode="html",
        )

    a, b = mention(message.from_user), mention(target)

    # ----- Propose -----
    if cmd == "propose":
        existing = await get_rel(message.from_user.id, target.id)
        if existing in {"engaged", "married"}:
            return await message.reply_text(
                "💍 **You already have a relationship with this person. ❤️**",
                parse_mode="html",
            )
        _cleanup_pending()
        text = pick(SPECIAL["propose"], a=a, b=b)
        key = f"{message.chat.id}:{message.id}"
        _pending[key] = (message.from_user.id, target.id, time.time())
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("💍 Accept", callback_data=f"social:accept:{key}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"social:reject:{key}"),
        ]])
        return await send_random_media(message, cmd, text, reply_markup=markup)

    # ----- Love -----
    if cmd == "love":
        return await send_random_media(
            message, cmd, pick(CAPTIONS["love"], a=a, b=b, pct=random.randint(1, 100))
        )

    # ----- Marriage / Divorce -----
    if cmd in {"marriage", "divorce"}:
        status = await get_rel(message.from_user.id, target.id)
        if cmd == "marriage" and status != "engaged":
            return await message.reply_text(
                "❌ **Not so fast, love. 😭**\n*You need an accepted proposal first. 💍*",
                parse_mode="html",
            )
        if cmd == "divorce" and status != "married":
            return await message.reply_text(
                "😭 **Bruh... What Marriage?**\n*You two aren't married. 💔*",
                parse_mode="html",
            )
        if cmd == "marriage":
            await set_rel(message.from_user.id, target.id, "married")
        else:
            await clear_rel(message.from_user.id, target.id)
        return await send_random_media(message, cmd, pick(SPECIAL[cmd], a=a, b=b))

    # ----- Generic (hug/kiss/etc.) -----
    return await send_random_media(message, cmd, pick(CAPTIONS[cmd], a=a, b=b))


async def crush_handler(client, message):
    if (message.command or [""])[0].lower() != "crush":
        return
    target = target_from_reply(message)
    if not target:
        return await message.reply_text(
            "❌ **Reply to the person whose secret crush you want to find. 👀**",
            parse_mode="html",
        )
    if target.is_bot or target.id == message.from_user.id:
        return await message.reply_text(
            "❌ **That target won't work. Try a real human. 😭**",
            parse_mode="html",
        )
    candidates = await members_from_chat(client, message.chat.id, {target.id})
    if not candidates:
        return await message.reply_text(
            "❌ **Not enough members to find a crush. 😭**",
            parse_mode="html",
        )
    crush = random.choice(candidates)
    return await send_random_media(
        message, "crush",
        pick(SPECIAL["crush"], a=mention(target), b=mention(crush), pct=random.randint(1, 100)),
    )


async def couple_handler(client, message):
    if (message.command or [""])[0].lower() != "couple":
        return
    candidates = await members_from_chat(client, message.chat.id)
    if len(candidates) < 2:
        return await message.reply_text(
            "❌ **Need at least 2 non-bot members. 💞**",
            parse_mode="html",
        )
    x, y = random.sample(candidates, 2)
    return await send_random_media(
        message, "couple",
        pick(SPECIAL["couple"], a=mention(x), b=mention(y), pct=random.randint(1, 100)),
    )


# ---------- Callback + Dispatcher ----------
async def _edit_proposal_message(cq, suffix_html):
    base = cq.message.caption or cq.message.text or ""
    new_text = base + "\n\n" + suffix_html
    try:
        if cq.message.caption:
            await cq.message.edit_caption(new_text, parse_mode="html")
        else:
            await cq.message.edit_text(new_text, parse_mode="html")
    except Exception:
        pass


if app:
    @app.on_callback_query(filters.regex(r"^social:(accept|reject):"))
    async def social_callback(client, cq):
        _cleanup_pending()
        key = cq.data.split(":", 2)[2]
        pair = _pending.get(key)
        if not pair:
            return await cq.answer("This proposal has expired. 💔", show_alert=True)
        proposer, target, _ts = pair
        if cq.from_user.id != target:
            return await cq.answer("Only the receiver can choose. 🚫", show_alert=True)

        action = cq.data.split(":")[1]
        if action == "accept":
            await set_rel(proposer, target, "engaged")
            _pending.pop(key, None)
            await _edit_proposal_message(cq, "💞 <b>Proposal Accepted!</b> 💍")
        else:
            _pending.pop(key, None)
            await _edit_proposal_message(cq, "💔 <b>Proposal Rejected.</b>")
        await cq.answer()

    @app.on_message(filters.command(COMMANDS))
    async def social_dispatch(client, message):
        cmd = (message.command or [""])[0].lower()
        if cmd == "crush":
            return await crush_handler(client, message)
        if cmd == "couple":
            return await couple_handler(client, message)
        return await generic_handler(client, message)