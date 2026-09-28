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
#  GROUP ADMIN MANAGEMENT
#  Supports / ! . prefixes for every management command.
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_PREFIXES = ["/", "!", "."]
ADMIN_RIGHTS = {
    "info": "can_change_info",
    "delete": "can_delete_messages",
    "ban": "can_restrict_members",
    "invite": "can_invite_users",
    "pin": "can_pin_messages",
    "stream": "can_manage_video_chats",
    "addadmins": "can_promote_members",
    "anon": "is_anonymous",
    # Elara custom rights (stored in MongoDB; used by later management modules).
    "tags": None,
    "welcome": None,
    "stories": None,
}

PROMOTE_MODES = {
    0: ("Tᴇᴍᴘ Aᴅᴍɪɴ", set()),
    1: ("Jᴜɴɪᴏʀ Aᴅᴍɪɴ", {"delete", "invite", "pin"}),
    2: ("Aꜱꜱɪꜱᴛᴀɴᴛ Aᴅᴍɪɴ", {"delete", "invite", "pin", "info", "ban"}),
    3: ("Fᴜʟʟ Aᴅᴍɪɴ", set(ADMIN_RIGHTS.keys())),
}


def _management_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _management_admin(message):
    if not _management_group(message) or not message.from_user:
        return False
    if int(message.from_user.id) == int(config.OWNER_ID):
        return True
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _can_promote(message):
    if not await _management_admin(message):
        return False
    if int(message.from_user.id) == int(config.OWNER_ID):
        return True
    try:
        member = await app.get_chat_member(message.chat.id, message.from_user.id)
        if member.status == ChatMemberStatus.OWNER:
            return True
        # Telegram's real permission is the final authority for promotion.
        return bool(getattr(member, "privileges", None) and getattr(member.privileges, "can_promote_members", False))
    except Exception:
        return False


async def _can_edit_target(message, target_id):
    if int(target_id) == int(config.OWNER_ID):
        return False
    try:
        actor = await app.get_chat_member(message.chat.id, message.from_user.id)
        target = await app.get_chat_member(message.chat.id, target_id)
        if target.status == ChatMemberStatus.OWNER:
            return False
        if actor.status == ChatMemberStatus.OWNER:
            return True
        if actor.status != ChatMemberStatus.ADMINISTRATOR:
            return False
        if target.status == ChatMemberStatus.ADMINISTRATOR:
            # Telegram only lets admins manage admins below their own rank.
            return bool(getattr(actor, "privileges", None) and getattr(actor.privileges, "can_promote_members", False))
        return True
    except Exception:
        return False


def _mention(user, fallback="User"):
    uid = int(getattr(user, "id", 0) or 0)
    name = rich_esc(getattr(user, "first_name", None) or fallback)
    return f'<a href="tg://user?id={uid}">{name}</a>' if uid else name


async def _resolve_target(message, args):
    """Resolve reply, @username, Telegram ID, or text-mention target."""
    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user

    text = message.text or ""
    entities = list(message.entities or [])
    for entity in entities:
        if str(entity.type) in ("MessageEntityType.TEXT_MENTION", "text_mention") and getattr(entity, "user", None):
            return entity.user

    candidates = [str(x).strip() for x in args if str(x).strip()]
    for raw in candidates:
        if raw.lstrip("+-").isdigit():
            try:
                return await app.get_users(int(raw))
            except Exception:
                continue
        if raw.startswith("@"):
            try:
                return await app.get_users(raw)
            except Exception:
                continue
    return None


async def _admin_right_doc(chat_id, user_id):
    if db is None:
        return None
    return await db["admin_rights"].find_one({"chat_id": int(chat_id), "user_id": int(user_id)})


async def _save_admin_rights(chat_id, user_id, rights, mode=None):
    if db is None:
        return False
    doc = {
        "chat_id": int(chat_id),
        "user_id": int(user_id),
        "rights": sorted(set(rights)),
        "updated_at": __import__("datetime").datetime.utcnow(),
    }
    if mode is not None:
        doc["mode"] = int(mode)
    await db["admin_rights"].update_one(
        {"chat_id": int(chat_id), "user_id": int(user_id)},
        {"$set": doc},
        upsert=True,
    )
    return True


async def _apply_telegram_rights(chat_id, user_id, rights):
    """Apply rights that Telegram exposes as actual administrator privileges."""
    from pyrogram.types import ChatPrivileges

    kwargs = {
        "can_change_info": "info" in rights,
        "can_delete_messages": "delete" in rights,
        "can_restrict_members": "ban" in rights,
        "can_invite_users": "invite" in rights,
        "can_pin_messages": "pin" in rights,
        "can_manage_video_chats": "stream" in rights,
        "can_promote_members": "addadmins" in rights,
        "is_anonymous": "anon" in rights,
    }
    await app.promote_chat_member(chat_id, user_id, privileges=ChatPrivileges(**kwargs))


