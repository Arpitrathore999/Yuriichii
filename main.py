import asyncio

from pyrogram import idle

from core.bot import app
from core.loader import load_handlers
from core.logger import log_startup, sync_existing_groups


AUTO_REVIVE_INTERVAL = 600  # 10 min


async def auto_revive_loop():
    from core.economy import run_auto_revive_sweep

    await asyncio.sleep(60)

    while True:
        try:
            result = await run_auto_revive_sweep()
            if result["revived"] or result["topped_up"]:
                print(
                    f"[AUTO-REVIVE] revived={result['revived']} "
                    f"topped_up={result['topped_up']} "
                    f"scanned={result['scanned']}",
                    flush=True,
                )
        except Exception as e:
            print(f"[AUTO-REVIVE] sweep crashed: {type(e).__name__}: {e}", flush=True)

        await asyncio.sleep(AUTO_REVIVE_INTERVAL)


async def main_async():
    load_handlers()
    print("Elara Bot starting...", flush=True)

    # ✅ Start background auto-revive
    asyncio.create_task(auto_revive_loop())

    await app.start()
    print("Elara Bot started.", flush=True)

    # ✅ Log startup + sync groups
    await log_startup()
    await sync_existing_groups()

    await idle()

    await app.stop()
    print("Elara Bot stopped.", flush=True)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
