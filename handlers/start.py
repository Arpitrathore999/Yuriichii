# --------------------------------------------------------------------------------
#  Elara AI Bot © 2026
#  Rich UI Start & Help Module
# --------------------------------------------------------------------------------

import asyncio
import random

from pyrogram import enums, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from core.bot import app   # ✅ YOUR BOT INSTANCE
from database.users import ensure_user

# ✅ Alias so both `bot` and `app` work
bot = app


# ─── Rich UI Helpers (fallback if rich_ui.py missing) ────────────────────────
try:
    from utils.rich_ui import (
        rich_details,
        rich_esc,
        rich_heading,
        rich_img,
        rich_kv_table,
        rich_note,
        rich_send,
        rich_table,
        rich_edit,
        sanitize_display_name,
    )
except ImportError:
    def rich_esc(v):
        return (
            str(v or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def sanitize_display_name(name):
        return rich_esc(name or "there")

    def rich_img(url):
        return ""

    def rich_heading(text, level=3):
        return f"<b>{text}</b>\n"

    def rich_note(text):
        return f"{text}\n"

    def rich_details(title, body, open=True):
        return f"<b>{title}</b>\n{body}\n"

    def rich_kv_table(rows):
        lines = []
        for k, v in rows:
            lines.append(f"• <b>{k}:</b> {v}")
        return "\n".join(lines) + "\n"

    def rich_table(headers, rows):
        lines = [" | ".join(f"<b>{h}</b>" for h in headers)]
        lines.append("─" * 20)
        for r in rows:
            lines.append(" | ".join(str(c) for c in r))
        return "\n".join(lines) + "\n"

    async def rich_send(client, chat_id, text, reply_markup=None, photo=None):
        return await client.send_message(
            chat_id, text, reply_markup=reply_markup,
            parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )

    async def rich_edit(message, text, reply_markup=None):
        try:
            return await message.edit_text(
                text, reply_markup=reply_markup,
                parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            )
        except Exception:
            return None


# ─── Config helpers ──────────────────────────────────────────────────────────
BOT_NAME = getattr(config, "BOT_NAME", "Elara")
BOT_LINK = getattr(config, "BOT_LINK", "https://t.me/")
BOT_USERNAME = getattr(config, "BOT_USERNAME", "")
SUPPORT_GROUP = getattr(config, "SUPPORT_GROUP", "") or getattr(config, "SUPPORT_URL", "https://t.me/")
UPDATES_CHANNEL = getattr(config, "UPDATES_CHANNEL", "") or getattr(config, "UPDATES_URL", "https://t.me/")
OWNER_ID = getattr(config, "OWNER_ID", 0)
SOURCE_URL = getattr(config, "SOURCE_URL", "https://t.me/")
LOGGER_ID = getattr(config, "LOGGER_ID", 0)
START_PHOTOS = getattr(config, "START_PHOTOS", []) or [
    "https://telegra.ph/file/7f7c5c0e1a0e0e0e0e0e0.jpg"
]


def _support_updates_pills() -> str:
    return (
        f'<p>🍬 <a href="{SUPPORT_GROUP}">sᴜᴘᴘᴏʀᴛ</a> | '
        f'🍹 <a href="{UPDATES_CHANNEL}">ᴜᴘᴅᴀᴛᴇs</a></p>'
    )


def _home_caption(uid: int, name: str) -> str:
    return (
        rich_note(
            f"<p>❍ ʜᴇʏ <a href='tg://user?id={uid}'>{rich_esc(name)}</a>, "
            "ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 🌙</p>"
            f"<p>ɪ ᴀᴍ <b>{rich_esc(BOT_NAME)}</b> — ᴀ ғᴀsᴛ &amp; "
            "ғʀɪᴇɴᴅʟʏ ᴛᴇʟᴇɢʀᴀᴍ ᴀɪ ᴄᴏᴍᴘᴀɴɪᴏɴ ᴡɪᴛʜ sᴏᴍᴇ "
            "ᴀᴡᴇsᴏᴍᴇ ғᴇᴀᴛᴜʀᴇs. ✨</p>"
        )
        + rich_details(
            "✦ ᴋᴇʏ ғᴇᴀᴛᴜʀᴇs ✦",
            rich_table(
                ["ғᴇᴀᴛᴜʀᴇ", "ᴅᴇᴛᴀɪʟs"],
                [
                    ("🤖 ᴀɪ ᴄʜᴀᴛ", "ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs"),
                    ("🧠 ᴍᴇᴍᴏʀʏ", "ʀᴇᴄᴇɴᴛ ᴄʜᴀᴛ ᴄᴏɴᴛᴇxᴛ ᴜsᴇᴅ"),
                    ("💕 sᴏᴄɪᴀʟ", "ғᴜɴ ɢʀᴏᴜᴘ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs"),
                    ("⚡ ғᴀsᴛ", "ǫᴜɪᴄᴋ ᴀɪ ʀᴇsᴘᴏɴsᴇs"),
                ],
            ),
            open=True,
        )
        + rich_details(
            "✧ ᴡʜʏ ᴄʜᴏᴏsᴇ ɪᴛ? ✧",
            "<p>⭐ ɴᴀᴛᴜʀᴀʟ ᴀɪ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴs.</p>"
            "<p>🧠 sᴍᴀʀᴛ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ ᴍᴇᴍᴏʀʏ.</p>"
            "<p>💕 ғᴜɴ sᴏᴄɪᴀʟ ᴄᴏᴍᴍᴀɴᴅs.</p>"
            "<p>❍ ᴄʟɪᴄᴋ ʜᴇʟᴘ ʙᴇʟᴏᴡ ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.</p>",
            open=True,
        )
        + rich_note(f"ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <a href='{SOURCE_URL}'>ᴇʟᴀʀᴀ ᴀɪ</a>")
        + _support_updates_pills()
    )


def _home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⛩️ ᴀᴅᴅ ᴍᴇ ʙᴀʙʏ ⛩️",
            url=f"{BOT_LINK}?startgroup=true",
        )],
        [
            InlineKeyboardButton("🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=SUPPORT_GROUP),
            InlineKeyboardButton("🍹 ᴜᴘᴅᴀᴛᴇs 🍹", url=UPDATES_CHANNEL),
        ],
        [InlineKeyboardButton("🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
                              callback_data="elara:help")],
        [
            InlineKeyboardButton("🫧 ᴏᴡɴᴇʀ 🫧",
                                 url=f"tg://user?id={OWNER_ID}"),
            InlineKeyboardButton("🍡 sᴏᴜʀᴄᴇ 🍡",
                                 url=SOURCE_URL),
        ],
    ])