async def _promote_target(message, target, mode):
    rights = set(PROMOTE_MODES[mode][1])
    # Mode 3 means every Elara right. Telegram receives the supported subset.
    await app.promote_chat_member(
        message.chat.id,
        target.id,
        privileges=__import__("pyrogram.types", fromlist=["ChatPrivileges"]).ChatPrivileges(
            can_change_info="info" in rights,
            can_delete_messages="delete" in rights,
            can_restrict_members="ban" in rights,
            can_invite_users="invite" in rights,
            can_pin_messages="pin" in rights,
            can_manage_video_chats="stream" in rights,
            can_promote_members="addadmins" in rights,
            is_anonymous="anon" in rights,
        ),
    )
    if not await _save_admin_rights(message.chat.id, target.id, rights, mode):
        return False
    return True


async def _parse_promote(message):
    parts = list(message.command or [])[1:]
    if not parts:
        return None, None, "usage"
    try:
        mode = int(parts[-1])
    except (TypeError, ValueError):
        return None, None, "mode"
    if mode not in PROMOTE_MODES:
        return None, mode, "invalid_mode"
    target = await _resolve_target(message, parts[:-1])
    if not target:
        return None, mode, "target"
    return target, mode, None


@app.on_message(filters.command("promote", prefixes=ADMIN_PREFIXES))
async def group_promote(_, message):
    if not _management_group(message):
        return
    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴘʀᴏᴍᴏᴛᴇ ᴀᴅᴍɪɴs.")

    target, mode, error = await _parse_promote(message)
    if error == "usage":
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>.promote @username 0-3</code>")
    if error == "mode":
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴍᴏᴅᴇ. ᴜsᴇ <code>0</code>, <code>1</code>, <code>2</code> ᴏʀ <code>3</code>.")
    if error == "invalid_mode":
        return await message.reply(
            "❌ ɪɴᴠᴀʟɪᴅ ᴍᴏᴅᴇ. ᴀᴠᴀɪʟᴀʙʟᴇ: <code>0</code> • <code>1</code> • <code>2</code> • <code>3</code>."
        )
    if error == "target":
        return await message.reply("❌ ᴜsᴇ ᴀ ʀᴇᴘʟʏ, <code>@username</code> ᴏʀ ᴜsᴇʀ ɪᴅ.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴀᴅᴍɪɴ.")

    try:
        await _promote_target(message, target, mode)
    except Exception as e:
        print(f"[PROMOTE] {type(e).__name__}: {e}", flush=True)
        return await message.reply("❌ ᴄᴏᴜʟᴅɴ'ᴛ ᴘʀᴏᴍᴏᴛᴇ ᴛʜɪs ᴜsᴇʀ. ᴄʜᴇᴄᴋ ᴛʜᴇ ʙᴏᴛ's ᴀᴅᴍɪɴ ʀɪɢʜᴛs.")

    role = PROMOTE_MODES[mode][0]
    return await message.reply(f"{_mention(target)} 🕊 Pʀᴏᴍᴏᴛᴇᴅ Tᴏ 🏅 {role}.")


@app.on_message(filters.command("demote", prefixes=ADMIN_PREFIXES))
async def group_demote(_, message):
    if not _management_group(message):
        return
    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴅᴇᴍᴏᴛᴇ ᴀᴅᴍɪɴs.")
    args = list(message.command or [])[1:]
    target = await _resolve_target(message, args)
    if not target:
        return await message.reply("❌ ᴜsᴇ ᴀ ʀᴇᴘʟʏ, <code>@username</code> ᴏʀ ᴜsᴇʀ ɪᴅ.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴀᴅᴍɪɴ.")
    try:
        from pyrogram.types import ChatPrivileges
        await app.promote_chat_member(message.chat.id, target.id, privileges=ChatPrivileges())
        if db is not None:
            await db["admin_rights"].delete_one({"chat_id": int(message.chat.id), "user_id": int(target.id)})
    except Exception as e:
        print(f"[DEMOTE] {type(e).__name__}: {e}", flush=True)
        return await message.reply("❌ ᴄᴏᴜʟᴅɴ'ᴛ ᴅᴇᴍᴏᴛᴇ ᴛʜɪs ᴜsᴇʀ.")
    return await message.reply(f"{_mention(target)} 🕊 Dᴇᴍᴏᴛᴇᴅ Tᴏ 👤 Mᴇᴍʙᴇʀ.")


