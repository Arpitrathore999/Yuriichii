from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from core.bot import app
import config
from modules.social.settings import (
    COMMANDS,
    add_gif,
    add_caption,
    get_social_data,
    clear_gifs,
    clear_captions,
)


def owner_only(message):
    return bool(message.from_user and config.OWNER_ID and message.from_user.id == config.OWNER_ID)


async def can_manage_social(message):
    if owner_only(message):
        return True
    if not message.from_user or not message.chat:
        return False
    if message.chat.type == ChatType.PRIVATE:
        return False
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception as e:
        print(f"[SOCIAL ADMIN PERMISSION] {type(e).__name__}: {e}", flush=True)
        return False


async def deny(message):
    await message.reply("❌ You must be the group owner/admin to use this command.")


@app.on_message(filters.command("adminhelp"))
async def admin_help(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "🛠️ **Social Admin Commands**\n\n"
        "🎞️ **GIFs**\n"
        "• Reply to a GIF → `/addgif hug`\n"
        "• `/socialgifs hug` — count GIFs/captions\n"
        "• `/clearsocialgifs hug` — clear all GIFs\n\n"
        "📝 **Captions**\n"
        "• `/addcaption hug Your caption {a} {b}`\n"
        "• `/socialcaptions hug` — show caption count\n"
        "• `/clearsocialcaptions hug` — clear custom captions\n\n"
        "Available actions: " + ", ".join(f"`/{x}`" for x in COMMANDS)
    )


@app.on_message(filters.command("stats"))
async def stats(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply("📊 **Elara Stats**\n\nBot is online and modular.")


@app.on_message(filters.command("addgif"))
async def add_social_gif(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a GIF/animation with `/addgif hug`.")
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: reply to a GIF with `/addgif <command>`")

    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command. Use `/adminhelp` to see actions.")

    replied = message.reply_to_message
    media = replied.animation or replied.video or replied.document
    if not media:
        return await message.reply("❌ The replied message must contain a GIF/animation/video/document.")

    if await add_gif(command, media.file_id):
        data = await get_social_data(command)
        await message.reply(f"✅ GIF added to `/{command}`\n🎞️ Total GIFs: **{len(data['gifs'])}**")
    else:
        await message.reply("❌ MongoDB is unavailable. Check `MONGO_URI`.")


@app.on_message(filters.command("addcaption"))
async def add_social_caption(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 3:
        return await message.reply("❌ Usage: `/addcaption hug {a} hugged {b}! ❤️`")

    command = message.command[1].lower().lstrip("/")
    caption = message.text.split(None, 2)[2].strip()
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command. Use `/adminhelp`.")

    if await add_caption(command, caption):
        data = await get_social_data(command)
        await message.reply(f"✅ Caption added to `/{command}`\n📝 Total captions: **{len(data['captions'])}**")
    else:
        await message.reply("❌ MongoDB is unavailable. Check `MONGO_URI`.")


@app.on_message(filters.command("socialgifs"))
async def social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/socialgifs hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    data = await get_social_data(command)
    await message.reply(f"🎞️ `/{command}` GIFs: **{len(data['gifs'])}**\n📝 Captions: **{len(data['captions'])}**")


@app.on_message(filters.command("socialcaptions"))
async def social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/socialcaptions hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    data = await get_social_data(command)
    await message.reply(f"📝 `/{command}` has **{len(data['captions'])}** caption(s).")


@app.on_message(filters.command("clearsocialgifs"))
async def clear_social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/clearsocialgifs hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    ok = await clear_gifs(command)
    await message.reply("🗑️ Custom GIFs cleared." if ok else "❌ MongoDB is unavailable.")


@app.on_message(filters.command("clearsocialcaptions"))
async def clear_social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ Usage: `/clearsocialcaptions hug`")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ Invalid social command.")
    ok = await clear_captions(command)
    await message.reply("🗑️ Custom captions cleared." if ok else "❌ MongoDB is unavailable.")


# ══════════════════════════════════════════════════════════════════════════════
#  OWNER ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════
import asyncio
from datetime import datetime, timezone
from pyrogram import StopPropagation
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database.mongo import db
from database.users import (
    is_user_banned,
    set_user_banned,
    get_user,
    get_user_stats,
    get_users_page,
)
from database.broadcast import get_broadcast_count, get_broadcast_chats

_ADMIN_BROADCAST_WAIT = set()

def _panel_owner(message_or_query):
    user = getattr(message_or_query, "from_user", None)
    return bool(user and config.OWNER_ID and int(user.id) == int(config.OWNER_ID))

def _panel_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 DASHBOARD", callback_data="adm:dash"),
            InlineKeyboardButton("👥 USERS", callback_data="adm:users:0"),
        ],
        [
            InlineKeyboardButton("🚫 BANNED", callback_data="adm:banned:0"),
            InlineKeyboardButton("📢 BROADCAST", callback_data="adm:broadcast"),
        ],
        [
            InlineKeyboardButton("📡 BC STATS", callback_data="adm:bcstats"),
            InlineKeyboardButton("🗄 DATABASE", callback_data="adm:db"),
        ],
        [
            InlineKeyboardButton("🔄 REFRESH", callback_data="adm:dash"),
            InlineKeyboardButton("❌ CLOSE", callback_data="adm:close"),
        ],
    ])