# ─── Help Menu ───────────────────────────────────────────────────────────────
_HELP_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🤖 ᴀɪ", callback_data="elara:ai"),
        InlineKeyboardButton("💕 sᴏᴄɪᴀʟ", callback_data="elara:social"),
    ],
    [
        InlineKeyboardButton("⌯ ʜᴏᴍᴇ ⌯", callback_data="elara:home"),
    ],
])

_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("⌯ ʙᴀᴄᴋ ⌯", callback_data="elara:help")],
    [InlineKeyboardButton("⌯ ᴄʟᴏsᴇ ⌯", callback_data="elara:close")],
])


# ─── Help Texts ──────────────────────────────────────────────────────────────
_HELP_TEXTS = {
    "elara:ai": {
        "title": "🤖 ᴇʟᴀʀᴀ ᴀɪ ᴄᴏᴍᴍᴀɴᴅs",
        "desc": "ᴄʜᴀᴛ, ᴍᴇᴍᴏʀʏ &amp; ɢʀᴏᴜᴘ ᴀɪ ғᴇᴀᴛᴜʀᴇs.",
        "rows": [
            ("/ai &lt;message&gt;", "ᴄʜᴀᴛ ᴡɪᴛʜ ᴇʟᴀʀᴀ ᴀɪ"),
            ("ᴅᴍ ᴀɴʏ ᴍᴇssᴀɢᴇ", "ᴀɪ ʀᴇᴘʟɪᴇs ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ"),
            ("ᴇʟᴀʀᴀ ʜᴇʟʟᴏ", "ɢʀᴏᴜᴘ ᴛʀɪɢɢᴇʀ"),
            ("@BotUsername ʜɪ", "ᴍᴇɴᴛɪᴏɴ ᴛʀɪɢɢᴇʀ"),
            ("ʀᴇᴘʟʏ ᴛᴏ ᴇʟᴀʀᴀ", "ᴄᴏɴᴛᴇxᴛ ᴄʜᴀᴛ"),
        ],
    },
    "elara:social": {
        "title": "💕 ᴇʟᴀʀᴀ sᴏᴄɪᴀʟ",
        "desc": "ғᴜɴ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴs ғᴏʀ ʏᴏᴜʀ ɢʀᴏᴜᴘ.",
        "rows": [
            ("/hug", "🫂 ʜᴜɢ ᴀ ᴜsᴇʀ"),
            ("/kiss", "💋 ᴋɪss ᴀ ᴜsᴇʀ"),
            ("/bite", "🧛 ʙɪᴛᴇ ᴀ ᴜsᴇʀ"),
            ("/slap", "👋 sʟᴀᴘ ᴀ ᴜsᴇʀ"),
            ("/kick", "🦵 ᴋɪᴄᴋ ᴀ ᴜsᴇʀ"),
            ("/cuddle", "🫶 ᴄᴜᴅᴅʟᴇ ᴀ ᴜsᴇʀ"),
            ("/pat", "🫳 ᴘᴀᴛ ᴀ ᴜsᴇʀ"),
            ("/highfive", "✋ ʜɪɢʜ ғɪᴠᴇ"),
            ("/flirt", "😏 ғʟɪʀᴛ"),
            ("/love", "❤️ ʟᴏᴠᴇ"),
            ("/crush", "💘 ᴄʀᴜsʜ"),
            ("/couple", "💞 ᴄᴏᴜᴘʟᴇ"),
            ("/propose", "💍 ᴘʀᴏᴘᴏsᴇ"),
            ("/marriage", "💒 ᴍᴀʀʀɪᴀɢᴇ"),
            ("/divorce", "💔 ᴅɪᴠᴏʀᴄᴇ"),
        ],
    },
}


