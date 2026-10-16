# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/pixelbattle_engine.py — 🎨 PIXEL BATTLE Engine
#  Territory capture game: claim empty cells adjacent to your own.
#  Paid + Free. 2-6 players. 10x10 grid.
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from database.mongo import db


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
EMPTY = "⬜"

# Player colors (max 6 players)
PLAYER_COLORS = ["🟦", "🟥", "🟩", "🟨", "🟪", "🟧"]

GRID_SIZE = 10            # 10x10 = 100 cells
MIN_PLAYERS = 2
MAX_PLAYERS = 6

LOBBY_SECONDS = 60
TURN_SECONDS  = 20

ENTRY_MIN = 100
ENTRY_MAX = 500_000
GAME_FEE_PERCENT = 0.10
WINNER_XP = 150
LOSER_XP  = 30

STATE_LOBBY     = "LOBBY"
STATE_PLAYING   = "PLAYING"
STATE_FINISHED  = "FINISHED"
STATE_CANCELLED = "CANCELLED"
TERMINAL = (STATE_FINISHED, STATE_CANCELLED)

ACTIVE_GAMES: dict[int, "PixelGame"] = {}
USER_ACTIVE: dict[int, int] = {}


def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════════════════════════
class PixelGame:
    def __init__(self, chat_id: int, host_id: int, host_name: str,
                 host_mention: str, entry_fee: int = 0, is_paid: bool = True):
        self.chat_id      = int(chat_id)
        self.chat_name    = ""
        self.host_id      = int(host_id)
        self.host_name    = host_name
        self.host_mention = host_mention
        self.entry_fee    = int(entry_fee)
        self.is_paid      = bool(is_paid)

        self.players: list[dict] = []   # {user_id, name, mention, color, cell_count, paid}
        self.grid: list[list[str]] = []  # 10x10 grid of cell contents

        self.state       = STATE_LOBBY
        self.turn_index  = 0
        self.turn_count  = 0
        self.pass_count  = 0             # Consecutive passes (for stalemate detection)

        self.winner_id: Optional[int] = None
        self.winner_ids: list[int] = []

        # Track message IDs for cleanup
        self.game_messages: list[int] = []
        self.lobby_message_id: Optional[int] = None
        self.board_message_id: Optional[int] = None

        self.lobby_task: Optional[asyncio.Task] = None
        self.turn_task:  Optional[asyncio.Task] = None

        self.payout_done = False
        self.refund_done = False
        self.gross_pool  = 0
        self.tax_amount  = 0
        self.net_prize   = 0

        self.created_at  = _now()
        self.finished_at: Optional[datetime] = None

    # ── Player helpers ────────────────────────────────────────────────────
    def has_player(self, uid) -> bool:
        return any(p["user_id"] == int(uid) for p in self.players)

    def get_player(self, uid) -> Optional[dict]:
        for p in self.players:
            if p["user_id"] == int(uid):
                return p
        return None

    def add_player(self, uid, name, mention) -> bool:
        if self.has_player(uid) or len(self.players) >= MAX_PLAYERS:
            return False
        color_idx = len(self.players)
        self.players.append({
            "user_id": int(uid),
            "name": name,
            "mention": mention,
            "color": PLAYER_COLORS[color_idx],
            "cell_count": 0,
            "paid": False,
        })
        return True

    def is_full(self) -> bool:  return len(self.players) >= MAX_PLAYERS
    def can_start(self) -> bool: return len(self.players) >= MIN_PLAYERS

    # ── Grid helpers ──────────────────────────────────────────────────────
    def init_grid(self):
        self.grid = [[EMPTY for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]

    def is_empty(self, r: int, c: int) -> bool:
        return 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE and self.grid[r][c] == EMPTY

    def get_player_cells(self, uid: int) -> list[tuple[int, int]]:
        p = self.get_player(uid)
        if not p:
            return []
        color = p["color"]
        cells = []
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if self.grid[r][c] == color:
                    cells.append((r, c))
        return cells

    def get_valid_moves(self, uid: int) -> list[tuple[int, int]]:
        """Return valid (row, col) cells for player.

        First move: any empty cell.
        After that: only cells adjacent to player's own cells.
        """
        p = self.get_player(uid)
        if not p:
            return []

        own_cells = self.get_player_cells(uid)

        # First move → any empty cell
        if not own_cells:
            return [(r, c) for r in range(GRID_SIZE) for c in range(GRID_SIZE)
                    if self.grid[r][c] == EMPTY]

        # Adjacent empty cells
        valid = set()
        for (r, c) in own_cells:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if self.is_empty(nr, nc):
                    valid.add((nr, nc))
        return sorted(valid)

    def claim_cell(self, uid: int, r: int, c: int) -> tuple[bool, str]:
        """Claim a cell for player."""
        p = self.get_player(uid)
        if not p:
            return False, "not_player"
        if self.grid[r][c] != EMPTY:
            return False, "cell_taken"

        # Validate adjacency (except first move)
        own_cells = self.get_player_cells(uid)
        if own_cells:
            adjacent = False
            for (or_, oc) in own_cells:
                if abs(or_ - r) + abs(oc - c) == 1:
                    adjacent = True
                    break
            if not adjacent:
                return False, "not_adjacent"

        self.grid[r][c] = p["color"]
        p["cell_count"] = p.get("cell_count", 0) + 1
        self.turn_count += 1
        return True, "ok"

    def current_player(self) -> Optional[dict]:
        if not self.players:
            return None
        self.turn_index %= len(self.players)
        return self.players[self.turn_index]

    def next_turn(self):
        if not self.players:
            return
        self.turn_index = (self.turn_index + 1) % len(self.players)

    def total_cells_claimed(self) -> int:
        return sum(p["cell_count"] for p in self.players)

    def is_grid_full(self) -> bool:
        return self.total_cells_claimed() >= (GRID_SIZE * GRID_SIZE)

    def get_scores(self) -> dict[int, int]:
        return {p["user_id"]: p["cell_count"] for p in self.players}

    def determine_winner(self) -> Optional[int]:
        """Return winner uid (most cells). Ties broken randomly."""
        if not self.players:
            return None
        max_cells = max(p["cell_count"] for p in self.players)
        top = [p["user_id"] for p in self.players if p["cell_count"] == max_cells]
        return random.choice(top) if top else None

    def check_game_over(self) -> bool:
        """Game over if grid full OR all players stuck (no valid moves)."""
        if self.is_grid_full():
            return True
        # Check if any player has valid moves
        for p in self.players:
            if self.get_valid_moves(p["user_id"]):
                return False
        return True

    def cancel_timers(self):
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for attr in ("lobby_task", "turn_task"):
            t = getattr(self, attr, None)
            if t and not t.done() and t is not current:
                t.cancel()
            setattr(self, attr, None)

    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    def calculate_pool(self) -> tuple[int, int, int]:
        if not self.is_paid or self.entry_fee <= 0:
            return 0, 0, 0
        gross = self.entry_fee * len(self.players)
        tax = int(gross * GAME_FEE_PERCENT)
        net = gross - tax
        return gross, tax, net


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
def get_game(chat_id: int) -> Optional[PixelGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def get_user_game(uid: int) -> Optional[PixelGame]:
    cid = USER_ACTIVE.get(int(uid))
    if cid is None:
        return None
    g = ACTIVE_GAMES.get(int(cid))
    if not g or g.is_terminal():
        USER_ACTIVE.pop(int(uid), None)
        return None
    return g


def create_game(chat_id, host_id, host_name, host_mention,
                entry_fee=0, is_paid=True) -> PixelGame:
    g = PixelGame(chat_id, host_id, host_name, host_mention, entry_fee, is_paid)
    ACTIVE_GAMES[int(chat_id)] = g
    USER_ACTIVE[int(host_id)] = int(chat_id)
    return g


def remove_game(chat_id):
    g = ACTIVE_GAMES.pop(int(chat_id), None)
    if not g:
        return
    for p in g.players:
        if USER_ACTIVE.get(p["user_id"]) == int(chat_id):
            USER_ACTIVE.pop(p["user_id"], None)


# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
def _stats_col():
    return db["pixelbattle_stats"] if db is not None else None


def _games_col():
    return db["pixelbattle_games"] if db is not None else None


async def ensure_stats(user_id: int, name: str = ""):
    col = _stats_col()
    if col is None:
        return
    await col.update_one(
        {"_id": int(user_id)},
        {
            "$set": {"name": name, "updated_at": _now()},
            "$setOnInsert": {
                "_id": int(user_id),
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "total_cells": 0,
                "best_cells": 0,
                "coins_wagered": 0,
                "gross_won": 0,
                "tax_paid": 0,
                "net_coins": 0,
                "win_streak": 0,
                "best_streak": 0,
                "last_played": None,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_result(user_id: int, name: str, *, won: bool,
                        cells: int = 0, wagered: int = 0,
                        gross_won: int = 0, tax_paid: int = 0):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, name)

    inc = {
        "games_played": 1,
        "coins_wagered": int(wagered),
        "total_cells": int(cells),
    }
    if won:
        inc["wins"] = 1
        inc["gross_won"] = int(gross_won)
        inc["tax_paid"] = int(tax_paid)
        inc["net_coins"] = int(gross_won) - int(tax_paid) - int(wagered)
    else:
        inc["losses"] = 1
        inc["net_coins"] = -int(wagered)

    update = {
        "$inc": inc,
        "$set": {"name": name, "updated_at": _now(), "last_played": _now()},
    }

    # best_cells
    doc = await col.find_one({"_id": int(user_id)}, {"best_cells": 1, "win_streak": 1, "best_streak": 1})
    current_best = int((doc or {}).get("best_cells", 0))
    if int(cells) > current_best:
        update["$set"]["best_cells"] = int(cells)

    # streak
    if won:
        cur = int((doc or {}).get("win_streak", 0)) + 1
        best = max(cur, int((doc or {}).get("best_streak", 0)))
        update["$set"]["win_streak"] = cur
        update["$set"]["best_streak"] = best
    else:
        update["$set"]["win_streak"] = 0

    await col.update_one({"_id": int(user_id)}, update)


async def get_stats(user_id: int) -> Optional[dict]:
    col = _stats_col()
    if col is None:
        return None
    return await col.find_one({"_id": int(user_id)})


async def top_players(limit: int = 10):
    col = _stats_col()
    if col is None:
        return []
    return await col.find().sort(
        [("wins", -1), ("net_coins", -1), ("best_cells", -1)]
    ).limit(limit).to_list(length=limit)


async def persist_game(game: PixelGame):
    col = _games_col()
    if col is None:
        return
    try:
        await col.update_one(
            {"_id": int(game.chat_id)},
            {"$set": {
                "chat_id": int(game.chat_id),
                "chat_name": game.chat_name,
                "host_id": int(game.host_id),
                "entry_fee": int(game.entry_fee),
                "is_paid": bool(game.is_paid),
                "players": game.players,
                "grid": game.grid,
                "state": game.state,
                "turn_index": int(game.turn_index),
                "turn_count": int(game.turn_count),
                "winner_id": game.winner_id,
                "winner_ids": list(game.winner_ids),
                "payout_done": bool(game.payout_done),
                "refund_done": bool(game.refund_done),
                "updated_at": _now(),
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[Pixel persist] {type(e).__name__}: {e}", flush=True)


async def remove_persisted_game(chat_id: int):
    col = _games_col()
    if col is None:
        return
    try:
        await col.delete_one({"_id": int(chat_id)})
    except Exception:
        pass


async def recover_active_games() -> int:
    col = _games_col()
    if col is None:
        return 0
    from core.database import add_coins
    count = 0
    async for doc in col.find({"state": {"$in": [STATE_LOBBY, STATE_PLAYING]}}):
        try:
            entry = int(doc.get("entry_fee", 0))
            is_paid = bool(doc.get("is_paid", True))
            if is_paid and entry > 0:
                for p in doc.get("players", []):
                    if p.get("paid"):
                        try:
                            await add_coins(int(p["user_id"]), entry)
                        except Exception:
                            pass
            await col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"state": STATE_CANCELLED, "refund_done": True,
                          "cancelled_on_boot": True, "updated_at": _now()}},
            )
            count += 1
        except Exception as e:
            print(f"[Pixel recover] {type(e).__name__}: {e}", flush=True)
    return count
