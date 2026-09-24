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
from core.bot import app
from database.users import ensure_user


# ─── Rich UI Helpers (agar aapke paas rich_ui.py nahi hai to yeh fallback) ───
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
    # ── Fallback: simple HTML helpers ─────────────────────────────────────────
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
        return f'<a href="{url}">&#8203;</a>' if url else ""

    def rich_heading(text, level=3):
        sizes = {1: "24", 2: "20", 3: "18", 4: "16"}
        return f'<b><u>{text}</u></b>\n'

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
        "<p>"
        f'<tg-button type="url" style="primary" url="{SUPPORT_GROUP}">'
        "🍬 sᴜᴘᴘᴏʀᴛ</tg-button> "
        f'<tg-button type="url" style="success" url="{UPDATES_CHANNEL}">'
        "🍹 ᴜᴘᴅᴀᴛᴇs</tg-button>"
        "</p>"
    )


# ─── Home Caption Builder ────────────────────────────────────────────────────
def _home_caption(uid: int, name: str, photo: str) -> str:
    return (
        rich_img(photo)
        + rich_note(
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
        + rich_note(f"ᴘᴏᴡᴇʀᴇᴅ ʙʏ » <a href='https://t.me/{BOT_LINK.split('/')[-1]}'>ᴇʟᴀʀᴀ ᴀɪ</a>")
        + _support_updates_pills()
    )


def _home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⛩️ ᴀᴅᴅ ᴍᴇ ʙᴀʙʏ ⛩️",
            url=f"{BOT_LINK}?startgroup=true",
            style=enums.ButtonStyle.PRIMARY,
        )],
        [
            InlineKeyboardButton("🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=SUPPORT_GROUP,
                                 style=enums.ButtonStyle.SUCCESS),
            InlineKeyboardButton("🍹 ᴜᴘᴅᴀᴛᴇs 🍹", url=UPDATES_CHANNEL,
                                 style=enums.ButtonStyle.SUCCESS),
        ],
        [InlineKeyboardButton("🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
                              callback_data="elara:help",
                              style=enums.ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton("🫧 ᴏᴡɴᴇʀ 🫧",
                                 url=f"tg://user?id={OWNER_ID}",
                                 style=enums.ButtonStyle.DEFAULT),
            InlineKeyboardButton("🍡 sᴏᴜʀᴄᴇ 🍡",
                                 url=SOURCE_URL,
                                 style=enums.ButtonStyle.DEFAULT),
        ],
    ])


# ─── Help Menu ───────────────────────────────────────────────────────────────
_HELP_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🤖 ᴀɪ", callback_data="elara:ai",
                             style=enums.ButtonStyle.PRIMARY),
        InlineKeyboardButton("💕 sᴏᴄɪᴀʟ", callback_data="elara:social",
                             style=enums.ButtonStyle.SUCCESS),
    ],
    [
        InlineKeyboardButton("⌯ ʜᴏᴍᴇ ⌯", callback_data="elara:home",
                             style=enums.ButtonStyle.SUCCESS),
    ],
])

_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("⌯ ʙᴀᴄᴋ ⌯", callback_data="elara:help",
                          style=enums.ButtonStyle.PRIMARY)],
    [InlineKeyboardButton("⌯ ᴄʟᴏsᴇ ⌯", callback_data="elara:close",
                          style=enums.ButtonStyle.DANGER)],
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