def _user_name(doc):
    name = doc.get("first_name") or doc.get("username") or "Unknown"
    if doc.get("username"):
        return f"{name} (@{doc['username']})"
    return str(name)

def _dashboard_text(stats, bc):
    return (
        "╭━━━〔 👑 ᴇʟᴀʀᴀ ᴀᴅᴍɪɴ 〕━━━╮\n"
        "┃\n"
        f"┃ 👥 Users     : <code>{stats['total']}</code>\n"
        f"┃ 🟢 Active    : <code>{stats['active']}</code>\n"
        f"┃ 🚫 Banned    : <code>{stats['banned']}</code>\n"
        f"┃ 💬 Chats     : <code>{bc['total']}</code>\n"
        f"┃ 👥 Groups    : <code>{bc['groups']}</code>\n"
        f"┃ 📩 Private   : <code>{bc['private']}</code>\n"
        "┃\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Select an option below."
    )

async def _edit_panel(query, text, markup=_panel_kb()):
    try:
        await query.message.edit_text(text, reply_markup=markup)
    except Exception:
        try:
            await query.message.reply(text, reply_markup=markup)
        except Exception:
            pass

async def _show_users(query, page=0, banned_only=False):
    docs, total = await get_users_page(page, 8, banned_only=banned_only)
    title = "🚫 BANNED USERS" if banned_only else "👥 ALL USERS"
    lines = [f"<b>{title}</b>\n"]
    rows = []
    for d in docs:
        uid = int(d["_id"])
        name = _user_name(d)
        status = "🚫" if d.get("banned") else "🟢"
        lines.append(f"{status} <a href='tg://user?id={uid}'>{name}</a> — <code>{uid}</code>")
        if d.get("banned"):
            rows.append([InlineKeyboardButton(f"♻️ Unban {uid}", callback_data=f"adm:unban:{uid}")])
        else:
            rows.append([InlineKeyboardButton(f"🚫 Ban {uid}", callback_data=f"adm:ban:{uid}")])

    if not docs:
        lines.append("No users found.")
    nav=[]
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm:{'banned' if banned_only else 'users'}:{page-1}"))
    if (page+1)*8 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm:{'banned' if banned_only else 'users'}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ PANEL", callback_data="adm:dash")])
    await _edit_panel(query, "\n".join(lines), InlineKeyboardMarkup(rows))

@app.on_message(filters.command("adminpanel") & filters.user(config.OWNER_ID))
async def admin_panel(_, message):
    if not _panel_owner(message):
        return
    try:
        stats = await get_user_stats()
        bc = await get_broadcast_count()
        await message.reply(_dashboard_text(stats, bc), reply_markup=_panel_kb())
    except Exception as e:
        await message.reply(f"❌ Admin panel error: <code>{type(e).__name__}</code>")