def _category_html(title: str, desc: str, rows) -> str:
    return (
        rich_heading(title, level=3)
        + f"<p>{desc}</p>"
        + rich_table(["ᴄᴏᴍᴍᴀɴᴅ", "ᴅᴇsᴄʀɪᴘᴛɪᴏɴ"], rows)
        + _support_updates_pills()
    )


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS  —  ✅ Uses `bot` (aliased to `app`)
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("start"))
async def start_handler(_, message: Message) -> None:
    uid = message.from_user.id
    name = sanitize_display_name(message.from_user.first_name)
    chat_id = message.chat.id
    chat_type = message.chat.type

    try:
        await message.delete()
    except Exception:
        pass

    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    if chat_type == ChatType.PRIVATE:
        caption = _home_caption(uid, name)
        kb = _home_kb()
        try:
            await bot.send_message(
                chat_id, caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            await bot.send_message(
                chat_id, caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

        if LOGGER_ID:
            try:
                username = message.from_user.username
                username_display = f"@{rich_esc(username)}" if username else "N/A"
                logger_caption = (
                    rich_heading("#ɴᴇᴡᴜsᴇʀ sᴛᴀʀᴛᴇᴅ", level=2)
                    + rich_kv_table([
                        ("ɴᴀᴍᴇ", f'<a href="tg://user?id={uid}">{rich_esc(name)}</a>'),
                        ("ɪᴅ", f"<code>{uid}</code>"),
                        ("ᴜsᴇʀɴᴀᴍᴇ", username_display),
                    ])
                )
                await bot.send_message(
                    LOGGER_ID, logger_caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception as e:
                print(f"[start_handler] Logger error: {e}")

    else:
        chat_title = message.chat.title or "this chat"
        caption = (
            f"<p>❍ ʜᴇʏ <a href='tg://user?id={uid}'>{rich_esc(name)}</a>, "
            f"ᴛʜɪs ɪs <b>{rich_esc(BOT_NAME)}</b></p>"
            + rich_note(
                f"ᴛʜᴀɴᴋs ғᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ ɪɴ {rich_esc(chat_title)}. "
                f"{rich_esc(name)} ᴄᴀɴ ɴᴏᴡ ᴛᴀʟᴋ ᴡɪᴛʜ ᴍᴇ ʜᴇʀᴇ. 🌙"
            )
            + _support_updates_pills()
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⛩️ ᴀᴅᴅ ᴍᴇ ʙᴀʙʏ ⛩️",
                                     url=f"{BOT_LINK}?startgroup=true"),
                InlineKeyboardButton("🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=SUPPORT_GROUP),
            ],
            [InlineKeyboardButton("🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
                                  callback_data="elara:help")],
        ])
        try:
            await bot.send_message(
                chat_id, caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            await bot.send_message(
                chat_id, caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )


@bot.on_message(filters.command("help"))
async def help_handler(_, message: Message) -> None:
    uid = message.from_user.id
    name = sanitize_display_name(message.from_user.first_name)

    try:
        await message.delete()
    except Exception:
        pass

    caption = (
        rich_heading("📜 ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ", level=3)
        + rich_note(
            f'<p>❍ ʜᴇʏ <a href="tg://user?id={uid}">{rich_esc(name)}</a>, '
            "ᴘɪᴄᴋ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ ᴛᴏ sᴇᴇ ɪᴛs ᴄᴏᴍᴍᴀɴᴅs.</p>"
        )
        + rich_details(
            "✦ ʜᴇʟᴘ ғᴇᴀᴛᴜʀᴇs ✦",
            rich_table(
                ["ғᴇᴀᴛᴜʀᴇ", "ᴅᴇᴛᴀɪʟs"],
                [
                    ("✉️ ʜᴇʟᴘ ᴍᴇɴᴜ", "ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs ᴄᴀɴ ʙᴇ ᴜsᴇᴅ ᴡɪᴛʜ : /"),
                ],
            ),
            open=True,
        )
        + rich_note(f"ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <a href='{SOURCE_URL}'>ᴇʟᴀʀᴀ ᴀɪ</a>")
        + _support_updates_pills()
    )

    await bot.send_message(
        message.chat.id, caption,
        reply_markup=_HELP_KB,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


@bot.on_callback_query(filters.regex(r"^elara:(home|help|ai|social|close)$"))
async def callback_handler(_, cbq) -> None:
    data = cbq.data
    chat_id = cbq.message.chat.id
    uid = cbq.from_user.id
    name = sanitize_display_name(cbq.from_user.first_name)

    if data == "elara:close":
        await cbq.answer()
        try:
            await cbq.message.delete()
        except Exception:
            pass
        return

    if data == "elara:home":
        await cbq.answer()
        caption = _home_caption(uid, name)
        kb = _home_kb()
        try:
            await cbq.message.delete()
        except Exception:
            pass
        await bot.send_message(
            chat_id, caption,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    if data == "elara:help":
        await cbq.answer()
        caption = (
            rich_heading("📜 ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ", level=3)
            + rich_note(
                f'<p>❍ ʜᴇʏ <a href="tg://user?id={uid}">{rich_esc(name)}</a>, '
                "ᴘɪᴄᴋ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ ᴛᴏ sᴇᴇ ɪᴛs ᴄᴏᴍᴍᴀɴᴅs.</p>"
            )
            + rich_note(f"ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <a href='{SOURCE_URL}'>ᴇʟᴀʀᴀ ᴀɪ</a>")
            + _support_updates_pills()
        )
        try:
            await cbq.message.delete()
        except Exception:
            pass
        await bot.send_message(
            chat_id, caption,
            reply_markup=_HELP_KB,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    if data in ("elara:ai", "elara:social"):
        await cbq.answer()
        help_data = _HELP_TEXTS.get(data)
        if help_data:
            text = _category_html(
                help_data["title"],
                help_data["desc"],
                help_data["rows"],
            )
            try:
                await cbq.message.edit_text(
                    text,
                    reply_markup=_BACK_KB,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                pass