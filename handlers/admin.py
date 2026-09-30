# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/admin.py — Premium Owner Panel + Social Admin
# --------------------------------------------------------------------------------

PREFIXES = ["/", "!", "."]

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
        "🚫 <b>ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ</b>\n\n"
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

@app.on_message(filters.command("adminhelp", prefixes=PREFIXES))
async def admin_help(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "🛠️ <b>ꜱᴏᴄɪᴀʟ ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅꜱ</b>\n\n"
        "🎞️ <b>ɢɪꜰꜱ</b>\n"
        "• ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪꜰ → <code>/addgif hug</code>\n"
        "• <code>/socialgifs hug</code> — ᴄᴏᴜɴᴛ ɢɪꜰs/ᴄᴀᴘᴛɪᴏɴs\n"
        "• <code>/clearsocialgifs hug</code> — ᴄʟᴇᴀʀ ᴀʟʟ ɢɪꜰs\n\n"
        "📝 <b>ᴄᴀᴘᴛɪᴏɴꜱ</b>\n"
        "• <code>/addcaption hug Your caption {a} {b}</code>\n"
        "• <code>/socialcaptions hug</code> — sʜᴏᴡ ᴄᴀᴘᴛɪᴏɴ ᴄᴏᴜɴᴛ\n"
        "• <code>/clearsocialcaptions hug</code> — ᴄʟᴇᴀʀ ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴs\n\n"
        "ᴀᴠᴀɪʟᴀʙʟᴇ ᴀᴄᴛɪᴏɴs: " + ", ".join(f"<code>/{x}</code>" for x in COMMANDS)
    )


