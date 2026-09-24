import random

from .settings import get_social_data, DEFAULT_CAPTIONS
from .relationship import get_status, set_status, clear_status


def mention(user):
    user_id = getattr(user, "id", None)
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone"
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if user_id:
        return f'<a href="tg://user?id={int(user_id)}">{name}</a>'
    return name


def render_caption(template, a, b):
    fallback = "{a} interacted with {b} ❤️"
    try:
        if not isinstance(template, str) or not template.strip():
            template = fallback
        return template.format(a=a, b=b, pct=random.randint(1, 100))
    except Exception as e:
        print(f"[SOCIAL CAPTION ERROR] {type(e).__name__}: {e}", flush=True)
        return fallback.format(a=a, b=b)


async def get_gif_file_id(command):
    # Manual GIFs: assets/social/<command>/*.gif
    try:
        from pathlib import Path
        base = Path(__file__).resolve().parents[2] / "assets" / "social" / command
        files = [p for p in base.glob("*") if p.is_file() and p.suffix.lower() == ".gif"] if base.exists() else []
        if files:
            return str(random.choice(files))
    except Exception as e:
        print(f"[SOCIAL LOCAL GIF ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    # Backward-compatible MongoDB file_id fallback.
    try:
        data = await get_social_data(command)
        gifs = data.get("gifs") or []
        return random.choice(gifs) if gifs else None
    except Exception as e:
        print(f"[SOCIAL GIF DB ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return None


async def action(message, command, target):
    a = mention(message.from_user)
    b = mention(target)

    try:
        data = await get_social_data(command)
    except Exception as e:
        print(f"[SOCIAL DATA ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        data = {"captions": []}

    captions = data.get("captions") or DEFAULT_CAPTIONS.get(command) or ["{a} interacted with {b} ❤️"]
    try:
        template = random.choice(captions)
    except Exception:
        template = "{a} interacted with {b} ❤️"
    text = render_caption(template, a, b)

    if command == "propose":
        try:
            status = await get_status(message.from_user.id, target.id)
            if status in {"engaged", "married"}:
                return "💍 Tum dono ka relationship already hai. ❤️"
            await set_status(message.from_user.id, target.id, "engaged")
        except Exception as e:
            print(f"[SOCIAL RELATIONSHIP ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    elif command == "marriage":
        try:
            if await get_status(message.from_user.id, target.id) != "engaged":
                return "❌ Pehle proposal accept hona chahiye. 💍"
            await set_status(message.from_user.id, target.id, "married")
        except Exception as e:
            print(f"[SOCIAL RELATIONSHIP ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    elif command == "divorce":
        try:
            if await get_status(message.from_user.id, target.id) != "married":
                return "😭 Tum dono married hi nahi ho."
            await clear_status(message.from_user.id, target.id)
        except Exception as e:
            print(f"[SOCIAL RELATIONSHIP ERROR] /{command}: {type(e).__name__}: {e}", flush=True)

    return text