@app.on_message(filters.command("adminuser") & filters.user(config.OWNER_ID))
async def admin_user_lookup(_, message):
    if not _panel_owner(message):
        return
    if len(message.command or []) < 2:
        return await message.reply("Usage: <code>/adminuser USER_ID</code>")
    try:
        uid = int(message.command[1])
    except ValueError:
        return await message.reply("❌ Invalid user ID.")
    doc = await get_user(uid)
    if not doc:
        return await message.reply("❌ User is not in the bot database.")
    banned = bool(doc.get("banned"))
    text = (
        f"👤 <b>User Details</b>\n\n"
        f"Name: <code>{doc.get('first_name','')}</code>\n"
        f"Username: <code>@{doc.get('username','')}</code>\n"
        f"ID: <code>{uid}</code>\n"
        f"Status: {'🚫 BANNED' if banned else '🟢 ACTIVE'}"
    )
    buttons = [[InlineKeyboardButton(
        "♻️ UNBAN" if banned else "🚫 PERMANENT BAN",
        callback_data=f"adm:{'unban' if banned else 'ban'}:{uid}"
    )],[InlineKeyboardButton("⬅️ PANEL", callback_data="adm:dash")]]
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^adm:"))
async def admin_panel_callback(_, query: CallbackQuery):
    if not _panel_owner(query):
        await query.answer("⛔ Owner only.", show_alert=True)
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "dash"
    await query.answer()
    if action == "close":
        try: await query.message.delete()
        except Exception: pass
        return
    if action == "dash":
        stats = await get_user_stats()
        bc = await get_broadcast_count()
        return await _edit_panel(query, _dashboard_text(stats, bc))
    if action == "users":
        return await _show_users(query, int(parts[2]) if len(parts)>2 else 0, False)
    if action == "banned":
        return await _show_users(query, int(parts[2]) if len(parts)>2 else 0, True)
    if action in ("ban", "unban"):
        uid = int(parts[2])
        if uid == int(config.OWNER_ID):
            return await query.answer("You cannot ban the owner.", show_alert=True)
        ok = await set_user_banned(uid, action == "ban", query.from_user.id)
        if not ok:
            return await query.answer("MongoDB is unavailable.", show_alert=True)
        await query.answer("User permanently banned." if action == "ban" else "User unbanned.", show_alert=True)
        stats = await get_user_stats()
        bc = await get_broadcast_count()
        return await _edit_panel(query, _dashboard_text(stats, bc))
    if action == "bcstats":
        bc = await get_broadcast_count()
        text = (
            "<b>📡 BROADCAST DATABASE</b>\n\n"
            f"Total chats: <code>{bc['total']}</code>\n"
            f"Groups: <code>{bc['groups']}</code>\n"
            f"Private users: <code>{bc['private']}</code>\n\n"
            "Use <code>/broadcast text</code> for the existing full broadcast system."
        )
        return await _edit_panel(query, text)
    if action == "db":
        state = "🟢 CONNECTED" if db is not None else "🔴 NOT CONFIGURED"
        if db is not None:
            try:
                await db.command("ping")
                state = "🟢 CONNECTED"
            except Exception:
                state = "🔴 CONNECTION ERROR"
        return await _edit_panel(query, f"<b>🗄 DATABASE STATUS</b>\n\nMongoDB: {state}")
    if action == "broadcast":
        _ADMIN_BROADCAST_WAIT.add(int(query.from_user.id))
        return await _edit_panel(
            query,
            "<b>📢 ADMIN BROADCAST</b>\n\n"
            "Send your next message here. Text, photo, video or document are supported.\n"
            "The message will be sent to all tracked private users and groups.\n\n"
            "Send <code>/cancelbroadcast</code> to cancel."
        )

@app.on_message(filters.command("cancelbroadcast") & filters.user(config.OWNER_ID))
async def cancel_admin_broadcast(_, message):
    _ADMIN_BROADCAST_WAIT.discard(int(message.from_user.id))
    await message.reply("❌ Admin broadcast cancelled.")

@app.on_message(filters.user(config.OWNER_ID), group=20)
async def admin_broadcast_message(client, message):
    uid = int(message.from_user.id) if message.from_user else 0
    if uid not in _ADMIN_BROADCAST_WAIT:
        return
    if message.text and message.text.startswith("/cancelbroadcast"):
        return
    _ADMIN_BROADCAST_WAIT.discard(uid)
    chats = await get_broadcast_chats()
    sent = failed = 0
    status = await message.reply("📢 Broadcasting started...")
    for doc in chats:
        cid = int(doc["chat_id"])
        try:
            if message.text:
                await client.send_message(cid, message.text)
            elif message.photo:
                await client.send_photo(cid, message.photo.file_id, caption=message.caption or "")
            elif message.video:
                await client.send_video(cid, message.video.file_id, caption=message.caption or "")
            elif message.document:
                await client.send_document(cid, message.document.file_id, caption=message.caption or "")
            else:
                await client.copy_message(cid, message.chat.id, message.id)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(
        f"📢 <b>Broadcast finished</b>\n\n"
        f"✅ Sent: <code>{sent}</code>\n"
        f"❌ Failed: <code>{failed}</code>\n"
        f"📦 Targets: <code>{len(chats)}</code>"
    )

# Global ban guard. Owner is always exempt.
@app.on_message(filters.all, group=-100)
async def banned_user_guard(_, message):
    if not message.from_user or _panel_owner(message):
        return
    if await is_user_banned(message.from_user.id):
        try:
            await message.reply("🚫 <b>You are permanently banned from using this bot.</b>")
        except Exception:
            pass
        raise StopPropagation

@app.on_callback_query(group=-100)
async def banned_callback_guard(_, query):
    if not query.from_user or _panel_owner(query):
        return
    if await is_user_banned(query.from_user.id):
        await query.answer("🚫 You are permanently banned from using this bot.", show_alert=True)
        raise StopPropagation
