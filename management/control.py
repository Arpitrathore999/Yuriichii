# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/control.py — Group Admin Management
#  (OWNER self-promote + full rights: topics, tags, stories, dm)
# --------------------------------------------------------------------------------

import inspect

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import ChatPrivileges, InlineKeyboardButton, InlineKeyboardMarkup

import config
from core.bot import app
from database.mongo import db
from utils.rich_ui import (
    rich_esc,
    rich_heading,
    rich_note,
    rich_kv_table,
    rich_table,
    rich_send,
    rich_edit,
)


PREFIXES = ["/", "!", "."]

# ✅ UPDATED — anon removed, tags/stories/topics/dm added
ADMIN_RIGHTS = {
    "info": "can_change_info",
    "delete": "can_delete_messages",
    "ban": "can_restrict_members",
    "invite": "can_invite_users",
    "pin": "can_pin_messages",
    "stream": "can_manage_video_chats",
    "addadmins": "can_promote_members",
    "topics": "can_manage_topics",
    "tags": "can_manage_tags",
    "stories": "can_manage_stories",
    "dm": "can_manage_direct_messages",
}

PROMOTE_MODES = {
    0: ("Tᴇᴍᴘ Aᴅᴍɪɴ", set()),
    1: ("Jᴜɴɪᴏʀ Aᴅᴍɪɴ", {"delete", "invite", "pin"}),
    2: ("Aꜱꜱɪꜱᴛᴀɴᴛ Aᴅᴍɪɴ", {"delete", "invite", "pin", "info", "ban"}),
    3: ("Fᴜʟʟ Aᴅᴍɪɴ", set(ADMIN_RIGHTS.keys())),
}


# ✅ Detect which ChatPrivileges flags current pyrogram/kurigram supports
def _supported_privileges() -> set:
    try:
        params = set(inspect.signature(ChatPrivileges.__init__).parameters.keys())
        params.discard("self")
        return params
    except Exception:
        return set()


_SUPPORTED = _supported_privileges()


# ── Empty privileges = full demote ────────────────────────────────────────────

def _empty_privileges() -> ChatPrivileges:
    """Build a fully-empty privileges object (all flags False).
    Only includes flags supported by current pyrogram build.
    """
    all_false = {
        "can_manage_chat": False,
        "can_delete_messages": False,
        "can_manage_video_chats": False,
        "can_restrict_members": False,
        "can_promote_members": False,
        "can_change_info": False,
        "can_invite_users": False,
        "can_post_messages": False,
        "can_edit_messages": False,
        "can_pin_messages": False,
        "can_manage_topics": False,
        "can_post_stories": False,
        "can_edit_stories": False,
        "can_delete_stories": False,
        "can_manage_tags": False,
        "can_manage_direct_messages": False,
        "is_anonymous": False,
    }
    filtered = {k: v for k, v in all_false.items() if k in _SUPPORTED or not _SUPPORTED}
    return ChatPrivileges(**filtered)


