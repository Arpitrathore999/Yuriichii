# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/control.py — Group Admin Management
#  (OWNER self-promote + full rights + .title command)
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

# ✅ topics & dm REMOVED — tags, stories kept
ADMIN_RIGHTS = {
    "info": "can_change_info",
    "delete": "can_delete_messages",
    "ban": "can_restrict_members",
    "invite": "can_invite_users",
    "pin": "can_pin_messages",
    "stream": "can_manage_video_chats",
    "addadmins": "can_promote_members",
    "tags": "can_manage_tags",
    "stories": "can_manage_stories",
}

PROMOTE_MODES = {
    0: ("Tᴇᴍᴘ Aᴅᴍɪɴ", set()),
    1: ("Jᴜɴɪᴏʀ Aᴅᴍɪɴ", {"delete", "invite", "pin"}),
    2: ("Aꜱꜱɪꜱᴛᴀɴᴛ Aᴅᴍɪɴ", {"delete", "invite", "pin", "info", "ban"}),
    3: ("Fᴜʟʟ Aᴅᴍɪɴ", set(ADMIN_RIGHTS.keys())),
}


# ── Detect supported ChatPrivileges flags (for compatibility) ─────────────────
def _supported_flags() -> set:
    try:
        params = set(inspect.signature(ChatPrivileges.__init__).parameters.keys())
        params.discard("self")
        return params
    except Exception:
        return set()


_SUPPORTED = _supported_flags()


def _filter_kwargs(kwargs: dict) -> dict:
    """Keep only flags the current pyrogram supports."""
    if not _SUPPORTED:
        return kwargs
    return {k: v for k, v in kwargs.items() if k in _SUPPORTED}


# ── Empty privileges = full demote ────────────────────────────────────────────

def _empty_privileges():
    """Saare flags False → clear demote signal."""
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
        "can_post_stories": False,
        "can_edit_stories": False,
        "can_delete_stories": False,
        "can_manage_topics": False,
        "can_manage_tags": False,
        "can_manage_direct_messages": False,
        "is_anonymous": False,
    }
    return ChatPrivileges(**_filter_kwargs(all_false))


