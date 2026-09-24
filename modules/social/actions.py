import random
from .captions import CAPTIONS
from .relationship import get_status, set_status, clear_status

def mention(user):
    name = (user.first_name or "Someone").replace("<","").replace(">","")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

async def action(message, command, target):
    a = mention(message.from_user)
    b = mention(target)

    if command == "love":
        text = random.choice(CAPTIONS["love"]).format(a=a, b=b, pct=random.randint(1,100))
        return text

    if command == "propose":
        status = await get_status(message.from_user.id, target.id)
        if status in {"engaged", "married"}:
            return "💍 Tum dono ka relationship already hai. ❤️"
        await set_status(message.from_user.id, target.id, "engaged")
        return random.choice(CAPTIONS["propose"]).format(a=a,b=b)

    if command == "marriage":
        if await get_status(message.from_user.id, target.id) != "engaged":
            return "❌ Pehle proposal accept hona chahiye. 💍"
        await set_status(message.from_user.id, target.id, "married")
        return CAPTIONS["marriage"][0].format(a=a,b=b)

    if command == "divorce":
        if await get_status(message.from_user.id, target.id) != "married":
            return "😭 Tum dono married hi nahi ho."
        await clear_status(message.from_user.id, target.id)
        return CAPTIONS["divorce"][0].format(a=a,b=b)

    return random.choice(CAPTIONS[command]).format(a=a,b=b,pct=random.randint(1,100))
