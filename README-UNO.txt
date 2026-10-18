ELARA UNO INTEGRATION PATCH

Includes changed/new files only from Yuriichii-main:
- handlers/uno.py (updated URL fallback)
- core/uno_engine.py (server-authoritative classic UNO rules)
- core/uno_server.py (NEW HTTP + WebSocket backend; uses aiohttp already in requirements)
- core/loader.py (existing loader with handlers.uno registered; included to preserve exact patch state)
- main.py (starts the UNO web server on Railway's PORT)
- uno_web/index.html (online lobby/game UI)

RAILWAY SETUP
1. Merge these files into the matching paths in your existing GitHub repository.
2. Make sure Railway has BOT_TOKEN set (same bot token used by Elara) and RAILWAY_PUBLIC_DOMAIN is available. If Railway does not expose RAILWAY_PUBLIC_DOMAIN, set UNO_WEBAPP_URL to https://YOUR-RAILWAY-DOMAIN.
3. Railway must expose the same service's HTTP port via its assigned PORT. The bot and UNO web server run in the same process.
4. Commit and deploy. Open https://YOUR-RAILWAY-DOMAIN/health; expected JSON: {"ok": true, "service": "elara-uno"}.
5. In Telegram, run /uno, open Play UNO. Create a room. Other players open /uno and enter the displayed room code, then Join. Host presses Start Game.

RULES IMPLEMENTED
- 2-6 human players; 7 cards each
- Match current colour or top-card symbol/value
- Wild and Wild Draw Four require chosen colour
- Skip, Reverse (including 2-player reverse acts as skip), Draw Two, Wild Draw Four
- Draw one ends turn (simplified official-style rule; drawn card cannot be immediately played)
- Winner when a player empties their hand
- Server keeps hands private per player and validates turns/actions

LIMITATIONS / IMPORTANT
- This patch is a functional baseline, but it has not been deployed/tested against your live Railway project. Test with two Telegram accounts before announcing it.
- Telegram Mini App identity is verified using BOT_TOKEN and Telegram initData. Do not remove this verification in public deployment.
- AI opponents are intentionally not enabled in online rooms yet.
- Room state is in memory; rooms reset when Railway restarts/redeploys and multiple replicas will not share rooms. Use one Railway replica for this baseline.
- UNO call is accepted only when the player has one card; automatic penalties for failing to call UNO and stacking house rules are not implemented.
- Do not replace your entire project with this patch. Merge only these files.