async def _full_demote(chat_id, user_id):
    """Demote user back to normal member."""
    try:
        await app.promote_chat_member(chat_id, user_id, privileges=_empty_privileges())
    except Exception as e:
        print(f"[FULL DEMOTE] {type(e).__name__}: {e}", flush=True)
    if db is not None:
        await db["admin_rights"].delete_one(
            {"chat_id": int(chat_id), "user_id": int(user_id)}
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


def _is_bot_owner(message):
    """Check if the sender is bot's OWNER_ID."""
    return bool(
        message.from_user
        and int(message.from_user.id) == int(config.OWNER_ID)
    )


async def _is_admin(message):
    if not _is_group(message) or not message.from_user:
        return False
    if _is_bot_owner(message):
        return True
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _bot_can_promote(chat_id):
    try:
        me = await app.get_chat_member(chat_id, "me")
        if me.status == ChatMemberStatus.OWNER:
            return True
        return bool(
            getattr(me, "privileges", None)
            and getattr(me.privileges, "can_promote_members", False)
        )
    except Exception:
        return False


async def _can_promote(message):
    # ✅ Bot OWNER_ID bypass
    if _is_bot_owner(message):
        return await _bot_can_promote(message.chat.id)

    if not await _is_admin(message):
        return False
    try:
        actor = await app.get_chat_member(message.chat.id, message.from_user.id)
        if actor.status == ChatMemberStatus.OWNER:
            return True
        return bool(
            getattr(actor, "privileges", None)
            and getattr(actor.privileges, "can_promote_members", False)
        )
    except Exception:
        return False


async def _can_edit_target(message, target_id):
    # ✅ Bot OWNER_ID bypass
    if _is_bot_owner(message):
        try:
            target_member = await app.get_chat_member(message.chat.id, target_id)
            if target_member.status == ChatMemberStatus.OWNER:
                return False
        except Exception:
            pass
        return True

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
            return bool(
                getattr(actor, "privileges", None)
                and getattr(actor.privileges, "can_promote_members", False)
            )
        return True
    except Exception:
        return False


def _mention(user, fallback="User"):
    uid = int(getattr(user, "id", 0) or 0)
    name = str(getattr(user, "first_name", None) or fallback)
    return f'<a href="tg://user?id={uid}">{name}</a>' if uid else name


async def _resolve_target(message, args):
    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user

    for entity in list(message.entities or []):
        etype = str(getattr(entity, "type", ""))
        if etype in ("MessageEntityType.TEXT_MENTION", "text_mention") and getattr(entity, "user", None):
            return entity.user

    for raw in (str(x).strip() for x in args if str(x).strip()):
        if raw.startswith("@"):
            raw = raw[1:]
        if raw.lstrip("+-").isdigit():
            try:
                return await app.get_users(int(raw))
            except Exception:
                continue
        if raw:
            try:
                return await app.get_users(raw)
            except Exception:
                continue
    return None


async def _bot_privilege_names(chat_id) -> set:
    """Return set of Elara-right-names the bot itself can grant."""
    try:
        me = await app.get_chat_member(chat_id, "me")
        p = getattr(me, "privileges", None)
        if me.status == ChatMemberStatus.OWNER or not p:
            return set(ADMIN_RIGHTS.keys())

        # ✅ UPDATED mapping
        mapping = {
            "info": "can_change_info",
            "delete": "can_delete_messages",
            "ban": "can_restrict_members",
            "invite": "can_invite_users",
            "pin": "can_pin_messages",
            "stream": "can_manage_video_chats",
            "addadmins": "can_promote_members",
            "topics": "can_manage_topics",
            "tags": "can_manage_tags",
            "stories": "can_post_stories",              # representative of the 3
            "dm": "can_manage_direct_messages",
        }
        return {n for n, a in mapping.items() if bool(getattr(p, a, False))}
    except Exception:
        return set()


def _rights_kwargs(rights) -> dict:
    """Build ChatPrivileges kwargs from Elara-right-names."""
    return {
        "can_change_info": "info" in rights,
        "can_delete_messages": "delete" in rights,
        "can_restrict_members": "ban" in rights,
        "can_invite_users": "invite" in rights,
        "can_pin_messages": "pin" in rights,
        "can_manage_video_chats": "stream" in rights,
        "can_promote_members": "addadmins" in rights,
        "can_manage_topics": "topics" in rights,
        "can_manage_tags": "tags" in rights,
        "can_post_stories": "stories" in rights,
        "can_edit_stories": "stories" in rights,
        "can_delete_stories": "stories" in rights,
        "can_manage_direct_messages": "dm" in rights,
        "is_anonymous": False,
    }


def _make_privileges(rights) -> ChatPrivileges:
    """Build ChatPrivileges object, filtered to supported flags."""
    kwargs = _rights_kwargs(rights)
    filtered = {k: v for k, v in kwargs.items() if k in _SUPPORTED or not _SUPPORTED}
    return ChatPrivileges(**filtered)


async def _apply_rights(chat_id, user_id, rights):
    available = await _bot_privilege_names(chat_id)
    granted = set(rights) & available
    try:
        await app.promote_chat_member(
            chat_id, user_id,
            privileges=_make_privileges(granted)
        )
    except Exception as e:
        print(f"[APPLY RIGHTS] {type(e).__name__}: {e}", flush=True)
        raise
    return granted


async def _save_rights(chat_id, user_id, rights, mode=None):
    if db is None:
        return
    doc = {
        "chat_id": int(chat_id),
        "user_id": int(user_id),
        "rights": sorted(set(rights)),
    }
    if mode is not None:
        doc["mode"] = int(mode)
    await db["admin_rights"].update_one(
        {"chat_id": int(chat_id), "user_id": int(user_id)},
        {"$set": doc},
        upsert=True,
    )


# ── /promote ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("promote", prefixes=PREFIXES))
async def cmd_promote(_, message):
    if not _is_group(message):
        return
    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴘʀᴏᴍᴏᴛᴇ ᴀᴅᴍɪɴꜱ.")

    parts = list(message.command or [])[1:]
    mode = 2
    target_parts = parts

    if parts:
        if str(parts[0]).isdigit():
            mode = int(parts[0]); target_parts = parts[1:]
        elif str(parts[-1]).isdigit():
            mode = int(parts[-1]); target_parts = parts[:-1]

    if mode not in PROMOTE_MODES:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴍᴏᴅᴇ. ᴜꜱᴇ 0, 1, 2 ᴏʀ 3.")

    target = await _resolve_target(message, target_parts)

    # ✅ Bot owner: agar target nahi → sender khud
    if not target and _is_bot_owner(message):
        target = message.from_user

    if not target:
        return await message.reply("❌ ᴜꜱᴇ ᴀ ʀᴇᴘʟʏ, @ᴜꜱᴇʀɴᴀᴍᴇ ᴏʀ ᴜꜱᴇʀ ɪᴅ.")

    is_self = message.from_user and (int(target.id) == int(message.from_user.id))
    if not is_self:
        if not await _can_edit_target(message, target.id):
            return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪꜱ ᴜꜱᴇʀ.")

    requested = set(PROMOTE_MODES[mode][1])
    try:
        applied = await _apply_rights(message.chat.id, target.id, requested)
    except Exception as e:
        print(f"[PROMOTE] {type(e).__name__}: {e}", flush=True)
        return await message.reply(f"❌ ᴘʀᴏᴍᴏᴛᴇ ꜰᴀɪʟᴇᴅ: <code>{str(e)[:200]}</code>")

    await _save_rights(message.chat.id, target.id, applied, mode)

    role = PROMOTE_MODES[mode][0]
    return await message.reply(
        f"{_mention(target)} 🕊 Pʀᴏᴍᴏᴛᴇᴅ ᴛᴏ 🏅 <b>{role}</b>\n"
        f"🔐 <code>{', '.join(sorted(applied)) or 'none'}</code>"
    )


# ── /demote ───────────────────────────────────────────────────────────────────

@app.on_message(filters.command("demote", prefixes=PREFIXES))
async def cmd_demote(_, message):
    if not _is_group(message):
        return
    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴅᴇᴍᴏᴛᴇ ᴀᴅᴍɪɴꜱ.")

    args = list(message.command or [])[1:]
    target = await _resolve_target(message, args)

    if not target and _is_bot_owner(message):
        target = message.from_user

    if not target:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴀᴅᴍɪɴ ᴏʀ ᴜꜱᴇ @ᴜꜱᴇʀɴᴀᴍᴇ/ɪᴅ.")

    is_self = message.from_user and (int(target.id) == int(message.from_user.id))
    if not is_self:
        if not await _can_edit_target(message, target.id):
            return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪꜱ ᴜꜱᴇʀ.")

    try:
        await _full_demote(message.chat.id, target.id)
    except Exception as e:
        print(f"[DEMOTE] {type(e).__name__}: {e}", flush=True)
        return await message.reply(f"❌ ᴅᴇᴍᴏᴛᴇ ꜰᴀɪʟᴇᴅ: <code>{str(e)[:300]}</code>")

    return await message.reply(f"{_mention(target)} 🕊 Dᴇᴍᴏᴛᴇᴅ ᴛᴏ 👤 Mᴇᴍʙᴇʀ.")


# ── /adminlist ────────────────────────────────────────────────────────────────

@app.on_message(filters.command("adminlist", prefixes=PREFIXES))
async def cmd_adminlist(_, message):
    if not _is_group(message):
        return
    try:
        from pyrogram.enums import ChatMembersFilter
        admins = []
        async for m in app.get_chat_members(
            message.chat.id, filter=ChatMembersFilter.ADMINISTRATORS
        ):
            if m.user:
                admins.append(m)
        if not admins:
            return await message.reply("❌ ɴᴏ ᴀᴅᴍɪɴs ғᴏᴜɴᴅ.")
        lines = ["👑 <b>Aᴅᴍɪɴ Lɪsᴛ</b>\n"]
        for m in admins:
            title = "Oᴡɴᴇʀ" if m.status == ChatMemberStatus.OWNER else "Aᴅᴍɪɴ"
            lines.append(f"• {_mention(m.user)} — 🏅 {title}")
        return await message.reply("\n".join(lines))
    except Exception as e:
        print(f"[ADMINLIST] {type(e).__name__}: {e}", flush=True)
        return await message.reply(f"❌ ᴇʀʀᴏʀ: <code>{str(e)[:200]}</code>")


# ══════════════════════════════════════════════════════════════════════════════
#  ADD / REMOVE HELP MENU (Rich UI)
# ══════════════════════════════════════════════════════════════════════════════

def _add_help_text():
    return (
        rich_heading("➕ ᴀᴅᴅ ᴄᴏᴍᴍᴀɴᴅ ɢᴜɪᴅᴇ", level=3)
        + "<i>ᴜꜱᴇʀ ᴋᴏ ᴀᴅᴍɪɴ ʙᴀɴᴀɴᴇ ᴋᴇ ʟɪʏᴇ</i>\n\n"
        + rich_kv_table([
            ("📌 ᴜꜱᴀɢᴇ",   "<code>.add</code> <i>(reply)</i>"),
            ("🔤 ᴘʀᴇꜰɪx",   "<code>.</code>  <code>/</code>  <code>!</code>"),
            ("🎯 ᴛᴀʀɢᴇᴛ",  "ʀᴇᴘʟʏ • @ᴜꜱᴇʀɴᴀᴍᴇ • ɪᴅ"),
        ], headers=["ɪɴꜰᴏ", "ᴠᴀʟᴜᴇ"])
        + "\n"
        + rich_heading("📖 ᴇxᴀᴍᴘʟᴇꜱ", level=4)
        + rich_kv_table([
            (".add",              "ꜰᴜʟʟ ᴀᴅᴍɪɴ ʀɪɢʜᴛꜱ"),
            (".add delete ban",   "ꜱᴇʟᴇᴄᴛɪᴠᴇ ʀɪɢʜᴛꜱ"),
            (".add @username",    "ᴜꜱᴇʀɴᴀᴍᴇ ꜱᴇ"),
            (".add <reply>",      "ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_heading("🔐 ᴀᴠᴀɪʟᴀʙʟᴇ ʀɪɢʜᴛꜱ", level=4)
        + rich_kv_table([
            ("info",       "ᴄʜᴀɴɢᴇ ɢʀᴏᴜᴘ ɪɴꜰᴏ"),
            ("delete",     "ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ"),
            ("ban",        "ʙᴀɴ/ᴋɪᴄᴋ ᴜꜱᴇʀꜱ"),
            ("invite",     "ᴀᴅᴅ ᴜꜱᴇʀꜱ"),
            ("pin",        "ᴘɪɴ ᴍᴇꜱꜱᴀɢᴇꜱ"),
            ("stream",     "ᴍᴀɴᴀɢᴇ ᴠɪᴅᴇᴏ ᴄʜᴀᴛꜱ"),
            ("addadmins",  "ᴀᴅᴅ ɴᴇᴡ ᴀᴅᴍɪɴꜱ"),
            ("topics",     "ᴍᴀɴᴀɢᴇ ᴛᴏᴘɪᴄꜱ"),
            ("tags",       "ᴍᴀɴᴀɢᴇ ᴛᴀɢꜱ"),
            ("stories",    "ᴍᴀɴᴀɢᴇ ꜱᴛᴏʀɪᴇꜱ"),
            ("dm",         "ᴍᴀɴᴀɢᴇ ᴅɪʀᴇᴄᴛ ᴍᴇꜱꜱᴀɢᴇꜱ"),
        ], headers=["ʀɪɢʜᴛ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note("💡 ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ <code>.add</code> ʙʜᴇᴊɴᴇ ꜱᴇ ꜰᴜʟʟ ᴀᴅᴍɪɴ ʙᴀɴ ᴊᴀᴀᴛᴀ ʜᴀɪ.")
    )


def _remove_help_text():
    return (
        rich_heading("➖ ʀᴇᴍᴏᴠᴇ ᴄᴏᴍᴍᴀɴᴅ ɢᴜɪᴅᴇ", level=3)
        + "<i>ᴀᴅᴍɪɴ ʀɪɢʜᴛꜱ ʜᴀᴛᴀɴᴇ ᴋᴇ ʟɪʏᴇ</i>\n\n"
        + rich_kv_table([
            ("📌 ᴜꜱᴀɢᴇ",   "<code>.remove</code> <i>(reply)</i>"),
            ("🔤 ᴘʀᴇꜰɪx",   "<code>.</code>  <code>/</code>  <code>!</code>"),
            ("🎯 ᴛᴀʀɢᴇᴛ",  "ʀᴇᴘʟʏ • @ᴜꜱᴇʀɴᴀᴍᴇ • ɪᴅ"),
        ], headers=["ɪɴꜰᴏ", "ᴠᴀʟᴜᴇ"])
        + "\n"
        + rich_heading("📖 ᴇxᴀᴍᴘʟᴇꜱ", level=4)
        + rich_kv_table([
            (".remove",           "ꜰᴜʟʟ ᴅᴇᴍᴏᴛᴇ"),
            (".remove delete",    "ꜱɪʀꜰ ᴅᴇʟᴇᴛᴇ ʜᴀᴛᴀᴏ"),
            (".remove @username", "ᴜꜱᴇʀɴᴀᴍᴇ ꜱᴇ"),
            (".remove <reply>",   "ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note("⚠️ ᴋᴏɪ ʀɪɢʜᴛ ɴᴀ ᴅᴇɴᴇ ᴘᴇ ꜰᴜʟʟ ᴅᴇᴍᴏᴛᴇ ʜᴏ ᴊᴀᴀʏᴇɢᴀ.")
    )


def _control_menu_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ ᴀᴅᴅ", callback_data="ctl:add",
                                 style=enums.ButtonStyle.SUCCESS),
            InlineKeyboardButton("➖ ʀᴇᴍᴏᴠᴇ", callback_data="ctl:remove",
                                 style=enums.ButtonStyle.DANGER),
        ],
        [
            InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="ctl:close",
                                 style=enums.ButtonStyle.DANGER),
        ],
    ])


async def _show_control_help(message, action):
    text = _add_help_text() if action == "add" else _remove_help_text()
    return await rich_send(
        app, message.chat.id,
        text,
        reply_markup=_control_menu_kb(),
        reply_to_message_id=message.id,
    )


# ── Help commands ─────────────────────────────────────────────────────────────

@app.on_message(filters.command(["addhelp", "removehelp", "controlhelp"], prefixes=PREFIXES))
async def cmd_control_help(_, message):
    if not _is_group(message):
        return
    cmd = (message.command[0] or "").lower().lstrip("/!.")
    action = "remove" if cmd == "removehelp" else "add"
    await _show_control_help(message, action)


# ── Callback handler ──────────────────────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^ctl:"))
async def _ctl_callback(_, query):
    data = query.data.split(":")[1]
    if data == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return
    if data == "add":
        return await rich_edit(query, _add_help_text(), reply_markup=_control_menu_kb())
    if data == "remove":
        return await rich_edit(query, _remove_help_text(), reply_markup=_control_menu_kb())


# ══════════════════════════════════════════════════════════════════════════════
#  .add / .remove — rights handler
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_rights(message, action):
    if not _is_group(message):
        return

    args = list(message.command or [])[1:]
    has_reply = bool(message.reply_to_message and message.reply_to_message.from_user)

    # Help menu
    if not has_reply and not args:
        return await _show_control_help(message, action)

    if not has_reply and args:
        valid = set(ADMIN_RIGHTS)
        given = {str(x).lower().lstrip("/!.") for x in args}
        has_target = any(
            a.startswith("@") or a.lstrip("+-").isdigit()
            for a in args
        )
        has_valid_right = bool(given & valid)
        if not has_valid_right and not has_target:
            return await _show_control_help(message, action)

    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ɴᴇᴇᴅ <b>Promote Members</b> permission.")
    if not await _bot_can_promote(message.chat.id):
        return await message.reply("❌ ʙᴏᴛ ɴᴇᴇᴅs <b>Promote Members</b> permission.")

    target = None
    if has_reply:
        target = message.reply_to_message.from_user
    if not target:
        target = await _resolve_target(message, args)

    if not target and _is_bot_owner(message):
        target = message.from_user

    if not target:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜꜱᴇʀ ᴏʀ ᴜꜱᴇ @ᴜꜱᴇʀɴᴀᴍᴇ/ɪᴅ.")

    is_self = message.from_user and (int(target.id) == int(message.from_user.id))
    if not is_self:
        if not await _can_edit_target(message, target.id):
            return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪꜱ ᴜꜱᴇʀ.")

    valid = set(ADMIN_RIGHTS)
    rights = {str(x).lower().lstrip("/!.") for x in args}
    rights = {r for r in rights if r in valid}

    # No rights supplied
    if not rights:
        if action == "remove":
            try:
                await _full_demote(message.chat.id, target.id)
            except Exception as e:
                print(f"[REMOVE FULL] {type(e).__name__}: {e}", flush=True)
                return await message.reply(f"❌ ғᴀɪʟᴇᴅ: <code>{str(e)[:300]}</code>")
            return await message.reply(f"{_mention(target)} 🕊 <b>Dᴇᴍᴏᴛᴇᴅ</b>.")
        rights = await _bot_privilege_names(message.chat.id)
        rights = {r for r in rights if r in ADMIN_RIGHTS}

    current = set()
    if db is not None:
        doc = await db["admin_rights"].find_one(
            {"chat_id": int(message.chat.id), "user_id": int(target.id)}
        )
        if doc:
            current = set(doc.get("rights", []))

    if action == "add":
        current.update(rights)
    else:
        current.difference_update(rights)

    if not current:
        try:
            await _full_demote(message.chat.id, target.id)
        except Exception as e:
            print(f"[AUTO DEMOTE] {type(e).__name__}: {e}", flush=True)
            return await message.reply(f"❌ ғᴀɪʟᴇᴅ: <code>{str(e)[:300]}</code>")
        return await message.reply(f"{_mention(target)} 🕊 <b>Dᴇᴍᴏᴛᴇᴅ</b>.")

    applied = await _apply_rights(message.chat.id, target.id, current)
    await _save_rights(message.chat.id, target.id, applied)

    verb = "Aᴅᴅᴇᴅ" if action == "add" else "Rᴇᴍᴏᴠᴇᴅ"
    return await message.reply(
        f"{_mention(target)} 🕊 <b>Rɪɢʜᴛs {verb}</b>\n"
        f"🔐 <code>{', '.join(sorted(applied)) or 'none'}</code>"
    )


@app.on_message(filters.command("add", prefixes=PREFIXES))
async def cmd_add(_, message):
    await _handle_rights(message, "add")


@app.on_message(filters.command("remove", prefixes=PREFIXES))
async def cmd_remove(_, message):
    await _handle_rights(message, "remove")