@app.on_message(filters.command("stats", prefixes=PREFIXES))
async def stats(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    await message.reply(
        "📊 <b>ᴇʟᴀʀᴀ sᴛᴀᴛꜱ</b>\n\n<i>ʙᴏᴛ ɪs ᴏɴʟɪɴᴇ ᴀɴᴅ ᴍᴏᴅᴜʟᴀʀ.</i>"
    )


@app.on_message(filters.command("addgif", prefixes=PREFIXES))
async def add_social_gif(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if not message.reply_to_message:
        return await message.reply("❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪғ/ᴀɴɪᴍᴀᴛɪᴏɴ ᴡɪᴛʜ <code>/addgif hug</code>.")
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜꜱᴀɢᴇ: ʀᴇᴘʟʏ ᴛᴏ ᴀ ɢɪғ ᴡɪᴛʜ <code>/addgif &lt;command&gt;</code>")

    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ. ᴜꜱᴇ <code>/adminhelp</code>.")

    replied = message.reply_to_message
    media = replied.animation or replied.video or replied.document
    if not media:
        return await message.reply("❌ ᴛʜᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇꜱꜱᴀɢᴇ ᴍᴜꜱᴛ ᴄᴏɴᴛᴀɪɴ ᴀ ɢɪғ/ᴀɴɪᴍᴀᴛɪᴏɴ/ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ.")

    if await add_gif(command, media.file_id):
        data = await get_social_data(command)
        await message.reply(
            f"✅ ɢɪғ ᴀᴅᴅᴇᴅ ᴛᴏ <code>/{command}</code>\n"
            f"🎞️ ᴛᴏᴛᴀʟ ɢɪғꜱ: <b>{len(data['gifs'])}</b>"
        )
    else:
        await message.reply("❌ ᴍᴏɴɢᴏᴅʙ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴄʜᴇᴄᴋ <code>MONGO_URI</code>.")


@app.on_message(filters.command("addcaption", prefixes=PREFIXES))
async def add_social_caption(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 3:
        return await message.reply("❌ ᴜꜱᴀɢᴇ: <code>/addcaption hug {a} hugged {b}! ❤️</code>")

    command = message.command[1].lower().lstrip("/")
    caption = message.text.split(None, 2)[2].strip()
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ. ᴜꜱᴇ <code>/adminhelp</code>.")

    if await add_caption(command, caption):
        data = await get_social_data(command)
        await message.reply(
            f"✅ ᴄᴀᴘᴛɪᴏɴ ᴀᴅᴅᴇᴅ ᴛᴏ <code>/{command}</code>\n"
            f"📝 ᴛᴏᴛᴀʟ ᴄᴀᴘᴛɪᴏɴꜱ: <b>{len(data['captions'])}</b>"
        )
    else:
        await message.reply("❌ ᴍᴏɴɢᴏᴅʙ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴄʜᴇᴄᴋ <code>MONGO_URI</code>.")


@app.on_message(filters.command("socialgifs", prefixes=PREFIXES))
async def social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜꜱᴀɢᴇ: <code>/socialgifs hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    data = await get_social_data(command)
    await message.reply(
        f"🎞️ <code>/{command}</code> ɢɪғꜱ: <b>{len(data['gifs'])}</b>\n"
        f"📝 ᴄᴀᴘᴛɪᴏɴꜱ: <b>{len(data['captions'])}</b>"
    )


@app.on_message(filters.command("socialcaptions", prefixes=PREFIXES))
async def social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜꜱᴀɢᴇ: <code>/socialcaptions hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    data = await get_social_data(command)
    await message.reply(
        f"📝 <code>/{command}</code> ʜᴀꜱ <b>{len(data['captions'])}</b> ᴄᴀᴘᴛɪᴏɴ(s)."
    )


@app.on_message(filters.command("clearsocialgifs", prefixes=PREFIXES))
async def clear_social_gifs(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜꜱᴀɢᴇ: <code>/clearsocialgifs hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    ok = await clear_gifs(command)
    await message.reply("🗑️ ᴄᴜꜱᴛᴏᴍ ɢɪғꜱ ᴄʟᴇᴀʀᴇᴅ." if ok else "❌ ᴍᴏɴɢᴏᴅʙ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")


@app.on_message(filters.command("clearsocialcaptions", prefixes=PREFIXES))
async def clear_social_captions(_, message):
    if not await can_manage_social(message):
        return await deny(message)
    if len(message.command or []) < 2:
        return await message.reply("❌ ᴜꜱᴀɢᴇ: <code>/clearsocialcaptions hug</code>")
    command = message.command[1].lower().lstrip("/")
    if command not in COMMANDS:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅ.")
    ok = await clear_captions(command)
    await message.reply("🗑️ ᴄᴜꜱᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ." if ok else "❌ ᴍᴏɴɢᴏᴅʙ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.")


# ══════════════════════════════════════════════════════════════════════════════
#  OWNER ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

_ADMIN_BROADCAST_WAIT = {}


def _panel_owner(message_or_query):
    user = getattr(message_or_query, "from_user", None)
    return bool(user and config.OWNER_ID and int(user.id) == int(config.OWNER_ID))


def _panel_kb():
    return InlineKeyboardMarkup([
        [
            _btn("📊 ᴅᴀꜱʜʙᴏᴀʀᴅ", "adm:dash", enums.ButtonStyle.PRIMARY),
            _btn("👥 ᴜꜱᴇʀꜱ", "adm:users:0", enums.ButtonStyle.SUCCESS),
        ],
        [
            _btn("🚫 ʙᴀɴɴᴇᴅ", "adm:banned:0", enums.ButtonStyle.DANGER),
            _btn("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ", "adm:bcmenu", enums.ButtonStyle.PRIMARY),
        ],
        [
            _btn("📡 ʙᴄ ꜱᴛᴀᴛꜱ", "adm:bcstats", enums.ButtonStyle.SUCCESS),
            _btn("🗄 ᴅᴀᴛᴀʙᴀꜱᴇ", "adm:db", enums.ButtonStyle.PRIMARY),
        ],
        [
            _btn("💰 ᴇᴄᴏɴᴏᴍʏ", "adm:economy", enums.ButtonStyle.SUCCESS),
            _btn("🎁 ɢɪꜰᴛ ꜱʏꜱᴛᴇᴍ", "adm:gift", enums.ButtonStyle.PRIMARY),
        ],
        [
            _btn("🛒 ꜱʜᴏᴘ", "adm:shop", enums.ButtonStyle.PRIMARY),
            _btn("⚙️ ꜱᴏᴄɪᴀʟ", "adm:social", enums.ButtonStyle.SUCCESS),
        ],
        [
            _btn("🔄 ʀᴇꜰʀᴇꜱʜ", "adm:dash", enums.ButtonStyle.PRIMARY),
            _btn("❌ ᴄʟᴏꜱᴇ", "adm:close", enums.ButtonStyle.DANGER),
        ],
    ])


def _broadcast_kb():
    return InlineKeyboardMarkup([
        [_btn("📣 ᴀʟʟ ᴄʜᴀᴛꜱ", "adm:bcmode:all", enums.ButtonStyle.PRIMARY)],
        [
            _btn("👤 ᴘʀɪᴠᴀᴛᴇ ᴜꜱᴇʀꜱ", "adm:bcmode:private", enums.ButtonStyle.SUCCESS),
            _btn("👥 ɢʀᴏᴜᴘꜱ", "adm:bcmode:groups", enums.ButtonStyle.SUCCESS),
        ],
        [
            _btn("🟢 ᴀᴄᴛɪᴠᴇ 7ᴅ", "adm:bcmode:active", enums.ButtonStyle.PRIMARY),
            _btn("🎯 ꜱᴇʟᴇᴄᴛᴇᴅ ɪᴅꜱ", "adm:bcmode:selected", enums.ButtonStyle.PRIMARY),
        ],
        [_btn("⬅️ ʜᴏᴍᴇ", "adm:dash", enums.ButtonStyle.PRIMARY)],
    ])


def _back_to_panel_kb():
    return InlineKeyboardMarkup([
        [
            _btn("⬅️ ʙᴀᴄᴋ", "adm:dash", enums.ButtonStyle.PRIMARY),
            _btn("❌ ᴄʟᴏꜱᴇ", "adm:close", enums.ButtonStyle.DANGER),
        ],
    ])


def _dashboard_text(stats, bc):
    return (
        rich_heading("👑 ᴇʟᴀʀᴀ ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ", level=2)
        + "<i>ᴘᴏᴡᴇʀ & ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ᴄᴇɴᴛᴇʀ</i>\n\n"
        + rich_kv_table([
            ("👥 ᴜꜱᴇʀꜱ",       f"<code>{stats['total']}</code>"),
            ("🟢 ᴀᴄᴛɪᴠᴇ",       f"<code>{stats['active']}</code>"),
            ("🚫 ʙᴀɴɴᴇᴅ",       f"<code>{stats['banned']}</code>"),
            ("💬 ᴛᴏᴛᴀʟ ᴄʜᴀᴛꜱ",  f"<code>{bc['total']}</code>"),
            ("👥 ɢʀᴏᴜᴘꜱ",        f"<code>{bc['groups']}</code>"),
            ("📩 ᴘʀɪᴠᴀᴛᴇ",       f"<code>{bc['private']}</code>"),
        ], headers=["ꜱᴛᴀᴛᴜꜱ", "ᴠᴀʟᴜᴇ"])
        + "\n"
        + rich_note("💡 ᴜꜱᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴꜱ ʙᴇʟᴏᴡ ᴛᴏ ᴍᴀɴᴀɢᴇ ᴜꜱᴇʀꜱ, ʙᴀɴꜱ & ᴍᴏʀᴇ.")
    )


# ─── Sub-page texts ───────────────────────────────────────────────────────────

def _economy_text():
    return (
        rich_heading("💰 ᴇᴄᴏɴᴏᴍʏ ᴏᴡɴᴇʀ ᴄᴏᴍᴍᴀɴᴅꜱ", level=3)
        + rich_kv_table([
            ("/addcoins &lt;amount&gt;",            "ᴀᴅᴅ ᴇᴅᴏʟʟᴇʀꜱ ᴛᴏ ᴜꜱᴇʀ <i>(ʀᴇᴘʟʏ)</i>"),
            ("/add_edollers &lt;amount&gt;",       "ꜱᴀᴍᴇ (ᴀʟɪᴀꜱ)"),
            ("/removecoins &lt;amount&gt;",         "ʀᴇᴍᴏᴠᴇ ᴇᴅᴏʟʟᴇʀꜱ <i>(ʀᴇᴘʟʏ)</i>"),
            ("/remove_edollers &lt;amount&gt;",    "ꜱᴀᴍᴇ (ᴀʟɪᴀꜱ)"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note("💡 ᴀᴅᴅ/ʀᴇᴍᴏᴠᴇ ᴇᴅᴏʟʟᴇʀꜱ ꜰʀᴏᴍ ᴀɴʏ ᴜꜱᴇʀ.")
    )


def _gift_text():
    return (
        rich_heading("🎁 ɢɪꜰᴛ ꜱʏꜱᴛᴇᴍ", level=3)
        + rich_kv_table([
            ("/setgifttext &lt;id&gt; &lt;text&gt;",  "ꜱᴇᴛ ᴄᴜꜱᴛᴏᴍ ɢɪꜰᴛ ᴍᴇꜱꜱᴀɢᴇ"),
            ("/cleargifttext &lt;id&gt;",              "ʀᴇꜱᴇᴛ ɢɪꜰᴛ ᴛᴇxᴛ"),
            ("/resetgifttext &lt;id&gt;",              "ꜱᴀᴍᴇ (ᴀʟɪᴀꜱ)"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note(
            "ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀꜱ: <code>{sender}</code> <code>{item}</code> <code>{target}</code>"
        )
    )


def _shop_text():
    return (
        rich_heading("🛒 ꜱʜᴏᴘ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ", level=3)
        + rich_kv_table([
            ("/shopadd &lt;id&gt; &lt;price&gt; &lt;stock&gt; &lt;name&gt;", "ᴀᴅᴅ ɪᴛᴇᴍ"),
            ("/shopedit &lt;id&gt; &lt;field&gt; &lt;value&gt;",           "ᴇᴅɪᴛ ɪᴛᴇᴍ"),
            ("/shopmedia &lt;id&gt;",                                     "ᴀᴛᴛᴀᴄʜ ᴍᴇᴅɪᴀ <i>(ʀᴇᴘʟʏ)</i>"),
            ("/shopremove &lt;id&gt;",                                    "ᴅᴇʟᴇᴛᴇ ɪᴛᴇᴍ"),
            ("/shopstock &lt;id&gt; &lt;stock&gt;",                       "ꜱᴇᴛ ꜱᴛᴏᴄᴋ"),
            ("/shoptoggle &lt;id&gt; &lt;on/off&gt;",                     "ᴇɴᴀʙʟᴇ/ᴅɪꜱᴀʙʟᴇ"),
            ("/shopgift &lt;id&gt; &lt;on/off&gt;",                       "ɢɪꜰᴛ ᴍᴏᴅᴇ"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note("ᴜꜱᴇ <code>-1</code> ꜰᴏʀ ᴜɴʟɪᴍɪᴛᴇᴅ ꜱᴛᴏᴄᴋ.")
    )


def _social_text():
    return (
        rich_heading("⚙️ ꜱᴏᴄɪᴀʟ ᴀᴅᴍɪɴ", level=3)
        + rich_kv_table([
            ("/adminhelp",           "ꜱᴏᴄɪᴀʟ ʜᴇʟᴘ ᴍᴇɴᴜ"),
            ("/stats",               "ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ"),
            ("/addgif &lt;cmd&gt;",  "ᴀᴅᴅ ɢɪꜰ <i>(ʀᴇᴘʟʏ)</i>"),
            ("/addcaption",          "ᴀᴅᴅ ᴄᴀᴘᴛɪᴏɴ"),
            ("/socialgifs",          "ᴄᴏᴜɴᴛ ɢɪꜰꜱ"),
            ("/socialcaptions",      "ᴄᴏᴜɴᴛ ᴄᴀᴘᴛɪᴏɴꜱ"),
            ("/clearsocialgifs",     "ᴄʟᴇᴀʀ ɢɪꜰꜱ"),
            ("/clearsocialcaptions", "ᴄʟᴇᴀʀ ᴄᴀᴘᴛɪᴏɴꜱ"),
        ], headers=["ᴄᴏᴍᴍᴀɴᴅ", "ᴋᴀᴀᴍ"])
        + "\n"
        + rich_note("💡 ᴏᴡɴᴇʀ ᴏʀ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴ ᴅᴏɴᴏ ᴜꜱᴇ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ.")
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
    title = "🚫 ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ" if banned_only else "👥 ʙᴏᴛ ᴜꜱᴇʀꜱ"
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
        rows.append(("—", "—", "ɴᴏ ᴜꜱᴇʀꜱ ꜰᴏᴜɴᴅ"))
    text = (
        rich_heading(title, level=3)
        + f"<i>ᴛᴏᴛᴀʟ: {total} • ᴘᴀɢᴇ: {page + 1}</i>\n\n"
        + rich_table(["ᴜꜱᴇʀ", "ɪᴅ", "ꜱᴛᴀᴛᴜꜱ"], rows)
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

@app.on_message(filters.command("adminpanel", prefixes=PREFIXES))
async def admin_panel(_, message):
    if not _panel_owner(message):
        return await message.reply(
            "⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>\n\n"
            "<i>ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪꜱ ʀᴇꜱᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ.</i>"
        )
    stats = await get_user_stats()
    bc = await get_broadcast_count()
    await rich_send(
        app, message.chat.id,
        _dashboard_text(stats, bc),
        reply_markup=_panel_kb(),
        reply_to_message_id=message.id,
    )


@app.on_message(filters.command("adminuser", prefixes=PREFIXES))
async def admin_user_lookup(_, message):
    if not _panel_owner(message):
        return await message.reply("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>")
    if len(message.command or []) < 2:
        return await message.reply("ᴜꜱᴀɢᴇ: <code>/adminuser USER_ID</code>")
    try:
        uid = int(message.command[1])
    except ValueError:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ ɪᴅ.")
    doc = await get_user(uid)
    if not doc:
        return await message.reply("❌ ᴜꜱᴇʀ ɪꜱ ɴᴏᴛ ɪɴ ᴛʜᴇ ʙᴏᴛ ᴅᴀᴛᴀʙᴀꜱᴇ.")
    banned = bool(doc.get("banned"))
    joined = doc.get("joined_at")
    last_seen = doc.get("last_seen")
    text = (
        rich_heading("👤 ᴜꜱᴇʀ ᴅᴇᴛᴀɪʟꜱ", level=3)
        + rich_kv_table([
            ("ɴᴀᴍᴇ",      rich_esc(_user_name(doc))),
            ("ɪᴅ",        f"<code>{uid}</code>"),
            ("ꜱᴛᴀᴛᴜꜱ",    "🚫 ʙᴀɴɴᴇᴅ" if banned else "🟢 ᴀᴄᴛɪᴠᴇ"),
            ("ᴊᴏɪɴᴇᴅ",     f"<code>{joined.strftime('%Y-%m-%d') if joined else '—'}</code>"),
            ("ʟᴀꜱᴛ ꜱᴇᴇɴ", f"<code>{last_seen.strftime('%Y-%m-%d %H:%M') if last_seen else '—'}</code>"),
        ], headers=["ꜰɪᴇʟᴅ", "ᴠᴀʟᴜᴇ"])
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
            f"ᴜꜱᴀɢᴇ: <code>/{'banbot' if banned else 'botunban'} USER_ID</code>"
        )
    try:
        uid = int(message.command[1])
    except ValueError:
        return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴜꜱᴇʀ ɪᴅ.")
    if uid == int(config.OWNER_ID):
        return await message.reply("❌ ʏᴏᴜ ᴄᴀɴɴᴏᴛ ʙᴀɴ/ᴜɴʙᴀɴ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ.")
    ok = await set_user_banned(uid, banned, message.from_user.id)
    if not ok:
        return await message.reply("❌ ᴍᴏɴɢᴏᴅʙ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴄʜᴇᴄᴋ <code>MONGO_URI</code>.")
    if banned:
        return await message.reply(
            f"🚫 <b>ᴜꜱᴇʀ ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ ʙᴀɴɴᴇᴅ.</b>\n\n🆔 <code>{uid}</code>\n\n"
            "<i>ᴛʜᴇ ʙᴀɴ ɪꜱ ꜱᴛᴏʀᴇᴅ ɪɴ ᴍᴏɴɢᴏᴅʙ ᴀɴᴅ ꜱᴜʀᴠɪᴠᴇꜱ ʙᴏᴛ ʀᴇꜱᴛᴀʀᴛꜱ.</i>"
        )
    return await message.reply(f"♻️ <b>ᴜꜱᴇʀ ᴜɴʙᴀɴɴᴇᴅ.</b>\n\n🆔 <code>{uid}</code>")


@app.on_message(filters.command("banbot", prefixes=PREFIXES))
async def banbot(_, message):
    return await _direct_ban(message, True)


@app.on_message(filters.command("botunban", prefixes=PREFIXES))
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

    # ✅ Economy sub-page
    if action == "economy":
        return await _edit_panel(query, _economy_text(), _back_to_panel_kb())

    # ✅ Gift sub-page
    if action == "gift":
        return await _edit_panel(query, _gift_text(), _back_to_panel_kb())

    # ✅ Shop sub-page
    if action == "shop":
        return await _edit_panel(query, _shop_text(), _back_to_panel_kb())

    # ✅ Social sub-page
    if action == "social":
        return await _edit_panel(query, _social_text(), _back_to_panel_kb())

    if action in ("ban", "unban"):
        uid = int(parts[2])
        if uid == int(config.OWNER_ID):
            return await query.answer("ʏᴏᴜ ᴄᴀɴɴᴏᴛ ʙᴀɴ ᴛʜᴇ ᴏᴡɴᴇʀ.", show_alert=True)
        ok = await set_user_banned(uid, action == "ban", query.from_user.id)
        if not ok:
            return await query.answer("ᴍᴏɴɢᴏᴅʙ ɪꜱ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
        await query.answer(
            "ᴜꜱᴇʀ ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ ʙᴀɴɴᴇᴅ." if action == "ban" else "ᴜꜱᴇʀ ᴜɴʙᴀɴɴᴇᴅ.",
            show_alert=True,
        )
        return await _edit_panel(
            query,
            _dashboard_text(await get_user_stats(), await get_broadcast_count())
        )

    if action == "bcmenu":
        return await _edit_panel(
            query,
            rich_heading("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴇɴᴛᴇʀ", level=3)
            + rich_note(
                "ᴄʜᴏᴏꜱᴇ ᴡʜᴇʀᴇ ᴛʜᴇ ɴᴇxᴛ ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱʜᴏᴜʟᴅ ɢᴏ.\n\n"
                "🎯 ꜱᴇʟᴇᴄᴛᴇᴅ ɪᴅꜱ ᴀᴄᴄᴇᴘᴛꜱ ᴜꜱᴇʀ/ᴄʜᴀᴛ ɪᴅꜱ ꜱᴇᴘᴀʀᴀᴛᴇᴅ ʙʏ ꜱᴘᴀᴄᴇꜱ ᴏʀ ᴄᴏᴍᴍᴀꜱ."
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
                rich_heading("🎯 ꜱᴇʟᴇᴄᴛᴇᴅ ɪᴅꜱ", level=3)
                + rich_note(
                    "ꜱᴇɴᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴜꜱᴇʀ/ᴄʜᴀᴛ ɪᴅꜱ ꜱᴇᴘᴀʀᴀᴛᴇᴅ ʙʏ ꜱᴘᴀᴄᴇꜱ ᴏʀ ᴄᴏᴍᴍᴀꜱ.\n\n"
                    "ᴇxᴀᴍᴘʟᴇ: <code>123456789, 987654321</code>"
                ),
                InlineKeyboardMarkup([[
                    _btn("❌ ᴄᴀɴᴄᴇʟ", "adm:bccancel", enums.ButtonStyle.DANGER)
                ]]),
            )
        _ADMIN_BROADCAST_WAIT[uid] = {"mode": mode}
        label = {
            "all": "ᴀʟʟ ᴄʜᴀᴛꜱ",
            "private": "ᴘʀɪᴠᴀᴛᴇ ᴜꜱᴇʀꜱ",
            "groups": "ɢʀᴏᴜᴘꜱ",
            "active": "ᴀᴄᴛɪᴠᴇ ᴜꜱᴇʀꜱ (ʟᴀꜱᴛ 7 ᴅᴀʏꜱ)",
        }.get(mode, mode)
        return await _edit_panel(
            query,
            rich_heading(f"📢 {label.upper()}", level=3)
            + rich_note(
                "ꜱᴇɴᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.\n\n"
                "ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴀɴɪᴍᴀᴛɪᴏɴ & ꜰᴏʀᴡᴀʀᴅᴇᴅ ᴍᴇᴅɪᴀ ꜱᴜᴘᴘᴏʀᴛᴇᴅ.\n\n"
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
            rich_heading("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴇɴᴛᴇʀ", level=3)
            + rich_note("ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ."),
            _broadcast_kb(),
        )

    if action == "bcstats":
        bc = await get_broadcast_count()
        return await _edit_panel(
            query,
            rich_heading("📡 ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴛᴀᴛꜱ", level=3)
            + rich_kv_table([
                ("💬 ᴛᴏᴛᴀʟ",  f"<code>{bc['total']}</code>"),
                ("👥 ɢʀᴏᴜᴘꜱ", f"<code>{bc['groups']}</code>"),
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
            rich_heading("🗄 ᴅᴀᴛᴀʙᴀꜱᴇ ꜱᴛᴀᴛᴜꜱ", level=3)
            + rich_kv_table([("ᴍᴏɴɢᴏᴅʙ", state)], headers=["ꜱᴇʀᴠɪᴄᴇ", "ꜱᴛᴀᴛᴜꜱ"])
        )


# ══════════════════════════════════════════════════════════════════════════════
#  BROADCAST
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("cancelbroadcast", prefixes=PREFIXES))
async def cancel_admin_broadcast(_, message):
    if not _panel_owner(message):
        return await message.reply("⛔ <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b>")
    _ADMIN_BROADCAST_WAIT.pop(int(message.from_user.id), None)
    await message.reply("❌ <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>")


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
                return await message.reply("❌ ɴᴏ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅꜱ ꜰᴏᴜɴᴅ.")
            state["ids"] = ids
            state["mode"] = "selected_message"
            return await message.reply(
                "✅ ɪᴅꜱ ꜱᴀᴠᴇᴅ. ɴᴏᴡ ꜱᴇɴᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.\n\n"
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
        return await message.reply("❌ ɴᴏ ᴛᴀʀɢᴇᴛꜱ ꜰᴏᴜɴᴅ ꜰᴏʀ ᴛʜɪꜱ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴍᴏᴅᴇ.")
    status = await message.reply(
        f"📢 <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴛᴀʀᴛᴇᴅ</b>\n\n"
        f"🎯 ᴛᴀʀɢᴇᴛꜱ: <code>{len(targets)}</code>\n⏳ ꜱᴇɴᴅɪɴɢ..."
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
        "<b>📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
        f"🎯 ᴛᴀʀɢᴇᴛꜱ: <code>{len(targets)}</code>\n"
        f"✅ ꜱᴇɴᴛ: <code>{sent}</code>\n"
        f"❌ ꜰᴀɪʟᴇᴅ: <code>{failed}</code>"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL BAN GUARDS (silent — no reply to banned users)
# ══════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.all, group=-100)
async def banned_user_guard(_, message):
    if not message.from_user or _panel_owner(message):
        return
    if await is_user_banned(message.from_user.id):
        raise StopPropagation


@app.on_callback_query(group=-100)
async def banned_callback_guard(_, query):
    if not query.from_user or _panel_owner(query):
        return
    if await is_user_banned(query.from_user.id):
        try:
            await query.answer()
        except Exception:
            pass
        raise StopPropagation
