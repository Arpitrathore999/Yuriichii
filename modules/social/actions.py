import random

from .settings import get_social_data
from .relationship import get_status, set_status, clear_status


def mention(user):
    name = (user.first_name or "Someone")
    name = (
        name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def get_gif_file_id(command):
    data = await get_social_data(command)
    gifs = data.get("gifs") or []
    return random.choice(gifs) if gifs else None


async def action(message, command, target):
    a = mention(message.from_user)
    b = mention(target)
    data = await get_social_data(command)
    captions = data.get("captions") or []

    if command == "love":
        text = random.choice(captions).format(a=a, b=b, pct=random.randint(1, 100))
        return text

    if command == "propose":
        status = await get_status(message.from_user.id, target.id)
        if status in {"engaged", "married"}:
            return "💍 Tum dono ka relationship already hai. ❤️"
        await set_status(message.from_user.id, target.id, "engaged")
        return random.choice(captions).format(a=a, b=b, pct=random.randint(1, 100))

    if command == "marriage":
        if await get_status(message.from_user.id, target.id) != "engaged":
            return "❌ Pehle proposal accept hona chahiye. 💍"
        await set_status(message.from_user.id, target.id, "married")
        return random.choice(captions).format(a=a, b=b, pct=random.randint(1, 100))

    if command == "divorce":
        if await get_status(message.from_user.id, target.id) != "married":
            return "😭 Tum dono married hi nahi ho."
        await clear_status(message.from_user.id, target.id)
        return random.choice(captions).format(a=a, b=b, pct=random.randint(1, 100))

    return random.choice(captions).format(a=a, b=b, pct=random.randint(1, 100))