def _category_html(title: str, desc: str, rows, photo: str = None) -> str:
    html = ""
    if photo:
        html += rich_img(photo)
    return (
        html
        + rich_heading(title, level=3)
        + f"<p>{desc}</p>"
        + rich_table(["ᴄᴏᴍᴍᴀɴᴅ", "ᴅᴇsᴄʀɪᴘᴛɪᴏɴ"], rows)
        + _support_updates_pills()
    )


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_message(filters.command("start"))
async def start_handler(_, message: Message) -> None:
    uid = message.from_user.id
    name = sanitize_display_name(message.from_user.first_name)
    chat_id = message.chat.id
    chat_type = message.chat.type
    photo = random.choice(START_PHOTOS)

    # Delete command message
    try:
        await message.delete()
    except Exception:
        pass

    # Ensure user in DB
    try:
        await ensure_user(message.from_user)
    except Exception:
        pass

    # ── Private Chat ─────────────────────────────────────────────────────────
    if chat_type == ChatType.PRIVATE:
        caption = _home_caption(uid, name, photo)
        kb = _home_kb()

        try:
            await rich_send(bot, chat_id, caption, reply_markup=kb)
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            await rich_send(bot, chat_id, caption, reply_markup=kb)

        # Log new user
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
                await rich_send(bot, LOGGER_ID, logger_caption)
            except Exception as e:
                print(f"[start_handler] Logger error: {e}")

    # ── Group Chat ───────────────────────────────────────────────────────────
    else:
        chat_title = message.chat.title or "this chat"
        caption = (
            rich_img(photo)
            + f"<p>❍ ʜᴇʏ <a href='tg://user?id={uid}'>{rich_esc(name)}</a>, "
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
                                     url=f"{BOT_LINK}?startgroup=true",
                                     style=enums.ButtonStyle.PRIMARY),
                InlineKeyboardButton("🍬 sᴜᴘᴘᴏʀᴛ 🍬", url=SUPPORT_GROUP,
                                     style=enums.ButtonStyle.SUCCESS),
            ],
            [InlineKeyboardButton("🏩 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅs 🏩",
                                  callback_data="elara:help",
                                  style=enums.ButtonStyle.PRIMARY)],
        ])

        try:
            await rich_send(bot, chat_id, caption, reply_markup=kb)
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            await rich_send(bot, chat_id, caption, reply_markup=kb)


@bot.on_message(filters.command("help"))
async def help_handler(_, message: Message) -> None:
    uid = message.from_user.id
    name = sanitize_display_name(message.from_user.first_name)
    photo = random.choice(START_PHOTOS)

    try:
        await message.delete()
    except Exception:
        pass

    caption = (
        rich_heading("📜 ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ", level=3)
        + rich_img(photo)
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

    await rich_send(bot, message.chat.id, caption, reply_markup=_HELP_KB)


@bot.on_callback_query(filters.regex(r"^elara:(home|help|ai|social|close)$"))
async def callback_handler(_, cbq) -> None:
    data = cbq.data
    chat_id = cbq.message.chat.id
    uid = cbq.from_user.id
    name = sanitize_display_name(cbq.from_user.first_name)

    # ── Close ────────────────────────────────────────────────────────────────
    if data == "elara:close":
        await cbq.answer()
        try:
            await cbq.message.delete()
        except Exception:
            pass
        return

    # ── Home ─────────────────────────────────────────────────────────────────
    if data == "elara:home":
        await cbq.answer()
        photo = random.choice(START_PHOTOS)
        caption = _home_caption(uid, name, photo)
        kb = _home_kb()

        try:
            await cbq.message.delete()
        except Exception:
            pass

        await rich_send(bot, chat_id, caption, reply_markup=kb)
        return

    # ── Help Menu ────────────────────────────────────────────────────────────
    if data == "elara:help":
        await cbq.answer()
        photo = random.choice(START_PHOTOS)
        caption = (
            rich_heading("📜 ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ", level=3)
            + rich_img(photo)
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

        try:
            await cbq.message.delete()
        except Exception:
            pass

        await rich_send(bot, chat_id, caption, reply_markup=_HELP_KB)
        return

    # ── Help Categories ──────────────────────────────────────────────────────
    if data in ("elara:ai", "elara:social"):
        await cbq.answer()
        photo = random.choice(START_PHOTOS)
        help_data = _HELP_TEXTS.get(data)
        if help_data:
            text = _category_html(
                help_data["title"],
                help_data["desc"],
                help_data["rows"],
                photo,
            )
            await rich_edit(cbq.message, text, reply_markup=_BACK_KB)