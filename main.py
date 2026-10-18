import asyncio
import traceback

from pyrogram import idle

from core.bot import app
from core.loader import load_handlers
from core.logger import log_startup, sync_existing_groups


AUTO_REVIVE_INTERVAL = 600

async def auto_revive_loop():
    from core.economy import run_auto_revive_sweep
    await asyncio.sleep(60)
    while True:
        try:
            result = await run_auto_revive_sweep()
            if result["revived"] or result["topped_up"]:
                print(f"[AUTO-REVIVE] revived={result['revived']} topped_up={result['topped_up']} scanned={result['scanned']}", flush=True)
        except Exception as e:
            print(f"[AUTO-REVIVE] sweep crashed: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(AUTO_REVIVE_INTERVAL)


async def _load_wordseek_dictionary():
    try:
        from core.wordseek_engine import ensure_dictionary_loaded, dict_stats
        await ensure_dictionary_loaded()
        stats = dict_stats()
        print(f"[WordSeek] dict ready...", flush=True)
    except Exception as e:
        print(f"[WordSeek] dict load failed: {type(e).__name__}: {e}", flush=True)


async def _recover_wordseek_games():
    try:
        from core.wordseek_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[WordSeek RECOVERY] restored {count} active games", flush=True)
    except Exception as e:
        print(f"[WordSeek RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_ttt_games():
    try:
        from core.ttt_engine import refund_interrupted_games
        count = await refund_interrupted_games()
        if count: print(f"[TTT RECOVERY] refunded {count} interrupted games", flush=True)
    except Exception as e:
        print(f"[TTT RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_rps_games():
    try:
        from core.rps_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[RPS RECOVERY] refunded {count} interrupted games", flush=True)
    except Exception as e:
        print(f"[RPS RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_wordchain_games():
    try:
        from core.wordchain_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[WordChain RECOVERY] cancelled {count} active games", flush=True)
    except Exception as e:
        print(f"[WordChain RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_mafia_games():
    try:
        from core.mafia_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[Mafia RECOVERY] refunded {count} games", flush=True)
    except Exception as e:
        print(f"[Mafia RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_pixelbattle_games():
    try:
        from core.pixelbattle_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[PixelBattle RECOVERY] refunded {count} games", flush=True)
    except Exception as e:
        print(f"[PixelBattle RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_shadow_games():
    try:
        from core.shadow_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[Shadow RECOVERY] cancelled {count} games", flush=True)
    except Exception as e:
        print(f"[Shadow RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_hack_games():
    try:
        from core.hack_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[Hack RECOVERY] refunded {count} games", flush=True)
    except Exception as e:
        print(f"[Hack RECOVERY] {type(e).__name__}: {e}", flush=True)


async def _recover_card_games():
    try:
        from core.card_engine import recover_active_games
        count = await recover_active_games()
        if count: print(f"[Card RECOVERY] refunded {count} games", flush=True)
    except Exception as e:
        print(f"[Card RECOVERY] {type(e).__name__}: {e}", flush=True)


async def main_async():
    load_handlers()
    print("Elara Bot starting...", flush=True)
    asyncio.create_task(auto_revive_loop())
    await app.start()
    uno_runner = None
    try:
        from core.uno_server import start_server
        uno_runner = await start_server()
    except Exception as e:
        print(f"[UNO] Web server failed: {type(e).__name__}: {e}", flush=True)
    print("Elara Bot started.", flush=True)

    await _load_wordseek_dictionary()
    await log_startup()
    await sync_existing_groups()

    print("[RECOVERY] Scanning for interrupted games...", flush=True)
    await _recover_wordseek_games()
    await _recover_ttt_games()
    await _recover_rps_games()
    await _recover_wordchain_games()
    await _recover_mafia_games()
    await _recover_pixelbattle_games()
    await _recover_shadow_games()
    await _recover_hack_games()
    await _recover_card_games()
    print("[RECOVERY] Done.", flush=True)

    try:
        await idle()
    except KeyboardInterrupt:
        pass
    finally:
        if "uno_runner" in locals() and uno_runner:
            await uno_runner.cleanup()
        await app.stop()
        print("Elara Bot stopped.", flush=True)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("Shutdown requested.", flush=True)
    except Exception as e:
        print(f"CRASH: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    main()
