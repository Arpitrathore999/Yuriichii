from pyrogram import filters
from core.bot import app
from utils.helpers import get_reply_target
from modules.social.actions import action, get_gif_file_id

COMMANDS = ["hug","kiss","bite","slap","kick","cuddle","pat","highfive","flirt","love","crush","couple","propose","marriage","divorce"]

def _plain(text):
    import re
    return re.sub(r"<[^>]+>", "", str(text or "")).strip()

@app.on_message(filters.command(COMMANDS))
async def social(_, message):
    command = (message.command[0] if message.command else "").lower().lstrip("/")
    target = None
    try: target = get_reply_target(message)
    except Exception as e: print(f"[SOCIAL TARGET ERROR] {type(e).__name__}: {e}", flush=True)
    if target is None and len(message.command or []) >= 2:
        try: target = await app.get_users(str(message.command[1]).lstrip("@"))
        except Exception as e: print(f"[SOCIAL USER ERROR] {type(e).__name__}: {e}", flush=True)
    if not target or not getattr(target, "id", None):
        return await message.reply_text(f"❌ Reply to a user's message or use `/{command} @username`.")
    if getattr(target, "is_bot", False): return await message.reply_text("🤖 You can't target a bot with this command.")
    if message.from_user and target.id == message.from_user.id: return await message.reply_text("❌ You can't use this command on yourself.")
    try: text = await action(message, command, target)
    except Exception as e:
        print(f"[SOCIAL ACTION ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        text = f"❤️ {message.from_user.first_name if message.from_user else 'Someone'} interacted with {target.first_name or 'someone'}!"
    try: gif = await get_gif_file_id(command)
    except Exception as e:
        print(f"[SOCIAL GIF LOOKUP ERROR] /{command}: {type(e).__name__}: {e}", flush=True); gif = None
    if gif:
        try:
            await message.reply_animation(gif, caption=text, parse_mode="html"); return
        except Exception as e:
            print(f"[SOCIAL GIF HTML ERROR] {type(e).__name__}: {e}", flush=True)
            try: await message.reply_animation(gif, caption=_plain(text)); return
            except Exception as e2: print(f"[SOCIAL GIF PLAIN ERROR] {type(e2).__name__}: {e2}", flush=True)
    try: await message.reply_text(text, parse_mode="html")
    except Exception: await message.reply_text(_plain(text))