async def _full_demote(chat_id, user_id):
    """User ko poora normal member bana de."""
    try:
        await app.promote_chat_member(chat_id, user_id, privileges=_empty_privileges())
    except TypeError:
        try:
            await app.promote_chat_member(
                chat_id, user_id,
                privileges=ChatPrivileges(
                    can_manage_chat=False,
                    can_delete_messages=False,
                    can_manage_video_chats=False,
                    can_restrict_members=False,
                    can_promote_members=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                    is_anonymous=False,
                ),
            )
        except Exception:
            await app.promote_chat_member(chat_id, user_id, privileges=ChatPrivileges())
    if db is not None:
        await db["admin_rights"].delete_one(
            {"chat_id": int(chat_id), "user_id": int(user_id)}
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_group(message):
    return bool(message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


async def _is_admin(message):
    if not _is_group(message) or not message.from_user:
        return False
    if int(message.from_user.id) == int(config.OWNER_ID):
        return True
    try:
        m = await app.get_chat_member(message.chat.id, message.from_user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def _can_promote(message):
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


async def _bot_privilege_names(chat_id):
    try:
        me = await app.get_chat_member(chat_id, "me")
        p = getattr(me, "privileges", None)
        if me.status == ChatMemberStatus.OWNER or not p:
            return set(ADMIN_RIGHTS.keys())
        # ✅ UPDATED mapping (topics & dm removed)
        mapping = {
            "info": "can_change_info",
            "delete": "can_delete_messages",
            "ban": "can_restrict_members",
            "invite": "can_invite_users",
            "pin": "can_pin_messages",
            "stream": "can_manage_video_chats",
            "addadmins": "can_promote_members",
            "tags": "can_manage_tags",
            "stories": "can_post_stories",
        }
        return {n for n, a in mapping.items() if bool(getattr(p, a, False))}
    except Exception:
        return set()


def _rights_kwargs(rights):
    return {
        "can_change_info": "info" in rights,
        "can_delete_messages": "delete" in rights,
        "can_restrict_members": "ban" in rights,
        "can_invite_users": "invite" in rights,
        "can_pin_messages": "pin" in rights,
        "can_manage_video_chats": "stream" in rights,
        "can_promote_members": "addadmins" in rights,
        "can_manage_tags": "tags" in rights,
        "can_post_stories": "stories" in rights,
        "can_edit_stories": "stories" in rights,
        "can_delete_stories": "stories" in rights,
        "is_anonymous": False,
    }


async def _apply_rights(chat_id, user_id, rights):
    available = await _bot_privilege_names(chat_id)
    granted = set(rights) & available
    kwargs = _filter_kwargs(_rights_kwargs(granted))
    try:
        await app.promote_chat_member(
            chat_id, user_id,
            privileges=ChatPrivileges(**kwargs)
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

    parts = list(message.command or [])[1:]
    mode = 2
    target_parts = parts

    if parts:
        if str(parts[0]).isdigit():
            mode = int(parts[0]); target_parts = parts[1:]
        elif str(parts[-1]).isdigit():
            mode = int(parts[-1]); target_parts = parts[:-1]

    if mode not in PROMOTE_MODES:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴍᴏᴅᴇ. ᴜsᴇ 0, 1, 2 ᴏʀ 3.")

    target = await _resolve_target(message, target_parts)
    if not target and not target_parts and not message.reply_to_message:
        if not message.from_user or int(message.from_user.id) != int(config.OWNER_ID):
            return await message.reply("❌ ᴏɴʟʏ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ sᴇʟꜰ ᴘʀᴏᴍᴏᴛᴇ.")
        target = message.from_user

    if not target:
        return await message.reply("❌ ᴜsᴇ ᴀ ʀᴇᴘʟʏ, @ᴜꜱᴇʀɴᴀᴍᴇ ᴏʀ ᴜsᴇʀ ɪᴅ.")

    is_self_promote = bool(
        message.from_user
        and int(target.id) == int(message.from_user.id)
        and not target_parts
        and not message.reply_to_message
    )
    if is_self_promote:
        if not message.from_user or int(message.from_user.id) != int(config.OWNER_ID):
            return await message.reply("❌ ᴏɴʟʏ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ sᴇʟꜰ ᴘʀᴏᴍᴏᴛᴇ.")
        if not await _bot_can_promote(message.chat.id):
            return await message.reply("❌ ʙᴏᴛ ɴᴇᴇᴅs <b>Promote Members</b> permission.")
    else:
        if not await _can_promote(message):
            return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴘʀᴏᴍᴏᴛᴇ ᴀᴅᴍɪɴs.")
        if not await _can_edit_target(message, target.id):
            return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴜsᴇʀ.")

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
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴅᴇᴍᴏᴛᴇ ᴀᴅᴍɪɴs.")

    args = list(message.command or [])[1:]
    target = await _resolve_target(message, args)
    if not target:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴀᴅᴍɪɴ ᴏʀ ᴜsᴇ @ᴜsᴇʀɴᴀᴍᴇ/ɪᴅ.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴜsᴇʀ.")

    try:
        await _full_demote(message.chat.id, target.id)
    except Exception as e:
        print(f"[DEMOTE] {type(e).__name__}: {e}", flush=True)
        return await message.reply(f"❌ ᴅᴇᴍᴏᴛᴇ ꜰᴀɪʟᴇᴅ: <code>{str(e)[:300]}</code>")

    return await message.reply(f"{_mention(target)} 🕊 Dᴇᴍᴏᴛᴇᴅ ᴛᴏ 👤 Mᴇᴍʙᴇʀ.")


# ── /title — Set custom admin title ──────────────────────────────────────────

@app.on_message(filters.command("title", prefixes=PREFIXES))
async def cmd_title(_, message):
    """Set custom admin title for a user.

    Usage:
        .title King        (reply to admin)
        .title @user King
        .title King @user
        .title             (reply — clear title)

    Max 16 characters (Telegram limit).
    """
    if not _is_group(message):
        return await message.reply("❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ᴡᴏʀᴋs ɪɴ ɢʀᴏᴜᴘs.")

    # Permission check
    if not await _can_promote(message):
        return await message.reply(
            "❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛɪᴛʟᴇs."
        )
    if not await _bot_can_promote(message.chat.id):
        return await message.reply(
            "❌ ʙᴏᴛ ɴᴇᴇᴅs <b>Promote Members</b> permission."
        )

    args = list(message.command or [])[1:]

    # Resolve target
    target = None
    title_parts = []

    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        title_parts = args  # all args are title
    else:
        # Find target in args (mention / id / username) and rest is title
        for i, a in enumerate(args):
            raw = a.strip()
            if raw.startswith("@") or raw.lstrip("+-").isdigit():
                try:
                    if raw.lstrip("+-").isdigit():
                        target = await app.get_users(int(raw))
                    else:
                        target = await app.get_users(raw.lstrip("@"))
                except Exception:
                    target = None
                if target:
                    title_parts = args[:i] + args[i+1:]
                    break
        if not target and args:
            # Maybe text mention entity
            for entity in list(message.entities or []):
                etype = str(getattr(entity, "type", ""))
                if etype in ("MessageEntityType.TEXT_MENTION", "text_mention") and getattr(entity, "user", None):
                    target = entity.user
                    # Remove that token from title_parts
                    title_parts = []
                    for a in args:
                        if a.strip() != "@" + (target.username or ""):
                            title_parts.append(a)
                    break

    if not target:
        return await message.reply(
            "❌ <b>ᴜsᴀɢᴇ:</b>\n"
            "• Reply to an admin + <code>.title King</code>\n"
            "• <code>.title @user King</code>"
        )

    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴜsᴇʀ.")

    # Check if target is admin
    try:
        target_member = await app.get_chat_member(message.chat.id, target.id)
    except Exception:
        return await message.reply("❌ ᴄᴀɴ'ᴛ ғᴇᴛᴄʜ ᴛᴀʀɢᴇᴛ ᴍᴇᴍʙᴇʀ.")

    if target_member.status == ChatMemberStatus.OWNER:
        return await message.reply("❌ ᴄᴀɴ'ᴛ ᴄʜᴀɴɢᴇ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ's ᴛɪᴛʟᴇ.")

    if target_member.status != ChatMemberStatus.ADMINISTRATOR:
        return await message.reply(
            f"❌ {_mention(target)} ɪs ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ.\n"
            "<i>ᴘʀᴏᴍᴏᴛᴇ ᴛʜᴇᴍ ғɪʀsᴛ ᴡɪᴛʜ /promote.</i>"
        )

    # Title text
    title_text = " ".join(title_parts).strip()

    # Telegram limit: 16 chars
    if len(title_text) > 16:
        return await message.reply(
            f"❌ ᴛɪᴛʟᴇ ᴛᴏᴏ ʟᴏɴɢ ({len(title_text)}/16).\n"
            "<i>ᴍᴀx 16 ᴄʜᴀʀᴀᴄᴛᴇʀs.</i>"
        )

    # Set title (empty string = clear)
    try:
        await app.set_administrator_title(
            message.chat.id, target.id, title_text
        )
    except Exception as e:
        print(f"[TITLE] {type(e).__name__}: {e}", flush=True)
        return await message.reply(
            f"❌ ꜰᴀɪʟᴇᴅ ᴛᴏ sᴇᴛ ᴛɪᴛʟᴇ: <code>{str(e)[:200]}</code>"
        )

    if title_text:
        return await message.reply(
            f"👑 {_mention(target)} ɴᴏᴡ ʜᴀs ᴛɪᴛʟᴇ: <b>{title_text}</b>"
        )
    else:
        return await message.reply(
            f"👑 {_mention(target)}'s ᴛɪᴛʟᴇ ʀᴇᴍᴏᴠᴇᴅ."
        )


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
            custom = getattr(m, "custom_title", None)
            if custom:
                title = custom
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
            ("tags",       "ᴍᴀɴᴀɢᴇ ᴛᴀɢꜱ"),
            ("stories",    "ᴍᴀɴᴀɢᴇ ꜱᴛᴏʀɪᴇꜱ"),
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


def _title_help_text():
    return (
        rich_heading("👑 ᴛɪᴛʟᴇ ᴄᴏᴍᴍᴀɴᴅ ɢᴜɪᴅᴇ", level=3)
        + "<i>ᴀᴅᴍɪɴ ʀɪɢʜᴛꜱ ʜᴀᴛᴀɴᴇ ᴋᴇ ʟɪʏᴇ</i>\n\n"
        + rich_kv_table([
            ("📌 ᴜꜱᴀɢᴇ",   "<code>.title King</code> <i>(reply)</i>"),
            ("🔤 ᴘʀᴇꜰɪx",   "<code>.</code>  <code>/</code>  <code>!</code>"),
            ("📏 ʟɪᴍɪᴛ",  "ᴍᴀx 16 ᴄʜᴀʀᴀᴄᴛᴇʀꜱ"),
        ], headers=["ɪɴꜰᴏ", "ᴠᴀʟᴜᴇ"])
        + "\n"
        + rich_heading("📖 ᴇxᴀᴍᴘʟᴇꜱ", level=4)
        + rich_kv_table([
            (".title King",        "ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ"),
            (".title @user King",  "ᴜꜱᴇʀɴᴀᴍᴇ ꜱᴇ"),
            (".title",             "ᴛɪᴛʟᴇ ʜᴀᴛᴀᴏ"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note("👑 ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴋᴏ ᴄᴜꜱᴛᴏᴍ ᴛɪᴛʟᴇ ᴍɪʟ sᴀᴋᴛᴀ ʜᴀɪ.")
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
            InlineKeyboardButton("👑 ᴛɪᴛʟᴇ", callback_data="ctl:title",
                                 style=enums.ButtonStyle.PRIMARY),
            InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="ctl:close",
                                 style=enums.ButtonStyle.DANGER),
        ],
    ])


async def _show_control_help(message, action):
    if action == "add":
        text = _add_help_text()
    elif action == "remove":
        text = _remove_help_text()
    else:
        text = _title_help_text()
    return await rich_send(
        app, message.chat.id,
        text,
        reply_markup=_control_menu_kb(),
        reply_to_message_id=message.id,
    )


@app.on_message(filters.command(["addhelp", "removehelp", "controlhelp", "titlehelp"], prefixes=PREFIXES))
async def cmd_control_help(_, message):
    if not _is_group(message):
        return
    cmd = (message.command[0] or "").lower().lstrip("/!.")
    if cmd == "removehelp":
        action = "remove"
    elif cmd == "titlehelp":
        action = "title"
    else:
        action = "add"
    await _show_control_help(message, action)


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
    if data == "title":
        return await rich_edit(query, _title_help_text(), reply_markup=_control_menu_kb())


# ══════════════════════════════════════════════════════════════════════════════
#  .add / .remove — rights handler
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_rights(message, action):
    if not _is_group(message):
        return

    args = list(message.command or [])[1:]
    has_reply = bool(message.reply_to_message and message.reply_to_message.from_user)

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

    if not target:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜꜱᴇʀ ᴏʀ ᴜꜱᴇ @ᴜꜱᴇʀɴᴀᴍᴇ/ɪᴅ.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪꜰʏ ᴛʜɪs ᴜꜱᴇʀ.")

    valid = set(ADMIN_RIGHTS)
    rights = {str(x).lower().lstrip("/!.") for x in args}
    rights = {r for r in rights if r in valid}

    if not rights:
        if action == "remove":
            try:
                await _full_demote(message.chat.id, target.id)
            except Exception as e:
                print(f"[REMOVE FULL] {type(e).__name__}: {e}", flush=True)
                return await message.reply(f"❌ ꜰᴀɪʟᴇᴅ: <code>{str(e)[:300]}</code>")
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
            return await message.reply(f"❌ ꜰᴀɪʟᴇᴅ: <code>{str(e)[:300]}</code>")
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
