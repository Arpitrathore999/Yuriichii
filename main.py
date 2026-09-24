import asyncio
from core.bot import app
from core.loader import load_handlers

async def main():
    load_handlers()
    print("Elara Bot started.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
