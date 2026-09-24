import random

from .settings import get_social_data, DEFAULT_CAPTIONS
from .relationship import get_status, set_status, clear_status


def mention(user):
    name = (getattr(user, "first_name", None) or "Someone")
    name = (
        name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def render_caption(template, a, b):
    """Render an admin caption safely. A bad custom caption must never break a social command."""
    try:
        return template.format(a=a, b=b, pct=random.randint(1, 100))
    except (KeyError, IndexError, ValueError):
        fallback = "{a} interacted with {b} ❤️"
        return fallback.format(a=a, b=b)


async def get_gif_file_id(command):
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
    text = render_caption(random.choice(captions), a, b)

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
