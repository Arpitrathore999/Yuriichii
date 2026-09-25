import random
from pathlib import Path

from .settings import get_social_data, DEFAULT_CAPTIONS
from .relationship import get_status, set_status, clear_status


# Local social media is stored in: <project root>/assets/social/<command>/
SUPPORTED_MEDIA = {".gif", ".mp4", ".webm", ".jpg", ".jpeg", ".png", ".webp"}


def mention(user):
    user_id = getattr(user, "id", None)
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "Someone"
    name = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Telegram HTML mention: the visible name is clickable and resolves to the real user ID.
    return f'<a href="tg://user?id={int(user_id)}">{name}</a>' if user_id else name


def render_caption(template, a, b):
    fallback = "{a} interacted with {b} ❤️"
    try:
        if not isinstance(template, str) or not template.strip():
            template = fallback
        return template.format(a=a, b=b, pct=random.randint(1, 100))
    except Exception as e:
        print(f"[SOCIAL CAPTION ERROR] {type(e).__name__}: {e}", flush=True)
        return fallback.format(a=a, b=b)


def get_local_media(command):
    """Return a random real media file from assets/social/<command>."""
    try:
        # actions.py -> social -> modules -> project root
        project_root = Path(__file__).resolve().parents[2]
        folder = project_root / "assets" / "social" / command

        if not folder.is_dir():
            print(f"[SOCIAL MEDIA] folder not found: {folder}", flush=True)
            return None

        files = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_MEDIA
        )

        if not files:
            print(f"[SOCIAL MEDIA] no supported media in: {folder}", flush=True)
            return None

        selected = random.choice(files)
        print(f"[SOCIAL MEDIA] /{command} -> {selected}", flush=True)
        return str(selected)
    except Exception as e:
        print(f"[SOCIAL MEDIA ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return None


async def get_gif_file_id(command):
    # Keep the old function name so existing imports continue to work.
    local_media = get_local_media(command)
    if local_media:
        return local_media

    # Manual assets are the only media source now.
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