@app.on_message(filters.command("adminlist", prefixes=ADMIN_PREFIXES))
async def group_adminlist(_, message):
    if not _management_group(message):
        return
    try:
        admins = []
        async for member in app.get_chat_members(message.chat.id, filter=__import__("pyrogram.enums", fromlist=["ChatMembersFilter"]).ChatMembersFilter.ADMINISTRATORS):
            if member.user:
                admins.append(member)
        lines = ["╭━━━〔 👑 Aᴅᴍɪɴ Lɪsᴛ 〕━━━╮"]
        for member in admins:
            u = member.user
            title = "Oᴡɴᴇʀ" if member.status == ChatMemberStatus.OWNER else "Aᴅᴍɪɴ"
            lines.append(f"\n{_mention(u)} — 🏅 {title}")
        lines.append("\n╰━━━━━━━━━━━━━━━━━━╯")
        return await message.reply("".join(lines))
    except Exception as e:
        print(f"[ADMINLIST] {type(e).__name__}: {e}", flush=True)
        return await message.reply("❌ ᴄᴏᴜʟᴅɴ'ᴛ ғᴇᴛᴄʜ ᴛʜᴇ ᴀᴅᴍɪɴ ʟɪsᴛ.")


async def _parse_right_command(message, action):
    args = list(message.command or [])[1:]
    if not args:
        return None, None, "usage"
    valid = set(ADMIN_RIGHTS)
    rights = [str(x).lower().lstrip("/") for x in args if str(x).lower().lstrip("/") in valid]
    invalid = [str(x) for x in args if str(x).lower().lstrip("/") not in valid and not str(x).lstrip("+-").isdigit() and not str(x).startswith("@")] 
    target = await _resolve_target(message, args)
    if not target:
        return None, rights, "target" if not rights else "target"
    if not rights:
        return target, rights, "right"
    return target, rights, None


@app.on_message(filters.command(["add", "remove"], prefixes=ADMIN_PREFIXES))
async def group_rights(_, message):
    if not _management_group(message):
        return
    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴍᴀɴᴀɢᴇ ᴀᴅᴍɪɴ ʀɪɢʜᴛs.")
    action = (message.command[0] or "").lower()
    target, rights, error = await _parse_right_command(message, action)
    if error == "usage":
        return await message.reply("❌ ᴜsᴀɢᴇ: <code>.add ban</code> ᴏɴ ᴀɴ ᴀᴅᴍɪɴ's ʀᴇᴘʟʏ.")
    if error == "right":
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ʀɪɢʜᴛ. ᴜsᴇ: <code>info delete ban invite pin tags welcome stream addadmins anon stories</code>")
    if error == "target":
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴀᴅᴍɪɴ ᴏʀ ᴀᴅᴅ <code>@username</code>/<code>user id</code>.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴀᴅᴍɪɴ.")

    doc = await _admin_right_doc(message.chat.id, target.id)
    current = set(doc.get("rights", [])) if doc else set()
    if action == "add":
        current.update(rights)
    else:
        current.difference_update(rights)
    try:
        await _apply_telegram_rights(message.chat.id, target.id, current)
        await _save_admin_rights(message.chat.id, target.id, current, doc.get("mode") if doc else None)
    except Exception as e:
        print(f"[ADMIN RIGHTS] {type(e).__name__}: {e}", flush=True)
        return await message.reply("❌ ᴄᴏᴜʟᴅɴ'ᴛ ᴜᴘᴅᴀᴛᴇ ᴛʜᴇsᴇ ʀɪɢʜᴛs. ᴄʜᴇᴄᴋ ᴛʜᴇ ʙᴏᴛ's ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.")

    label = " • ".join(r.title() for r in rights)
    verb = "Aᴅᴅᴇᴅ" if action == "add" else "Rᴇᴍᴏᴠᴇᴅ"
    return await message.reply(f"{_mention(target)} 🕊 Rɪɢʜᴛs {verb} — 🏅 {label}.")


# ══════════════════════════════════════════════════════════════════════════════
#  SOCIAL ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("adminhelp", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("stats", prefixes=ADMIN_PREFIXES))
async def stats(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "📊 <b>ᴇʟᴀʀᴀ sᴛᴀᴛs</b>\n\n<i>ʙᴏᴛ ɪs ᴏɴʟɪɴᴇ ᴀɴᴅ ᴍᴏᴅᴜʟᴀʀ.</i>"
    )


