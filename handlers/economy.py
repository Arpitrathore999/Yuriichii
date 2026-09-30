"""Telegram handlers for the isolated economy system."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import RPCError

from core.bot import app
from database.mongo import db
from core.database import (
    ensure_user,
    get_user,
    get_coin_rank,
    get_kill_rank,
    top_rich,
    top_killers,
)
from core.economy import (
    check_user,
    claim_daily,
    deposit_wallet,
    kill_user,
    net_after_tax,
    protect_user,
    rob_user,
    tax_for,
    transfer,
    withdraw_wallet,
)

PREFIXES = ["/", ".", "!"]
OWNER_ID = int(getattr(__import__("config"), "OWNER_ID", 0) or 0)


def _mention(user_id, name):
    return f'<a href="tg://user?id={int(user_id)}">{escape(name or "User")}</a>'


def _name(user):
    return getattr(user, "first_name", None) or getattr(user, "username", None) or str(getattr(user, "id", "User"))


def _reply_target(message):
    reply = message.reply_to_message
    return reply.from_user if reply and reply.from_user else None


async def _ensure_from_message(message):
    if message.from_user:
        await ensure_user(message.from_user)


async def _resolve_private_target(message, token):
    try:
        if token.lstrip("-").isdigit():
            return await app.get_users(int(token))
        return await app.get_users(token.lstrip("@"))
    except Exception:
        return None


def _protection_active(user):
    until = user.get("protection_until") if user else None
    return bool(until and until > datetime.now(timezone.utc))


async def _profile_text(user):
    await ensure_user(user)
    doc = await get_user(user.id)
    coin_rank = await get_coin_rank(user.id)
    kill_rank = await get_kill_rank(user.id)

    level = int(doc.get("level", 1))
    xp = int(doc.get("xp", 0))
    required = level * 1000

    return (
        f"👤 {_mention(user.id, _name(user))}\n"
        f"💰 Cᴏɪɴꜱ: ${int(doc.get('coins', 0))}\n"
        f"🏆 Gʟᴏʙᴀʟ Rᴀɴᴋ: {coin_rank or '—'}\n"
        f"🔓 Sᴛᴀᴛᴜꜱ: {escape(str(doc.get('status', 'alive')))}\n"
        f"⚔️ Kɪʟʟꜱ: {int(doc.get('kills', 0))} (#{kill_rank or '—'})\n"
        f"💠 Lᴇᴠᴇʟ {level}: {xp}/{required}"
    )


@app.on_message(filters.command(["bal", "balance"], prefixes=PREFIXES))
async def economy_balance(_, message):
    await _ensure_from_message(message)
    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command or []) > 1:
        # Username targeting is deliberately forbidden for /bal.
        return await message.reply("❌ /bal only supports yourself or a reply target.")
    if not target or target.is_bot:
        return await message.reply("❌ Invalid user.")
    await ensure_user(target)
    await message.reply(await _profile_text(target), parse_mode=ParseMode.HTML)


@app.on_message(filters.command("daily", prefixes=PREFIXES))
async def economy_daily(_, message):
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply("❌ /daily can only be used in private chat.")
    await _ensure_from_message(message)
    result = await claim_daily(message.from_user.id)
    if not result["ok"]:
        if result["reason"] == "already_claimed":
            return await message.reply("🎁 You already claimed today's daily reward. Come back after midnight.")
        return await message.reply("❌ Economy database is unavailable.")
    await message.reply(
        f"🎁 Dᴀɪʟʏ Rᴇᴡᴀʀᴅ\n\n"
        f"💰 Rᴇᴡᴀʀᴅ: +{result['reward']} 🪙\n"
        f"💳 Bᴀʟᴀɴᴄᴇ: {result['balance']} 🪙"
    )


@app.on_message(filters.command("kill", prefixes=PREFIXES))
async def economy_kill(_, message):
    await _ensure_from_message(message)
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ Reply to a user's message to use /kill.")
    if target.is_bot:
        return await message.reply("🤖 You can't kill a bot.")
    result = await kill_user(message.from_user.id, target.id)
    reason = result.get("reason")
    if not result["ok"]:
        return await message.reply({
            "self": "❌ You can't kill yourself.",
            "dead": "☠️ That user is already dead.",
            "protected": "🛡️ That user is protected.",
            "killer_dead": "☠️ Dead users cannot kill.",
            "killer_unavailable": "❌ Your kill could not be completed safely.",
            "not_available": "❌ The target was already processed.",
            "transaction_unavailable": "❌ Economy transaction could not be completed.",
        }.get(reason, "❌ Kill failed."))
    level_info = result.get("level", {})
    level_note = f"\n💠 Level: {level_info['level']}" if level_info.get("levels") else ""
    await message.reply(
        f"⚔️ Kɪʟʟ Sᴜᴄᴄᴇꜱꜱ\n\n"
        f"💀 Target: {_mention(target.id, _name(target))}\n"
        f"💰 Reward: +{result['coins']} 🪙\n"
        f"✨ XP: +{result['xp']}{level_note}",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command("rob", prefixes=PREFIXES))
async def economy_rob(_, message):
    await _ensure_from_message(message)
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ Reply to a user's message to use /rob.")
    if target.is_bot:
        return await message.reply("🤖 You can't rob a bot.")
    result = await rob_user(message.from_user.id, target.id)
    reason = result.get("reason")
    if not result["ok"]:
        if reason == "cooldown":
            return await message.reply("⏳ You're robbing too fast. Try again later.")
        if reason == "protected":
            return await message.reply("🛡️ That user is protected.")
        if reason == "insufficient":
            return await message.reply("❌ Target doesn't have enough liquid coins.")
        return await message.reply("❌ Rob failed.")
    if not result["success"]:
        return await message.reply("🚨 Rob failed! You got nothing.")
    await message.reply(
        f"💸 Rᴏʙ Sᴜᴄᴄᴇꜱꜱ\n\n"
        f"👤 Target: {_mention(target.id, _name(target))}\n"
        f"💰 Stolen: {result['amount']} 🪙",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command("wallet", prefixes=PREFIXES))
async def economy_wallet(_, message):
    await _ensure_from_message(message)
    if len(message.command or []) != 2:
        doc = await get_user(message.from_user.id)
        total = int(doc.get("coins", 0)) + int(doc.get("wallet", 0))
        maximum = int(total * 0.30)
        return await message.reply(
            f"🏦 Wᴀʟʟᴇᴛ\n\n"
            f"💰 Liquid: {int(doc.get('coins', 0))}\n"
            f"🔐 Wallet: {int(doc.get('wallet', 0))}\n"
            f"📦 Maximum: {maximum}"
        )
    raw = message.command[1]
    try:
        amount = int(raw)
    except ValueError:
        return await message.reply("❌ Usage: /wallet +300 or /wallet -300")
    if amount == 0:
        return await message.reply("❌ Amount must not be zero.")
    result = await deposit_wallet(message.from_user.id, amount) if amount > 0 else await withdraw_wallet(message.from_user.id, abs(amount))
    if not result["ok"]:
        if result["reason"] == "wallet_limit":
            return await message.reply(f"❌ Wallet limit reached. Maximum: {result['maximum']} 🪙")
        if result["reason"] == "insufficient":
            return await message.reply("❌ Insufficient balance.")
        return await message.reply("❌ Invalid wallet operation.")
    await message.reply(
        f"🏦 Wᴀʟʟᴇᴛ Uᴘᴅᴀᴛᴇᴅ\n\n"
        f"💰 Liquid: {result['coins']} 🪙\n"
        f"🔐 Wallet: {result['wallet']} 🪙"
    )


@app.on_message(filters.command("give", prefixes=PREFIXES))
async def economy_give(_, message):
    await _ensure_from_message(message)
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ Reply to the recipient's message.\nUsage: /give <amount>")
    if target.is_bot:
        return await message.reply("🤖 You can't transfer coins to a bot.")
    if len(message.command or []) != 2:
        return await message.reply("❌ Usage: /give <amount> (reply to a user)")
    try:
        amount = int(message.command[1])
    except ValueError:
        return await message.reply("❌ Amount must be a positive integer.")
    result = await transfer(message.from_user.id, target.id, amount)
    if not result["ok"]:
        return await message.reply({
            "self": "❌ You can't transfer coins to yourself.",
            "invalid_amount": "❌ Amount must be greater than 0.",
            "insufficient": "❌ Insufficient liquid coins.",
            "transaction_unavailable": "❌ Transfer transaction could not be completed.",
        }.get(result.get("reason"), "❌ Transfer failed."))
    await message.reply(
        f"💸 Tʀᴀɴꜱғᴇʀ Cᴏᴍᴘʟᴇᴛᴇ\n\n"
        f"👤 To: {_mention(target.id, _name(target))}\n"
        f"💰 Sent: {result['gross']} 🪙\n"
        f"🧾 Tax: {result['tax']} 🪙\n"
        f"📥 Received: {result['net']} 🪙",
        parse_mode=ParseMode.HTML,
    )


@app.on_message(filters.command("protect", prefixes=PREFIXES))
async def economy_protect(_, message):
    await _ensure_from_message(message)
    if len(message.command or []) != 2 or message.command[1].lower() != "1d":
        return await message.reply("❌ Usage: /protect 1d")
    result = await protect_user(message.from_user.id)
    if not result["ok"]:
        if result["reason"] == "already_protected":
            return await message.reply("🛡️ Protection is already active.")
        if result["reason"] == "insufficient":
            return await message.reply("❌ You need 500 coins to activate protection.")
        return await message.reply("❌ Could not activate protection.")

    until = result["until"].astimezone(economy_timezone()).strftime("%d %b %Y, %I:%M %p")
    dm_text = (
        "🛡️ <b>Pʀᴏᴛᴇᴄᴛɪᴏɴ Aᴄᴛɪᴠᴀᴛᴇᴅ</b>\n\n"
        "💰 Cost: 500 🪙\n"
        f"⏳ Expires: {until}\n"
        "🔒 You are protected from /rob and /kill."
    )
    try:
        await app.send_message(message.from_user.id, dm_text, parse_mode=ParseMode.HTML)
        dm_note = "Details have been sent in DM."
    except Exception:
        dm_note = "DM delivery is unavailable, but protection is active."
    await message.reply(f"🛡️ Protection activated.\n{dm_note}")


@app.on_message(filters.command("check", prefixes=PREFIXES))
async def economy_check(_, message):
    await _ensure_from_message(message)
    target = None
    if message.chat.type == ChatType.PRIVATE:
        if len(message.command or []) != 2:
            return await message.reply("❌ Usage in private: /check @username or /check user_id")
        target = await _resolve_private_target(message, message.command[1])
    else:
        target = _reply_target(message)
        if len(message.command or []) > 1:
            return await message.reply("❌ In groups /check only supports reply targeting.")
    if not target:
        return await message.reply("❌ Target user not found.")
    if target.is_bot:
        return await message.reply("🤖 Bots cannot be checked.")
    if target.id == message.from_user.id:
        return await message.reply("❌ You can't check yourself.")

    result = await check_user(message.from_user.id, target.id)
    if not result["ok"]:
        if result["reason"] == "insufficient":
            return await message.reply("❌ You need 500 coins.")
        return await message.reply("❌ Check failed.")

    doc = result["target"]
    protected = "active" if result["protected"] else "inactive"
    details = (
        f"🔎 <b>Cʜᴇᴄᴋ</b>\n\n"
        f"👤 {_mention(target.id, _name(target))}\n"
        f"💰 Coins: {int(doc.get('coins', 0))}\n"
        f"🔐 Wallet: {int(doc.get('wallet', 0))}\n"
        f"💠 Level: {int(doc.get('level', 1))}\n"
        f"⚔️ Kills: {int(doc.get('kills', 0))}\n"
        f"🔓 Status: {escape(str(doc.get('status', 'alive')))}\n"
        f"🛡️ Protection: {protected}"
    )
    try:
        await app.send_message(message.from_user.id, details, parse_mode=ParseMode.HTML)
        if message.chat.type != ChatType.PRIVATE:
            return await message.reply("🔎 Check details have been sent in DM.")
    except Exception:
        return await message.reply("❌ I couldn't send the check details in DM.")


@app.on_message(filters.command("toprich", prefixes=PREFIXES))
async def economy_toprich(_, message):
    await _ensure_from_message(message)
    rows = await top_rich(10)
    if not rows:
        return await message.reply("❌ No economy users found.")
    lines = ["🏆 Tᴏᴘ Rɪᴄʜ", ""]
    for i, row in enumerate(rows, 1):
        name = row.get("first_name") or row.get("username") or str(row["_id"])
        lines.append(f"{i}. {_mention(row['_id'], name)} — {int(row.get('wealth', 0))} 🪙")
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command("topkillers", prefixes=PREFIXES))
async def economy_topkillers(_, message):
    await _ensure_from_message(message)
    rows = await top_killers(10)
    if not rows:
        return await message.reply("❌ No economy users found.")
    lines = ["⚔️ Tᴏᴘ Kɪʟʟᴇʀꜱ", ""]
    for i, row in enumerate(rows, 1):
        name = row.get("first_name") or row.get("username") or str(row["_id"])
        lines.append(f"{i}. {_mention(row['_id'], name)} — {int(row.get('kills', 0))} kills")
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


# --------------------------- Shop & Gifts -----------------------------------

def _shop_collection():
    from database.mongo import economy_shop
    return economy_shop()


async def _is_owner(message):
    return bool(message.from_user and int(message.from_user.id) == OWNER_ID)


@app.on_message(filters.command("shop", prefixes=PREFIXES))
async def economy_shop(_, message):
    col = _shop_collection()
    if col is None:
        return await message.reply("❌ Economy database is unavailable.")
    rows = await col.find({"enabled": True}).sort("item_id", 1).to_list(length=100)
    if not rows:
        return await message.reply("🛒 Shop is empty.")
    lines = ["🛒 Eᴄᴏɴᴏᴍʏ Sʜᴏᴘ", ""]
    for item in rows:
        stock = item.get("stock", -1)
        stock_text = "∞" if int(stock) < 0 else str(stock)
        gift = " 🎁" if item.get("gift") else ""
        lines.append(
            f"• <b>{escape(str(item.get('item_id')))}</b> — "
            f"{escape(str(item.get('name', 'Item')))}{gift}\n"
            f"  💰 {int(item.get('price', 0))} 🪙 | 📦 {stock_text}\n"
            f"  {escape(str(item.get('description', '')))}"
        )
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command("buy", prefixes=PREFIXES))
async def economy_buy(_, message):
    if len(message.command or []) != 2:
        return await message.reply("❌ Usage: /buy <item_id>")
    await _ensure_from_message(message)
    item_id = message.command[1]
    col = _shop_collection()
    if col is None:
        return await message.reply("❌ Economy database is unavailable.")
    item = await col.find_one({"item_id": item_id, "enabled": True})
    if not item:
        return await message.reply("❌ Item not found or disabled.")
    if int(item.get("stock", -1)) == 0:
        return await message.reply("❌ Item is out of stock.")

    from database.mongo import mongo_client, users
    client = mongo_client()
    ucol = users()
    if client is None or ucol is None:
        return await message.reply("❌ Economy database is unavailable.")

    price = int(item.get("price", 0))
    if price <= 0:
        return await message.reply("❌ Item price is invalid.")

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                stock_query = {"item_id": item_id, "enabled": True}
                stock_update = {}
                if int(item.get("stock", -1)) >= 0:
                    stock_query["stock"] = {"$gte": 1}
                    stock_update = {"$inc": {"stock": -1}}
                stock_result = await col.update_one(
                    stock_query,
                    stock_update,
                    session=session,
                ) if stock_update else None
                if stock_update and stock_result.modified_count != 1:
                    await session.abort_transaction()
                    return await message.reply("❌ Item went out of stock.")
                if (await ucol.update_one(
                    {"_id": message.from_user.id, "coins": {"$gte": price}},
                    {"$inc": {"coins": -price}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    session=session,
                )).modified_count != 1:
                    await session.abort_transaction()
                    return await message.reply("❌ Insufficient coins.")
                # Inventory is separate from social/game state.
                inv = db["economy_inventory"] if db is not None else None
                if inv is not None:
                    await inv.update_one(
                        {"user_id": message.from_user.id, "item_id": item_id},
                        {"$inc": {"quantity": 1},
                         "$set": {"name": item.get("name", item_id), "updated_at": datetime.now(timezone.utc)}},
                        upsert=True, session=session,
                    )
        return await message.reply(f"🛒 Purchased <b>{escape(str(item.get('name', item_id)))}</b> for {price} 🪙.", parse_mode=ParseMode.HTML)
    except Exception:
        return await message.reply("❌ Purchase transaction could not be completed.")


@app.on_message(filters.command("gift", prefixes=PREFIXES))
async def economy_gift(_, message):
    target = _reply_target(message)
    if not target:
        return await message.reply("❌ Reply to the recipient's message.\nUsage: /gift <item_id>")
    if target.is_bot:
        return await message.reply("🤖 You can't gift a bot.")
    if target.id == message.from_user.id:
        return await message.reply("❌ You can't gift yourself.")
    if len(message.command or []) != 2:
        return await message.reply("❌ Usage: /gift <item_id> (reply to a user)")
    item_id = message.command[1]
    col = _shop_collection()
    from database.mongo import mongo_client, users
    client = mongo_client()
    ucol = users()
    inv = db["economy_inventory"] if db is not None else None
    if col is None or client is None or ucol is None or inv is None:
        return await message.reply("❌ Economy database is unavailable.")
    item = await col.find_one({"item_id": item_id, "enabled": True, "gift": True})
    if not item:
        return await message.reply("❌ Gift not found or disabled.")
    price = int(item.get("price", 0))
    if price <= 0:
        return await message.reply("❌ Gift price is invalid.")

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                if int(item.get("stock", -1)) >= 0:
                    stock = await col.update_one(
                        {"item_id": item_id, "enabled": True, "gift": True, "stock": {"$gte": 1}},
                        {"$inc": {"stock": -1}},
                        session=session,
                    )
                    if stock.modified_count != 1:
                        await session.abort_transaction()
                        return await message.reply("❌ Gift is out of stock.")
                charged = await ucol.update_one(
                    {"_id": message.from_user.id, "coins": {"$gte": price}},
                    {"$inc": {"coins": -price}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    session=session,
                )
                if charged.modified_count != 1:
                    await session.abort_transaction()
                    return await message.reply("❌ Insufficient coins.")
                await inv.update_one(
                    {"user_id": target.id, "item_id": item_id},
                    {"$inc": {"quantity": 1},
                     "$set": {"name": item.get("name", item_id), "updated_at": datetime.now(timezone.utc)}},
                    upsert=True, session=session,
                )
                if db is not None:
                    await db["economy_gift_log"].insert_one(
                        {"from": message.from_user.id, "to": target.id, "item_id": item_id,
                         "price": price, "created_at": datetime.now(timezone.utc)},
                        session=session,
                    )
        return await message.reply(
            f"🎁 <b>{escape(str(item.get('name', item_id)))}</b> gifted to {_mention(target.id, _name(target))}!",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        return await message.reply("❌ Gift transaction could not be completed.")


# --------------------------- Owner shop management --------------------------

@app.on_message(filters.command("shopadd", prefixes=PREFIXES))
async def economy_shopadd(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) < 4:
        return await message.reply("❌ Usage: /shopadd <id> <price> <stock> <name>")
    try:
        item_id, price, stock = message.command[1], int(message.command[2]), int(message.command[3])
    except ValueError:
        return await message.reply("❌ Invalid price/stock.")
    name = " ".join(message.command[4:]).strip()
    if not name:
        return await message.reply("❌ Item name is required.")
    col = _shop_collection()
    now = datetime.now(timezone.utc)
    await col.update_one(
        {"item_id": item_id},
        {"$set": {"item_id": item_id, "name": name, "description": "",
                  "price": price, "stock": stock, "media_file_id": None,
                  "media_type": None, "gift": False, "enabled": True,
                  "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await message.reply(f"✅ Shop item <code>{escape(item_id)}</code> saved.", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("shopedit", prefixes=PREFIXES))
async def economy_shopedit(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) < 4:
        return await message.reply("❌ Usage: /shopedit <id> <name|description|price|stock> <value>")
    item_id, field = message.command[1], message.command[2].lower()
    if field not in {"name", "description", "price", "stock"}:
        return await message.reply("❌ Editable fields: name, description, price, stock")
    value = " ".join(message.command[3:]).strip()
    if field in {"price", "stock"}:
        try:
            value = int(value)
        except ValueError:
            return await message.reply("❌ Price/stock must be an integer.")
        if field == "price" and value < 0:
            return await message.reply("❌ Price cannot be negative.")
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": item_id},
        {"$set": {field: value, "updated_at": datetime.now(timezone.utc)}},
    )
    await message.reply("✅ Item updated." if result.modified_count else "❌ Item not found.")


@app.on_message(filters.command("shopmedia", prefixes=PREFIXES))
async def economy_shopmedia(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 2:
        return await message.reply("❌ Reply to a photo/GIF/video/animation with /shopmedia <id>.")
    reply = message.reply_to_message
    if not reply:
        return await message.reply("❌ Reply to the media you want to attach.")
    file_id = None
    media_type = None
    if reply.animation:
        file_id, media_type = reply.animation.file_id, "animation"
    elif reply.photo:
        file_id, media_type = reply.photo.file_id, "photo"
    elif reply.video:
        file_id, media_type = reply.video.file_id, "video"
    elif reply.document:
        file_id, media_type = reply.document.file_id, "document"
    if not file_id:
        return await message.reply("❌ Unsupported media. Use GIF/animation, photo, video or document.")
    col = _shop_collection()
    result = await col.update_one(
        {"item_id": message.command[1]},
        {"$set": {"media_file_id": file_id, "media_type": media_type,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    await message.reply("✅ Media attached." if result.modified_count else "❌ Item not found.")


@app.on_message(filters.command("shopremove", prefixes=PREFIXES))
async def economy_shopremove(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 2:
        return await message.reply("❌ Usage: /shopremove <id>")
    col = _shop_collection()
    result = await col.delete_one({"item_id": message.command[1]})
    await message.reply("✅ Removed." if result.deleted_count else "❌ Item not found.")


@app.on_message(filters.command("shopstock", prefixes=PREFIXES))
async def economy_shopstock(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 3:
        return await message.reply("❌ Usage: /shopstock <id> <stock> (-1 = unlimited)")
    try:
        stock = int(message.command[2])
    except ValueError:
        return await message.reply("❌ Invalid stock.")
    col = _shop_collection()
    result = await col.update_one({"item_id": message.command[1]}, {"$set": {"stock": stock, "updated_at": datetime.now(timezone.utc)}})
    await message.reply("✅ Stock updated." if result.modified_count else "❌ Item not found.")


@app.on_message(filters.command("shoptoggle", prefixes=PREFIXES))
async def economy_shoptoggle(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 3 or message.command[2].lower() not in {"on", "off"}:
        return await message.reply("❌ Usage: /shoptoggle <id> <on/off>")
    col = _shop_collection()
    result = await col.update_one({"item_id": message.command[1]}, {"$set": {"enabled": message.command[2].lower() == "on"}})
    await message.reply("✅ Updated." if result.modified_count else "❌ Item not found.")


@app.on_message(filters.command("shopgift", prefixes=PREFIXES))
async def economy_shopgift(_, message):
    if not await _is_owner(message):
        return
    if len(message.command or []) != 3 or message.command[2].lower() not in {"on", "off"}:
        return await message.reply("❌ Usage: /shopgift <id> <on/off>")
    col = _shop_collection()
    result = await col.update_one({"item_id": message.command[1]}, {"$set": {"gift": message.command[2].lower() == "on"}})
    await message.reply("✅ Gift mode updated." if result.modified_count else "❌ Item not found.")
