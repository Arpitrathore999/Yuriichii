# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/ttt_engine.py — 🎮 TIC TAC TOE ENGINE
#  Uses Elara's EXISTING economy/XP/streak systems.
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
import string
from datetime import datetime, timezone
from typing import Optional

from database.mongo import db


# ─── Constants ─────────────────────────────────────────────────────────────────
ENTRY_MIN = 100
ENTRY_MAX = 500_000
TURN_SECONDS = 60
LOBBY_SECONDS = 120               # ✅ 2 minutes join window
GAME_FEE_PERCENT = 0.10
WINNER_XP = 20
DRAW_XP = 0
TOTAL_CELLS = 9

P1_SYMBOL = "❌"
P2_SYMBOL = "⭕"
EMPTY = "⬜"

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),      # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),      # cols
    (0, 4, 8), (2, 4, 6),                 # diagonals
]

# In-memory active games: {game_id: TTTGame}
ACTIVE_GAMES: dict[str, "TTTGame"] = {}
# User's active game index: {user_id: game_id}
USER_ACTIVE: dict[int, str] = {}


def _now():
    return datetime.now(timezone.utc)


def _new_game_id() -> str:
    """Short unique game ID."""
    part = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"TTT{part}"


# ─── TTT Game Class ────────────────────────────────────────────────────────────
class TTTGame:
    def __init__(self, game_id: str, chat_id: int, host_id: int, host_name: str,
                 host_mention: str, bet: int, currency: str):
        self.game_id = game_id
        self.chat_id = int(chat_id)
        self.host_id = int(host_id)
        self.host_name = host_name
        self.host_mention = host_mention
        self.bet = int(bet)
        self.currency = (currency or "coins").lower()

        self.opponent_id: Optional[int] = None
        self.opponent_name: Optional[str] = None
        self.opponent_mention: Optional[str] = None

        self.board: list[str] = [EMPTY] * TOTAL_CELLS
        self.status: str = "WAITING"           # WAITING | ACTIVE | FINISHED | DRAW | CANCELLED
        self.current_turn: Optional[int] = None
        self.turn_started_at: Optional[datetime] = None
        self.winner_id: Optional[int] = None
        self.created_at = _now()
        self.turn_task: Optional[asyncio.Task] = None
        self.lobby_task: Optional[asyncio.Task] = None      # ✅ NEW — join timeout

        # Message tracking
        self.invite_message_id: Optional[int] = None
        self.board_message_id: Optional[int] = None

        # Guard flags (prevent double-payout, double-XP)
        self.payout_done = False
        self.stats_recorded = False

    # ── Player helpers ──
    def has_host(self, user_id: int) -> bool:
        return int(user_id) == self.host_id

    def has_opponent(self) -> bool:
        return self.opponent_id is not None

    def is_player(self, user_id: int) -> bool:
        uid = int(user_id)
        return uid == self.host_id or uid == self.opponent_id

    def player_symbol(self, user_id: int) -> Optional[str]:
        uid = int(user_id)
        if uid == self.host_id:
            return P1_SYMBOL
        if uid == self.opponent_id:
            return P2_SYMBOL
        return None

    def opponent_of(self, user_id: int) -> Optional[int]:
        uid = int(user_id)
        if uid == self.host_id:
            return self.opponent_id
        if uid == self.opponent_id:
            return self.host_id
        return None

    # ── Board helpers ──
    def is_empty(self, pos: int) -> bool:
        return 0 <= pos < TOTAL_CELLS and self.board[pos] == EMPTY

    def can_accept_move(self) -> bool:
        return self.status == "ACTIVE"

    def apply_move(self, user_id: int, pos: int) -> tuple[bool, str]:
        if not self.can_accept_move():
            return False, "game_not_active"
        if not self.is_player(user_id):
            return False, "not_player"
        if int(user_id) != int(self.current_turn):
            return False, "not_your_turn"
        if not self.is_empty(pos):
            return False, "cell_taken"

        sym = self.player_symbol(user_id)
        self.board[pos] = sym
        return True, "ok"

    def check_winner(self) -> Optional[str]:
        """Return '❌', '⭕', or None."""
        for a, b, c in WIN_LINES:
            if self.board[a] != EMPTY and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return None

    def is_draw(self) -> bool:
        return all(cell != EMPTY for cell in self.board) and self.check_winner() is None

    def is_finished(self) -> bool:
        return self.status in ("FINISHED", "DRAW", "CANCELLED")

    # ── Winner resolution ──
    def resolve_winner_id(self, symbol: str) -> Optional[int]:
        if symbol == P1_SYMBOL:
            return self.host_id
        if symbol == P2_SYMBOL:
            return self.opponent_id
        return None

    # ── Turn management ──
    def switch_turn(self):
        if self.opponent_id is None:
            self.current_turn = self.host_id
            return
        self.current_turn = self.opponent_of(self.current_turn) or self.host_id
        self.turn_started_at = _now()

    def cancel_timer(self):
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
        self.turn_task = None

    def cancel_lobby_timer(self):
        """Cancel the join-window timer (called when opponent joins)."""
        if self.lobby_task and not self.lobby_task.done():
            self.lobby_task.cancel()
        self.lobby_task = None


# ─── Registry ─────────────────────────────────────────────────────────────────
def get_game(game_id: str) -> Optional[TTTGame]:
    return ACTIVE_GAMES.get(game_id)


def get_user_active_game(user_id: int) -> Optional[TTTGame]:
    gid = USER_ACTIVE.get(int(user_id))
    if not gid:
        return None
    game = ACTIVE_GAMES.get(gid)
    if not game or game.is_finished():
        USER_ACTIVE.pop(int(user_id), None)
        return None
    return game


