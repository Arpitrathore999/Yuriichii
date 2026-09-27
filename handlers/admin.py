# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/admin.py — Premium Owner Panel + Social Admin
# --------------------------------------------------------------------------------

from pyrogram import enums, filters, StopPropagation
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from core.bot import app

from modules.social.settings import (
    COMMANDS,
    add_gif,
    add_caption,
    get_social_data,
    clear_gifs,
    clear_captions,
)

from utils.rich_ui import (
    rich_esc,
    rich_heading,
    rich_note,
    rich_kv_table,
    rich_table,
    rich_send,
    rich_edit,
)

import asyncio
from database.mongo import db
from database.users import (
    is_user_banned,
    set_user_banned,
    get_user,
    get_user_stats,
    get_users_page,
    get_active_user_ids,
)
from database.broadcast import get_broadcast_count, get_broadcast_chats


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def owner_only(message):
    return bool(
        message.from_user
        and config.OWNER_ID
        and message.from_user.id == config.OWNER_ID
    )


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
    await message.reply(
        "🚫 <b>ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ</b>\n\n"
        "<i>ʏᴏᴜ ᴍᴜsᴛ ʙᴇ ᴛʜᴇ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ/ᴀᴅᴍɪɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</i>"
    )


def _btn(text, callback_data, style=enums.ButtonStyle.PRIMARY):
    return InlineKeyboardButton(text, callback_data=callback_data, style=style)


def _user_name(doc):
    first = (doc.get("first_name") or "Unknown").strip()
    username = (doc.get("username") or "").strip()
    return f"{first} (@{username})" if username else first


# ══════════════════════════════════════════════════════════════════════════════
#  SOCIAL ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("adminhelp"))
async def admin_help(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "🛠️ <b>sᴏᴄɪᴀʟ ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs</b>\n\n"
        "🎞️ <b>ɢɪғs</b>\n"
        "• ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪғ → <code>/addgif hug</code>\n"
        "• <code>/socialgifs hug</code> — ᴄᴏᴜɴᴛ ɢɪғs/ᴄᴀᴘᴛɪᴏɴs\n"
        "• <code>/clearsocialgifs hug</code> — ᴄʟᴇᴀʀ ᴀʟʟ ɢɪғs\n\n"
        "📝 <b>ᴄᴀᴘᴛɪᴏɴs</b>\n"
        "• <code>/addcaption hug Your caption {a} {b}</code>\n"
        "• <code>/socialcaptions hug</code> — sʜᴏᴡ ᴄᴀᴘᴛɪᴏɴ ᴄᴏᴜɴᴛ\n"
        "• <code>/clearsocialcaptions hug</code> — ᴄʟᴇᴀʀ ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴs\n\n"
        "ᴀᴠᴀɪʟᴀʙʟᴇ ᴀᴄᴛɪᴏɴs: " + ", ".join(f"<code>/{x}</code>" for x in COMMANDS)
    )


@app.on_message(filters.command("stats"))
async def stats(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "📊 <b>ᴇʟᴀʀᴀ sᴛᴀᴛs</b>\n\n<i>ʙᴏᴛ ɪs ᴏɴʟɪɴᴇ ᴀɴᴅ ᴍᴏᴅᴜʟᴀʀ.</i>"
    )