@app.on_message(filters.command("addgif", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("addcaption", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("socialgifs", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("socialcaptions", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("clearsocialgifs", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("clearsocialcaptions", prefixes=ADMIN_PREFIXES))
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

@app.on_message(filters.command("adminpanel", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("adminuser", prefixes=ADMIN_PREFIXES))
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


@app.on_message(filters.command("banbot", prefixes=ADMIN_PREFIXES))
async def banbot(_, message):
    return await _direct_ban(message, True)


@app.on_message(filters.command("botunban", prefixes=ADMIN_PREFIXES))
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


# ══════════════════════════════════════════════════════════════════════════════
#  BROADCAST
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("cancelbroadcast", prefixes=ADMIN_PREFIXES))
async def cancel_admin_broadcast(_, message):
    if not _panel_owner(message):
        return await message.reply("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>")
    _ADMIN_BROADCAST_WAIT.pop(int(message.from_user.id), None)
    await message.reply("❌ <b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>")


async def _copy_or_send(client, target_id, message):
    try:
        if message.text:
            return await client.send_message(target_id, message.text)
        return await client.copy_message(target_id, message.chat.id, message.id)
    except Exception:
        raise


@app.on_message(filters.all, group=-50)
async def admin_broadcast_message(client, message):
    if not _panel_owner(message):
        return
    uid = int(message.from_user.id) if message.from_user else 0
    state = _ADMIN_BROADCAST_WAIT.get(uid)
    if not state or state.get("mode") == "selected_ids":
        if state and state.get("mode") == "selected_ids" and message.text and not message.text.startswith("/"):
            raw_ids = message.text.replace(",", " ").split()
            ids = []
            for raw in raw_ids:
                try:
                    ids.append(int(raw))
                except ValueError:
                    pass
            if not ids:
                return await message.reply("❌ ɴᴏ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅs ғᴏᴜɴᴅ.")
            state["ids"] = ids
            state["mode"] = "selected_message"
            return await message.reply(
                "✅ ɪᴅs sᴀᴠᴇᴅ. ɴᴏᴡ sᴇɴᴅ ᴛʜᴇ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ.\n\n"
                "<code>/cancelbroadcast</code> ᴛᴏ ᴄᴀɴᴄᴇʟ."
            )
        return
    if state.get("mode") == "selected_message":
        targets = state.get("ids", [])
    else:
        docs = await get_broadcast_chats()
        mode = state.get("mode")
        if mode == "groups":
            targets = [int(d["chat_id"]) for d in docs if d.get("type") == "group"]
        elif mode == "private":
            targets = [int(d["chat_id"]) for d in docs if d.get("type") == "private"]
        elif mode == "active":
            targets = await get_active_user_ids(7)
        else:
            targets = [int(d["chat_id"]) for d in docs]
    if message.text and message.text.startswith("/"):
        return
    _ADMIN_BROADCAST_WAIT.pop(uid, None)
    if not targets:
        return await message.reply("❌ ɴᴏ ᴛᴀʀɢᴇᴛs ғᴏᴜɴᴅ ғᴏʀ ᴛʜɪs ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴏᴅᴇ.")
    status = await message.reply(
        f"📢 <b>ʙʀᴏᴀᴅᴄᴀsᴛ sᴛᴀʀᴛᴇᴅ</b>\n\n"
        f"🎯 ᴛᴀʀɢᴇᴛs: <code>{len(targets)}</code>\n⏳ sᴇɴᴅɪɴɢ..."
    )
    sent = failed = 0
    for cid in targets:
        try:
            await _copy_or_send(client, cid, message)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(
        "<b>📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
        f"🎯 ᴛᴀʀɢᴇᴛs: <code>{len(targets)}</code>\n"
        f"✅ sᴇɴᴛ: <code>{sent}</code>\n"
        f"❌ ғᴀɪʟᴇᴅ: <code>{failed}</code>"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL BAN GUARDS (silent — no reply to banned users)
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.all, group=-100)
async def banned_user_guard(_, message):
    if not message.from_user or _panel_owner(message):
        return
    if await is_user_banned(message.from_user.id):
        # Silently ignore — no reply, no reaction, nothing.
        raise StopPropagation


@app.on_callback_query(group=-100)
async def banned_callback_guard(_, query):
    if not query.from_user or _panel_owner(query):
        return
    if await is_user_banned(query.from_user.id):
        # Telegram requires an answer to stop the button spinner.
        # Empty answer = user sees nothing.
        try:
            await query.answer()
        except Exception:
            pass
        raise StopPropagation
