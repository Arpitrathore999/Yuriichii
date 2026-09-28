# --------------------------------------------------------------------------------
#  Elara © 2026
#  management/control.py — Group Admin Management
#  (promote / demote / add / remove / adminlist)
# --------------------------------------------------------------------------------

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import ChatPrivileges

import config
from core.bot import app
from database.mongo import db


# ── Prefixes (/, !, .) all supported ──────────────────────────────────────────
PREFIXES = ["/", "!", "."]

ADMIN_RIGHTS = {
    "info": "can_change_info",
    "delete": "can_delete_messages",
    "ban": "can_restrict_members",
    "invite": "can_invite_users",
    "pin": "can_pin_messages",
    "stream": "can_manage_video_chats",
    "addadmins": "can_promote_members",
    "anon": "is_anonymous",
}

PROMOTE_MODES = {
    0: ("Tᴇᴍᴘ Aᴅᴍɪɴ", set()),
    1: ("Jᴜɴɪᴏʀ Aᴅᴍɪɴ", {"delete", "invite", "pin"}),
    2: ("Aꜱꜱɪꜱᴛᴀɴᴛ Aᴅᴍɪɴ", {"delete", "invite", "pin", "info", "ban"}),
    3: ("Fᴜʟʟ Aᴅᴍɪɴ", set(ADMIN_RIGHTS.keys())),
}


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
    """Reply → text-mention → @username → numeric ID."""
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
        mapping = {
            "info": "can_change_info",
            "delete": "can_delete_messages",
            "ban": "can_restrict_members",
            "invite": "can_invite_users",
            "pin": "can_pin_messages",
            "stream": "can_manage_video_chats",
            "addadmins": "can_promote_members",
            "anon": "is_anonymous",
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
        "is_anonymous": "anon" in rights,
    }


async def _apply_rights(chat_id, user_id, rights):
    available = await _bot_privilege_names(chat_id)
    granted = set(rights) & available
    await app.promote_chat_member(
        chat_id, user_id,
        privileges=ChatPrivileges(**_rights_kwargs(granted))
    )
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
        return await message.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴘʀᴏᴍᴏᴛᴇ ᴀᴅᴍɪɴs.")

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
    if not target:
        return await message.reply("❌ ᴜsᴇ ᴀ ʀᴇᴘʟʏ, @ᴜsᴇʀɴᴀᴍᴇ ᴏʀ ᴜsᴇʀ ɪᴅ.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴜsᴇʀ.")

    requested = set(PROMOTE_MODES[mode][1])
    applied = await _apply_rights(message.chat.id, target.id, requested)
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
        await app.promote_chat_member(
            message.chat.id, target.id, privileges=ChatPrivileges()
        )
        if db is not None:
            await db["admin_rights"].delete_one(
                {"chat_id": int(message.chat.id), "user_id": int(target.id)}
            )
    except Exception as e:
        return await message.reply(f"❌ ᴅᴇᴍᴏᴛᴇ ғᴀɪʟᴇᴅ: <code>{str(e)[:200]}</code>")

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
        return await message.reply(f"❌ ᴇʀʀᴏʀ: <code>{str(e)[:200]}</code>")


# ── .add / .remove ────────────────────────────────────────────────────────────

async def _handle_rights(message, action):
    if not _is_group(message):
        return
    if not await _can_promote(message):
        return await message.reply("❌ ʏᴏᴜ ɴᴇᴇᴅ <b>Promote Members</b> permission.")
    if not await _bot_can_promote(message.chat.id):
        return await message.reply("❌ ʙᴏᴛ ɴᴇᴇᴅs <b>Promote Members</b> permission.")

    args = list(message.command or [])[1:]

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        target = await _resolve_target(message, args)

    if not target:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ᴏʀ ᴜsᴇ @ᴜsᴇʀɴᴀᴍᴇ/ɪᴅ.")
    if not await _can_edit_target(message, target.id):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴏᴅɪғʏ ᴛʜɪs ᴜsᴇʀ.")

    valid = set(ADMIN_RIGHTS)
    rights = {str(x).lower().lstrip("/!.") for x in args}
    rights = {r for r in rights if r in valid}

    if not rights:
        if action == "remove":
            try:
                await app.promote_chat_member(
                    message.chat.id, target.id, privileges=ChatPrivileges()
                )
                if db is not None:
                    await db["admin_rights"].delete_one(
                        {"chat_id": int(message.chat.id), "user_id": int(target.id)}
                    )
            except Exception as e:
                return await message.reply(f"❌ ғᴀɪʟᴇᴅ: <code>{str(e)[:200]}</code>")
            return await message.reply(f"{_mention(target)} 🕊 <b>Dᴇᴍᴏᴛᴇᴅ</b>.")
        rights = await _bot_privilege_names(message.chat.id)
        rights = {r for r in rights if r in ADMIN_RIGHTS}

    # Get current from DB
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

    applied = await _apply_rights(message.chat.id, target.id, current)

    if db is not None:
        if applied:
            await _save_rights(message.chat.id, target.id, applied)
        else:
            await db["admin_rights"].delete_one(
                {"chat_id": int(message.chat.id), "user_id": int(target.id)}
            )

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
