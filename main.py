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


async def _load_wordseek_dictionary():
    """One-time: load WordSeek dictionary (auto-downloads 370k words on first run)."""
    try:
        from core.wordseek_engine import ensure_dictionary_loaded, dict_stats
        await ensure_dictionary_loaded()
        stats = dict_stats()
        print(
            f"[WordSeek] dict ready — "
            f"4-letter: {stats[4]['valid']} valid / {stats[4]['answers']} answers, "
            f"5-letter: {stats[5]['valid']} valid / {stats[5]['answers']} answers, "
            f"6-letter: {stats[6]['valid']} valid / {stats[6]['answers']} answers",
            flush=True,
        )
    except Exception as e:
        print(f"[WordSeek] dict load failed: {type(e).__name__}: {e}", flush=True)


async def _recover_wordseek_games():
    """Restart recovery — restore any active WordSeek games from DB."""
    try:
        from core.wordseek_engine import recover_active_games
        count = await recover_active_games()
        if count:
            print(f"[WordSeek RECOVERY] restored {count} active games", flush=True)
    except Exception as e:
        print(f"[WordSeek RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_ttt_games():
    """Optional — recover interrupted TTT games (refunds if any)."""
    try:
        from core.ttt_engine import refund_interrupted_games
        count = await refund_interrupted_games()
        if count:
            print(f"[TTT RECOVERY] refunded {count} interrupted games", flush=True)
    except Exception as e:
        print(f"[TTT RECOVERY] {type(e).__name__}: {e}", flush=True)


async def main_async():
    load_handlers()
    print("Elara Bot starting...", flush=True)

    # ✅ Start background auto-revive task
    asyncio.create_task(auto_revive_loop())

    await app.start()
    print("Elara Bot started.", flush=True)

    # ✅ Load WordSeek dictionary (one-time; auto-downloads 370k words on first run)
    await _load_wordseek_dictionary()

    # ✅ Startup logs + group sync
    await log_startup()
    await sync_existing_groups()

    # ✅ Recover active games from DB (safe restart)
    await _recover_wordseek_games()
    await _recover_ttt_games()

    await idle()

    await app.stop()
    print("Elara Bot stopped.", flush=True)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