def register_game(game: TTTGame):
    ACTIVE_GAMES[game.game_id] = game
    USER_ACTIVE[game.host_id] = game.game_id
    if game.opponent_id:
        USER_ACTIVE[game.opponent_id] = game.game_id


def unregister_game(game_id: str):
    game = ACTIVE_GAMES.pop(game_id, None)
    if not game:
        return
    if USER_ACTIVE.get(game.host_id) == game_id:
        USER_ACTIVE.pop(game.host_id, None)
    if game.opponent_id and USER_ACTIVE.get(game.opponent_id) == game_id:
        USER_ACTIVE.pop(game.opponent_id, None)


def create_game(chat_id: int, host_id: int, host_name: str, host_mention: str,
                bet: int, currency: str) -> TTTGame:
    gid = _new_game_id()
    while gid in ACTIVE_GAMES:
        gid = _new_game_id()
    game = TTTGame(gid, chat_id, host_id, host_name, host_mention, bet, currency)
    register_game(game)
    return game


# ─── DB: TTT Stats ────────────────────────────────────────────────────────────
def _stats_col():
    return db["ttt_stats"] if db is not None else None


def _games_col():
    return db["ttt_games"] if db is not None else None


async def ensure_ttt_stats(user_id: int, name: str):
    col = _stats_col()
    if col is None:
        return
    await col.update_one(
        {"_id": int(user_id)},
        {
            "$set": {"name": name, "updated_at": _now()},
            "$setOnInsert": {
                "_id": int(user_id),
                "ttt_games": 0,
                "ttt_wins": 0,
                "ttt_losses": 0,
                "ttt_draws": 0,
                "ttt_streak": 0,
                "ttt_best_streak": 0,
                "ttt_total_coins_won": 0,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_ttt_result(
    user_id: int,
    name: str,
    won: bool,
    draw: bool = False,
    coins_won: int = 0,
):
    col = _stats_col()
    if col is None:
        return
    await ensure_ttt_stats(user_id, name)

    inc = {"ttt_games": 1}
    if draw:
        inc["ttt_draws"] = 1
    elif won:
        inc["ttt_wins"] = 1
        inc["ttt_total_coins_won"] = int(coins_won)
    else:
        inc["ttt_losses"] = 1

    if won and not draw:
        doc = await col.find_one({"_id": int(user_id)}, {"ttt_streak": 1, "ttt_best_streak": 1})
        current = int(doc.get("ttt_streak", 0)) + 1 if doc else 1
        best = max(current, int(doc.get("ttt_best_streak", 0)) if doc else 0)
        await col.update_one(
            {"_id": int(user_id)},
            {
                "$inc": inc,
                "$set": {
                    "ttt_streak": current,
                    "ttt_best_streak": best,
                    "updated_at": _now(),
                },
            },
        )
    else:
        # Loss or draw → reset current streak
        await col.update_one(
            {"_id": int(user_id)},
            {
                "$inc": inc,
                "$set": {
                    "ttt_streak": 0,
                    "updated_at": _now(),
                },
            },
        )


async def get_ttt_stats(user_id: int) -> Optional[dict]:
    col = _stats_col()
    if col is None:
        return None
    return await col.find_one({"_id": int(user_id)})


async def top_ttt_players(limit: int = 10):
    col = _stats_col()
    if col is None:
        return []
    return await col.find().sort(
        [("ttt_wins", -1), ("ttt_best_streak", -1)]
    ).limit(limit).to_list(length=limit)


# ─── Persist game state (for restart safety) ──────────────────────────────────
async def persist_game(game: TTTGame):
    col = _games_col()
    if col is None:
        return
    await col.update_one(
        {"_id": game.game_id},
        {
            "$set": {
                "game_id": game.game_id,
                "chat_id": game.chat_id,
                "host_id": game.host_id,
                "host_name": game.host_name,
                "host_mention": game.host_mention,
                "opponent_id": game.opponent_id,
                "opponent_name": game.opponent_name,
                "opponent_mention": game.opponent_mention,
                "board": game.board,
                "bet": game.bet,
                "currency": game.currency,
                "status": game.status,
                "current_turn": game.current_turn,
                "turn_started_at": game.turn_started_at,
                "winner_id": game.winner_id,
                "created_at": game.created_at,
                "updated_at": _now(),
            }
        },
        upsert=True,
    )


async def mark_game_finished(game_id: str, final_status: str):
    col = _games_col()
    if col is None:
        return
    await col.update_one(
        {"_id": game_id},
        {"$set": {"status": final_status, "updated_at": _now()}},
    )


async def refund_interrupted_games() -> int:
    """On boot: refund games that were ACTIVE/WAITING when bot crashed.
    Prevents locked funds. Returns count of refunded games.
    """
    col = _games_col()
    if col is None:
        return 0
    from core.database import add_coins
    count = 0
    async for doc in col.find({"status": {"$in": ["WAITING", "ACTIVE"]}}):
        try:
            for pid_key in ("host_id", "opponent_id"):
                pid = doc.get(pid_key)
                if not pid:
                    continue
                bet = int(doc.get("bet", 0))
                if bet > 0:
                    await add_coins(int(pid), bet)
            await col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "CANCELLED", "refunded_on_boot": True}},
            )
            count += 1
        except Exception as e:
            print(f"[TTT BOOT REFUND] {type(e).__name__}: {e}", flush=True)
    return count