@app.on_message(filters.command("addgif"))
async def add_social_gif(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if not message.reply_to_message:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪғ/ᴀɴɪᴍᴀᴛɪᴏɴ ᴡɪᴛʜ <code>/addgif hug</code>.")
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜsᴀɢᴇ: ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪғ ᴡɪᴛʜ <code>/addgif &lt;command&gt;</code>")

    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ. ᴜsᴇ <code>/adminhelp</code>.")

    replied = message.reply_to_message
    media = replied.animation or replied.video or replied.document
    if not media:
        return await message.reply("❌ ᴛʜᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ᴍᴜsᴛ ᴄᴏɴᴛᴀɪɴ ᴀ ɢɪғ/ᴀɴɪᴍᴀᴛɪᴏɴ/ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ.")

    if await add_gif(command, media.file_id):
        data = await get_social_data(command)
        await message.reply(
            f"✅ ɢɪғ ᴀᴅᴅᴇᴅ ᴛᴏ <code>/{command}</code>\n"
            f"🎞️ ᴛᴏᴛᴀʟ ɢɪғs: <b>{len(data['gifs'])}</b>"
        )
    else:
        await message.reply("❌ ᴍᴏɴɢᴏᴅʙ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴄʜᴇᴄᴋ <code>MONGO_URI</code>.")


@app.on_message(filters.command("addcaption"))
async def add_social_caption(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 3:
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>/addcaption hug {a} hugged {b}! ❤️</code>")

    command = message.command[1].lower().lstrip("/")
    caption = message.text.split(None, 2)[2].strip()
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ. ᴜsᴇ <code>/adminhelp</code>.")

    if await add_caption(command, caption):
        data = await get_social_data(command)
        await message.reply(
            f"✅ ᴄᴀᴘᴛɪᴏɴ ᴀᴅᴅᴇᴅ ᴛᴏ <code>/{command}</code>\n"
            f"📝 ᴛᴏᴛᴀʟ ᴄᴀᴘᴛɪᴏɴs: <b>{len(data['captions'])}</b>"
        )
    else:
        await message.reply("❌ ᴍᴏɴɢᴏᴅʙ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴄʜᴇᴄᴋ <code>MONGO_URI</code>.")


@app.on_message(filters.command("socialgifs"))
async def social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>/socialgifs hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    data = await get_social_data(command)
    await message.reply(
        f"🎞️ <code>/{command}</code> ɢɪғs: <b>{len(data['gifs'])}</b>\n"
        f"📝 ᴄᴀᴘᴛɪᴏɴs: <b>{len(data['captions'])}</b>"
    )


@app.on_message(filters.command("socialcaptions"))
async def social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>/socialcaptions hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    data = await get_social_data(command)
    await message.reply(
        f"📝 <code>/{command}</code> ʜᴀs <b>{len(data['captions'])}</b> ᴄᴀᴘᴛɪᴏɴ(s)."
    )


@app.on_message(filters.command("clearsocialgifs"))
async def clear_social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>/clearsocialgifs hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    ok = await clear_gifs(command)
    await message.reply("🗑️ ᴄᴜsᴛᴏᴍ ɢɪғs ᴄʟᴇᴀʀᴇᴅ." if ok else "❌ ᴍᴏɴɢᴏᴅʙ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")


@app.on_message(filters.command("clearsocialcaptions"))
async def clear_social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>/clearsocialcaptions hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    ok = await clear_captions(command)
    await message.reply("🗑️ ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴs ᴄʟᴇᴀʀᴇᴅ." if ok else "❌ ᴍᴏɴɢᴏᴅʙ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")


# ══════════════════════════════════════════════════════════════════════════════
#  OWNER ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

_ADMIN_BROADCAST_WAIT = {}


def _panel_owner(message_or_query):
    user = getattr(message_or_query, "from_user", None)
    return bool(user and config.OWNER_ID and int(user.id) == int(config.OWNER_ID))


def _panel_kb():
    return InlineKeyboardMarkup([
        [_btn("📊 ᴅᴀsʜʙᴏᴀʀᴅ", "adm:dash", enums.ButtonStyle.PRIMARY),
         _btn("👥 ᴜsᴇʀs", "adm:users:0", enums.ButtonStyle.SUCCESS)],
        [_btn("🚫 ʙᴀɴɴᴇᴅ", "adm:banned:0", enums.ButtonStyle.DANGER),
         _btn("📢 ʙʀᴏᴀᴅᴄᴀsᴛ", "adm:bcmenu", enums.ButtonStyle.PRIMARY)],
        [_btn("📡 ʙᴄ sᴛᴀᴛs", "adm:bcstats", enums.ButtonStyle.SUCCESS),
         _btn("🗄 ᴅᴀᴛᴀʙᴀsᴇ", "adm:db", enums.ButtonStyle.PRIMARY)],
        [_btn("🔄 ʀᴇғʀᴇsʜ", "adm:dash", enums.ButtonStyle.PRIMARY),
         _btn("❌ ᴄʟᴏsᴇ", "adm:close", enums.ButtonStyle.DANGER)],
    ])


def _broadcast_kb():
    return InlineKeyboardMarkup([
        [_btn("📣 ᴀʟʟ ᴄʜᴀᴛs", "adm:bcmode:all", enums.ButtonStyle.PRIMARY)],
        [_btn("👤 ᴘʀɪᴠᴀᴛᴇ ᴜsᴇʀs", "adm:bcmode:private", enums.ButtonStyle.SUCCESS),
         _btn("👥 ɢʀᴏᴜᴘs", "adm:bcmode:groups", enums.ButtonStyle.SUCCESS)],
        [_btn("🟢 ᴀᴄᴛɪᴠᴇ 7ᴅ", "adm:bcmode:active", enums.ButtonStyle.PRIMARY),
         _btn("🎯 sᴇʟᴇᴄᴛᴇᴅ ɪᴅs", "adm:bcmode:selected", enums.ButtonStyle.PRIMARY)],
        [_btn("⬅️ ʜᴏᴍᴇ", "adm:dash", enums.ButtonStyle.PRIMARY)],
    ])


def _dashboard_text(stats, bc):
    return (
        rich_heading("👑 ᴇʟᴀʀᴀ ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ", level=2)
        + "<i>ᴘᴏᴡᴇʀ & ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ</i>\n\n"
        + rich_kv_table([
            ("👥 ᴜsᴇʀs",       f"<code>{stats['total']}</code>"),
            ("🟢 ᴀᴄᴛɪᴠᴇ",       f"<code>{stats['active']}</code>"),
            ("🚫 ʙᴀɴɴᴇᴅ",       f"<code>{stats['banned']}</code>"),
            ("💬 ᴛᴏᴛᴀʟ ᴄʜᴀᴛs",  f"<code>{bc['total']}</code>"),
            ("👥 ɢʀᴏᴜᴘs",        f"<code>{bc['groups']}</code>"),
            ("📩 ᴘʀɪᴠᴀᴛᴇ",       f"<code>{bc['private']}</code>"),
        ], headers=["sᴛᴀᴛᴜs", "ᴠᴀʟᴜᴇ"])
        + "\n"
        + rich_note("💡 ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴍᴀɴᴀɢᴇ ᴜsᴇʀs, ʙᴀɴs & ʙʀᴏᴀᴅᴄᴀsᴛs.")
    )


async def _edit_panel(query, text, markup=None):
    markup = markup or _panel_kb()
    try:
        return await rich_edit(query, text, reply_markup=markup)
    except Exception:
        try:
            return await query.message.edit_text(text, reply_markup=markup)
        except Exception:
            return None


async def _show_users(query, page=0, banned_only=False):
    docs, total = await get_users_page(page, 8, banned_only=banned_only)
    title = "🚫 ʙᴀɴɴᴇᴅ ᴜsᴇʀs" if banned_only else "👥 ʙᴏᴛ ᴜsᴇʀs"
    rows = []
    buttons = []
    for d in docs:
        uid = int(d["_id"])
        name = rich_esc(_user_name(d))
        status = "🚫 ʙᴀɴɴᴇᴅ" if d.get("banned") else "🟢 ᴀᴄᴛɪᴠᴇ"
        rows.append((
            f'<a href="tg://user?id={uid}">{name}</a>',
            f"<code>{uid}</code>",
            status,
        ))
        buttons.append([_btn(
            f"♻️ ᴜɴʙᴀɴ {uid}" if d.get("banned") else f"🚫 ʙᴀɴ {uid}",
            f"adm:{'unban' if d.get('banned') else 'ban'}:{uid}",
            enums.ButtonStyle.SUCCESS if d.get("banned") else enums.ButtonStyle.DANGER,
        )])
    if not docs:
        rows.append(("—", "—", "ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ"))
    text = (
        rich_heading(title, level=3)
        + f"<i>ᴛᴏᴛᴀʟ: {total} • ᴘᴀɢᴇ: {page + 1}</i>\n\n"
        + rich_table(["ᴜsᴇʀ", "ɪᴅ", "sᴛᴀᴛᴜs"], rows)
    )
    nav = []
    prefix = "banned" if banned_only else "users"
    if page > 0:
        nav.append(_btn("‹ ᴘʀᴇᴠ", f"adm:{prefix}:{page-1}", enums.ButtonStyle.PRIMARY))
    if (page + 1) * 8 < total:
        nav.append(_btn("ɴᴇxᴛ ›", f"adm:{prefix}:{page+1}", enums.ButtonStyle.PRIMARY))
    if nav:
        buttons.append(nav)
    buttons.append([_btn("⬅️ ʜᴏᴍᴇ", "adm:dash", enums.ButtonStyle.PRIMARY)])
    return await _edit_panel(query, text, InlineKeyboardMarkup(buttons))


# ══════════════════════════════════════════════════════════════════════════════
#  PANEL COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("adminpanel"))
async def admin_panel(_, message):
    if not _panel_owner(message):
        return await message.reply(
            "⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>\n\n"
            "<i>ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ.</i>"
        )
    stats = await get_user_stats()
    bc = await get_broadcast_count()
    await rich_send(
        app, message.chat.id,
        _dashboard_text(stats, bc),
        reply_markup=_panel_kb(),
        reply_to_message_id=message.id,
    )


@app.on_message(filters.command("adminuser"))
async def admin_user_lookup(_, message):
    if not _panel_owner(message):
        return await message.reply("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>")
    if len(message.command or []) < 2:
        return await message.reply("ᴜsᴀɢᴇ: <code>/adminuser USER_ID</code>")
    try:
        uid = int(message.command[1])
    except ValueError:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴜsᴇʀ ɪᴅ.")
    doc = await get_user(uid)
    if not doc:
        return await message.reply("❌ ᴜsᴇʀ ɪs ɴᴏᴛ ɪɴ ᴛʜᴇ ʙᴏᴛ ᴅᴀᴛᴀʙᴀsᴇ.")
    banned = bool(doc.get("banned"))
    joined = doc.get("joined_at")
    last_seen = doc.get("last_seen")
    text = (
        rich_heading("👤 ᴜsᴇʀ ᴅᴇᴛᴀɪʟs", level=3)
        + rich_kv_table([
            ("ɴᴀᴍᴇ",      rich_esc(_user_name(doc))),
            ("ɪᴅ",        f"<code>{uid}</code>"),
            ("sᴛᴀᴛᴜs",    "🚫 ʙᴀɴɴᴇᴅ" if banned else "🟢 ᴀᴄᴛɪᴠᴇ"),
            ("ᴊᴏɪɴᴇᴅ",     f"<code>{joined.strftime('%Y-%m-%d') if joined else '—'}</code>"),
            ("ʟᴀsᴛ sᴇᴇɴ", f"<code>{last_seen.strftime('%Y-%m-%d %H:%M') if last_seen else '—'}</code>"),
        ], headers=["ғɪᴇʟᴅ", "ᴠᴀʟᴜᴇ"])
    )
    buttons = [[InlineKeyboardButton(
        "♻️ ᴜɴʙᴀɴ" if banned else "🚫 ᴘᴇʀᴍᴀɴᴇɴᴛ ʙᴀɴ",
        callback_data=f"adm:{'unban' if banned else 'ban'}:{uid}"
    )], [InlineKeyboardButton("⬅️ ᴘᴀɴᴇʟ", callback_data="adm:dash")]]
    await rich_send(
        app, message.chat.id, text,
        reply_markup=InlineKeyboardMarkup(buttons),
        reply_to_message_id=message.id,
    )


async def _direct_ban(message, banned: bool):
    if not _panel_owner(message):
        return await message.reply("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>")
    if len(message.command or []) < 2:
        return await message.reply(
            f"ᴜsᴀɢᴇ: <code>/{'banbot' if banned else 'botunban'} USER_ID</code>"
        )
    try:
        uid = int(message.command[1])
    except ValueError:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴜsᴇʀ ɪᴅ.")
    if uid == int(config.OWNER_ID):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴɴᴏᴛ ʙᴀɴ/ᴜɴʙᴀɴ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ.")
    ok = await set_user_banned(uid, banned, message.from_user.id)
    if not ok:
        return await message.reply("❌ ᴍᴏɴɢᴏᴅʙ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴄʜᴇᴄᴋ <code>MONGO_URI</code>.")
    if banned:
        return await message.reply(
            f"🚫 <b>ᴜsᴇʀ ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ ʙᴀɴɴᴇᴅ.</b>\n\n🆔 <code>{uid}</code>\n\n"
            "<i>ᴛʜᴇ ʙᴀɴ ɪs sᴛᴏʀᴇᴅ ɪɴ ᴍᴏɴɢᴏᴅʙ ᴀɴᴅ sᴜʀᴠɪᴠᴇs ʙᴏᴛ ʀᴇsᴛᴀʀᴛs.</i>"
        )
    return await message.reply(f"♻️ <b>ᴜsᴇʀ ᴜɴʙᴀɴɴᴇᴅ.</b>\n\n🆔 <code>{uid}</code>")


@app.on_message(filters.command("banbot"))
async def banbot(_, message):
    return await _direct_ban(message, True)


@app.on_message(filters.command("botunban"))
async def botunban(_, message):
    return await _direct_ban(message, False)


# ══════════════════════════════════════════════════════════════════════════════
#  PANEL CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_callback_query(filters.regex(r"^adm:"))
async def admin_panel_callback(_, query: CallbackQuery):
    if not _panel_owner(query):
        await query.answer("⛔ ᴏᴡɴᴇʀ ᴏɴʟʏ.", show_alert=True)
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "dash"
    await query.answer()

    if action == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "dash":
        return await _edit_panel(
            query,
            _dashboard_text(await get_user_stats(), await get_broadcast_count())
        )

    if action == "users":
        return await _show_users(query, int(parts[2]) if len(parts) > 2 else 0, False)

    if action == "banned":
        return await _show_users(query, int(parts[2]) if len(parts) > 2 else 0, True)

    if action in ("ban", "unban"):
        uid = int(parts[2])
        if uid == int(config.OWNER_ID):
            return await query.answer("ʏᴏᴜ ᴄᴀɴɴᴏᴛ ʙᴀɴ ᴛʜᴇ ᴏᴡɴᴇʀ.", show_alert=True)
        ok = await set_user_banned(uid, action == "ban", query.from_user.id)
        if not ok:
            return await query.answer("ᴍᴏɴɢᴏᴅʙ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
        await query.answer(
            "ᴜsᴇʀ ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ ʙᴀɴɴᴇᴅ." if action == "ban" else "ᴜsᴇʀ ᴜɴʙᴀɴɴᴇᴅ.",
            show_alert=True,
        )
        return await _edit_panel(
            query,
            _dashboard_text(await get_user_stats(), await get_broadcast_count())
        )

    if action == "bcmenu":
        return await _edit_panel(
            query,
            rich_heading("📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴇɴᴛᴇʀ", level=3)
            + rich_note(
                "ᴄʜᴏᴏsᴇ ᴡʜᴇʀᴇ ᴛʜᴇ ɴᴇxᴛ ʙʀᴏᴀᴅᴄᴀsᴛ sʜᴏᴜʟᴅ ɢᴏ.\n\n"
                "🎯 sᴇʟᴇᴄᴛᴇᴅ ɪᴅs ᴀᴄᴄᴇᴘᴛs ᴜsᴇʀ/ᴄʜᴀᴛ ɪᴅs sᴇᴘᴀʀᴀᴛᴇᴅ ʙʏ sᴘᴀᴄᴇs ᴏʀ ᴄᴏᴍᴍᴀs."
            ),
            _broadcast_kb(),
        )

    if action == "bcmode":
        mode = parts[2] if len(parts) > 2 else "all"
        uid = int(query.from_user.id)
        if mode == "selected":
            _ADMIN_BROADCAST_WAIT[uid] = {"mode": "selected_ids"}
            return await _edit_panel(
                query,
                rich_heading("🎯 sᴇʟᴇᴄᴛᴇᴅ ɪᴅs", level=3)
                + rich_note(
                    "sᴇɴᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴜsᴇʀ/ᴄʜᴀᴛ ɪᴅs sᴇᴘᴀʀᴀᴛᴇᴅ ʙʏ sᴘᴀᴄᴇs ᴏʀ ᴄᴏᴍᴍᴀs.\n\n"
                    "ᴇxᴀᴍᴘʟᴇ: <code>123456789, 987654321</code>"
                ),
                InlineKeyboardMarkup([[
                    _btn("❌ ᴄᴀɴᴄᴇʟ", "adm:bccancel", enums.ButtonStyle.DANGER)
                ]]),
            )
        _ADMIN_BROADCAST_WAIT[uid] = {"mode": mode}
        label = {
            "all": "ᴀʟʟ ᴄʜᴀᴛs",
            "private": "ᴘʀɪᴠᴀᴛᴇ ᴜsᴇʀs",
            "groups": "ɢʀᴏᴜᴘs",
            "active": "ᴀᴄᴛɪᴠᴇ ᴜsᴇʀs (ʟᴀsᴛ 7 ᴅᴀʏs)",
        }.get(mode, mode)
        return await _edit_panel(
            query,
            rich_heading(f"📢 {label.upper()}", level=3)
            + rich_note(
                "sᴇɴᴅ ᴛʜᴇ ᴍᴇssᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ.\n\n"
                "ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴀɴɪᴍᴀᴛɪᴏɴ & ғᴏʀᴡᴀʀᴅᴇᴅ ᴍᴇᴅɪᴀ sᴜᴘᴘᴏʀᴛᴇᴅ.\n\n"
                "<code>/cancelbroadcast</code> ᴛᴏ ᴄᴀɴᴄᴇʟ."
            ),
            InlineKeyboardMarkup([[
                _btn("❌ ᴄᴀɴᴄᴇʟ", "adm:bccancel", enums.ButtonStyle.DANGER)
            ]]),
        )

    if action == "bccancel":
        _ADMIN_BROADCAST_WAIT.pop(int(query.from_user.id), None)
        return await _edit_panel(
            query,
            rich_heading("📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴇɴᴛᴇʀ", level=3)
            + rich_note("ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ."),
            _broadcast_kb(),
        )

    if action == "bcstats":
        bc = await get_broadcast_count()
        return await _edit_panel(
            query,
            rich_heading("📡 ʙʀᴏᴀᴅᴄᴀsᴛ sᴛᴀᴛs", level=3)
            + rich_kv_table([
                ("💬 ᴛᴏᴛᴀʟ",  f"<code>{bc['total']}</code>"),
                ("👥 ɢʀᴏᴜᴘs", f"<code>{bc['groups']}</code>"),
                ("📩 ᴘʀɪᴠᴀᴛᴇ", f"<code>{bc['private']}</code>"),
            ], headers=["ᴍᴇᴛʀɪᴄ", "ᴠᴀʟᴜᴇ"])
        )

    if action == "db":
    state = "🟢 ᴄᴏɴɴᴇᴄᴛᴇᴅ" if db is not None else "🔴 ɴᴏᴛ ᴄᴏɴғɪɢᴜʀᴇᴅ"
    if db is not None:
        try:
            await db.command("ping")
        except Exception:
            state = "🔴 ᴄᴏɴɴᴇᴄᴛɪᴏɴ ᴇʀʀᴏʀ"
    return await _edit_panel(
        query,
        rich_heading("🗄 ᴅᴀᴛᴀʙᴀsᴇ sᴛᴀᴛᴜs", level=3)
        + rich_kv_table([("ᴍᴏɴɢᴏᴅʙ", state)], headers=["sᴇʀᴠɪᴄᴇ", "sᴛᴀᴛᴜs"])
    )
