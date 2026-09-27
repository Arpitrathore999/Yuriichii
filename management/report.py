from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType

from core.bot import app
from database.mongo import db

PREFIXES = ["/", "!", "."]
REPORT_COMMANDS = ["report", "admin"]


def _settings():
    return db["report_settings"] if db is not None else None


def _mentions(users):
    out = []
    for u in users:
        if not u or not u.user:
            continue
        name = (u.user.first_name or "Admin").replace("<", "&lt;").replace(">", "&gt;")
        out.append(f'<a href="tg://user?id={u.user.id}">{name}</a>')
    return " ".join(out)


async def _is_admin(chat_id, user_id):
    try:
        m = await app.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _reports_enabled(chat_id):
    col = _settings()
    if col is None:
        return True
    doc = await col.find_one({"chat_id": chat_id})
    return bool(doc.get("enabled", True)) if doc else True


async def _set_reports(chat_id, enabled):
    col = _settings()
    if col is None:
        return False
    await col.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id, "enabled": enabled}}, upsert=True)
    return True


async def _admin_mentions(chat_id):
    admins = []
    async for member in app.get_chat_members(chat_id, filter="administrators"):
        if member.user and not member.user.is_bot:
            admins.append(member)
    return admins


async def _report(_, message):
    if not message.chat or message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not message.reply_to_message or not message.from_user:
        return

    if await _is_admin(message.chat.id, message.from_user.id):
        return

    target = message.reply_to_message.from_user
    if not target:
        return
    if target.id == message.from_user.id:
        return
    if await _is_admin(message.chat.id, target.id):
        return
    if not await _reports_enabled(message.chat.id):
        return

    admins = await _admin_mentions(message.chat.id)
    if not admins:
        return

    reporter = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name or "User"}</a>'
    reported = f'<a href="tg://user?id={target.id}">{target.first_name or "User"}</a>'
    link = ""
    try:
        link = f'\n<a href="{message.reply_to_message.link}">↗ Open Reported Message</a>' if message.reply_to_message.link else ""
    except Exception:
        pass

    text = (
        "🚨 <b>Rᴇᴘᴏʀᴛ</b>\n\n"
        f"👤 <b>Rᴇᴘᴏʀᴛᴇᴅ:</b> {reported}\n"
        f"🗣 <b>Rᴇᴘᴏʀᴛᴇᴅ Bʏ:</b> {reporter}"
        f"{link}\n\n"
        f"🛡️ <b>Aᴅᴍɪɴs:</b> {_mentions(admins)}"
    )
    await message.reply(text, disable_web_page_preview=True)


@app.on_message(filters.command(REPORT_COMMANDS, prefixes=PREFIXES))
async def report_handler(_, message):
    await _report(_, message)


@app.on_message(filters.regex(r"^(?:@admin)$", flags=0))
async def admin_report_handler(_, message):
    await _report(_, message)


@app.on_message(filters.command("reports", prefixes=PREFIXES))
async def reports_setting(_, message):
    if not message.chat or message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not message.from_user or not await _is_admin(message.chat.id, message.from_user.id):
        return

    args = message.command[1:] if message.command else []
    if not args:
        status = "ᴇɴᴀʙʟᴇᴅ" if await _reports_enabled(message.chat.id) else "ᴅɪsᴀʙʟᴇᴅ"
        return await message.reply(f"📢 <b>Rᴇᴘᴏʀᴛs:</b> {status}")

    value = args[0].lower()
    if value not in {"yes", "no", "on", "off"}:
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>/reports yes</code> or <code>/reports no</code>")
    enabled = value in {"yes", "on"}
    if not await _set_reports(message.chat.id, enabled):
        return await message.reply("❌ MᴏɴɢᴏDB ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")
    await message.reply("✅ Rᴇᴘᴏʀᴛs ᴇɴᴀʙʟᴇᴅ." if enabled else "🔕 Rᴇᴘᴏʀᴛs ᴅɪsᴀʙʟᴇᴅ.")
