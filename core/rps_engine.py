# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/rps_engine.py — 🪨📄✂️ RPS Arena Engine
#  Multiplayer elimination + financial state machine + DB persistence
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
import secrets
from datetime import datetime, timezone
from typing import Optional

from database.mongo import db


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
MOVE_ROCK = "rock"
MOVE_PAPER = "paper"
MOVE_SCISSORS = "scissors"
VALID_MOVES = (MOVE_ROCK, MOVE_PAPER, MOVE_SCISSORS)

MOVE_EMOJI = {MOVE_ROCK: "🪨", MOVE_PAPER: "📄", MOVE_SCISSORS: "✂️"}
MOVE_LABEL = {MOVE_ROCK: "Rock", MOVE_PAPER: "Paper", MOVE_SCISSORS: "Scissors"}

# move → move it beats
BEATS = {
    MOVE_ROCK:     MOVE_SCISSORS,
    MOVE_SCISSORS: MOVE_PAPER,
    MOVE_PAPER:    MOVE_ROCK,
}

# ─── Economy / game defaults ───
ENTRY_MIN = 100
ENTRY_MAX = 500_000
DEFAULT_MIN_PLAYERS = 2
DEFAULT_MAX_PLAYERS = 5
LOBBY_SECONDS = 20
ROUND_SECONDS = 15
GAME_FEE_PERCENT = 0.10
WINNER_XP = 100
LOSER_XP = 10

# ─── Timeout policy ───
TIMEOUT_RANDOM = "random"
TIMEOUT_ELIMINATE = "eliminate"
DEFAULT_TIMEOUT_POLICY = TIMEOUT_RANDOM

# ─── Financial state machine ───
STATE_CREATED     = "CREATED"
STATE_COLLECTING  = "COLLECTING_ENTRIES"
STATE_ACTIVE      = "ACTIVE"
STATE_SETTLING    = "SETTLING"
STATE_FINISHED    = "FINISHED"
STATE_CANCELLED   = "CANCELLED"

TERMINAL_STATES = (STATE_FINISHED, STATE_CANCELLED)

# ─── Registries ───
ACTIVE_GAMES: dict[int, "RPSGame"] = {}
USER_ACTIVE: dict[int, int] = {}


def _now():
    return datetime.now(timezone.utc)


def _new_round_id() -> str:
    return secrets.token_hex(4)   # 8-char hex


# ══════════════════════════════════════════════════════════════════════════════
#  CORE RPS LOGIC  (pure, unit-testable)
# ══════════════════════════════════════════════════════════════════════════════
def resolve_round(moves: dict[int, str]) -> tuple[set[int], set[int], str]:
    """Resolve a round of multiplayer RPS.

    Returns:
        (survivors: set[int], eliminated: set[int], reason: str)

    Reasons:
        "empty"           — no moves submitted
        "draw_single"     — only 1 move type present (everyone same) → draw
        "draw_all_three"  — all 3 move types present → draw
        "played"          — exactly 2 move types → normal RPS elimination
    """
    if not moves:
        return set(), set(), "empty"

    unique = set(moves.values())

    # 1 move type = everyone same → draw
    if len(unique) == 1:
        return set(moves.keys()), set(), "draw_single"

    # 3 move types present → draw
    if len(unique) == 3:
        return set(moves.keys()), set(), "draw_all_three"

    # Exactly 2 move types → apply RPS rule
    a, b = list(unique)
    if BEATS[a] == b:
        winner_move = a
    elif BEATS[b] == a:
        winner_move = b
    else:
        # Should never happen
        return set(moves.keys()), set(), "draw_single"

    survivors  = {uid for uid, mv in moves.items() if mv == winner_move}
    eliminated = {uid for uid, mv in moves.items() if mv != winner_move}
    return survivors, eliminated, "played"


# ══════════════════════════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════════════════════════
class RPSGame:
    def __init__(self, chat_id: int, host_id: int, host_name: str,
                 host_mention: str, entry_fee: int,
                 min_players: int = DEFAULT_MIN_PLAYERS,
                 max_players: int = DEFAULT_MAX_PLAYERS):
        self.chat_id      = int(chat_id)
        self.host_id      = int(host_id)
        self.host_name    = host_name
        self.host_mention = host_mention
        self.entry_fee    = int(entry_fee)
        self.min_players  = int(min_players)
        self.max_players  = int(max_players)
        self.currency     = "coins"

        self.players:    list[dict] = []
        self.eliminated: list[dict] = []

        self.state       = STATE_CREATED
        self.round_no    = 0
        self.round_id:   Optional[str] = None
        self.round_moves: dict[int, str] = {}
        self.round_auto:  set[int] = set()   # user_ids auto-filled by timeout

        self.created_at  = _now()
        self.finished_at: Optional[datetime] = None
        self.winner_id:  Optional[int] = None

        self.lobby_task: Optional[asyncio.Task] = None
        self.round_task: Optional[asyncio.Task] = None

        self.lobby_message_id: Optional[int] = None
        self.round_message_id: Optional[int] = None

        # Finance tracking
        self.payout_done = False
        self.refund_done = False
        self.gross_pool  = 0
        self.tax_amount  = 0
        self.net_prize   = 0

    # ── player helpers ────────────────────────────────────────────────────
    def has_player(self, uid) -> bool:
        return any(p["user_id"] == int(uid) for p in self.players)

    def get_player(self, uid) -> Optional[dict]:
        for p in self.players:
            if p["user_id"] == int(uid):
                return p
        return None

    def add_player(self, uid, name, mention) -> bool:
        if self.has_player(uid) or len(self.players) >= self.max_players:
            return False
        self.players.append({
            "user_id": int(uid), "name": name, "mention": mention, "paid": False,
        })
        return True

    def is_full(self) -> bool:  return len(self.players) >= self.max_players
    def can_start(self) -> bool: return len(self.players) >= self.min_players
    def active_count(self) -> int: return len(self.players)

    def calculate_pool(self) -> tuple[int, int, int]:
        gross = self.entry_fee * len(self.players)
        tax   = int(gross * GAME_FEE_PERCENT)
        net   = gross - tax
        return gross, tax, net

    # ── round helpers ─────────────────────────────────────────────────────
    def start_new_round(self) -> str:
        self.round_no += 1
        self.round_id = _new_round_id()
        self.round_moves.clear()
        self.round_auto.clear()
        return self.round_id

    def submit_move(self, uid, move) -> tuple[bool, str]:
        uid = int(uid)
        if self.state != STATE_ACTIVE:
            return False, "not_active"
        if not self.has_player(uid):
            return False, "not_player"
        if move not in VALID_MOVES:
            return False, "invalid_move"
        if uid in self.round_moves:
            return False, "already_submitted"
        self.round_moves[uid] = move
        return True, "ok"

    def all_submitted(self) -> bool:
        return all(p["user_id"] in self.round_moves for p in self.players)

    def apply_timeout_policy(self, policy: str = DEFAULT_TIMEOUT_POLICY) -> list[int]:
        """Fill in moves for players who didn't submit. Returns eliminated user ids."""
        missing = [p for p in self.players if p["user_id"] not in self.round_moves]
        if not missing:
            return []
        if policy == TIMEOUT_ELIMINATE:
            uid_set = {p["user_id"] for p in missing}
            self.eliminate(uid_set)
            return list(uid_set)
        # random
        for p in missing:
            self.round_moves[p["user_id"]] = random.choice(VALID_MOVES)
            self.round_auto.add(p["user_id"])
        return []

    def eliminate(self, uids: set[int]):
        uids = {int(u) for u in uids}
        keep, gone = [], []
        for p in self.players:
            (gone if p["user_id"] in uids else keep).append(p)
        self.players = keep
        self.eliminated.extend(gone)

    def resolve_current_round(self) -> tuple[set[int], set[int], str]:
        return resolve_round(dict(self.round_moves))

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def cancel_timers(self):
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for attr in ("lobby_task", "round_task"):
            t = getattr(self, attr, None)
            if t and not t.done() and t is not current:
                t.cancel()
            setattr(self, attr, None)


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
def get_game(chat_id: int) -> Optional[RPSGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def get_user_game(uid: int) -> Optional[RPSGame]:
    cid = USER_ACTIVE.get(int(uid))
    if cid is None:
        return None
    g = ACTIVE_GAMES.get(int(cid))
    if not g or g.is_terminal():
        USER_ACTIVE.pop(int(uid), None)
        return None
    return g


def create_game(chat_id, host_id, host_name, host_mention, entry_fee,
                min_players=DEFAULT_MIN_PLAYERS,
                max_players=DEFAULT_MAX_PLAYERS) -> RPSGame:
    g = RPSGame(chat_id, host_id, host_name, host_mention, entry_fee,
                min_players, max_players)
    ACTIVE_GAMES[int(chat_id)] = g
    USER_ACTIVE[int(host_id)] = int(chat_id)
    return g


def remove_game(chat_id):
    g = ACTIVE_GAMES.pop(int(chat_id), None)
    if not g:
        return
    for p in g.players + g.eliminated:
        if USER_ACTIVE.get(p["user_id"]) == int(chat_id):
            USER_ACTIVE.pop(p["user_id"], None)


# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
def _stats_col():
    return db["rps_stats"] if db is not None else None


def _games_col():
    return db["rps_games"] if db is not None else None


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
                "draws": 0,
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


async def record_result(user_id: int, name: str, *,
                        won: bool = False, drew: bool = False,
                        wagered: int = 0, gross_won: int = 0,
                        tax_paid: int = 0):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, name)

    net = int(gross_won) - int(wagered)

    inc = {
        "games_played": 1,
        "coins_wagered": int(wagered),
    }
    if won:
        inc["wins"] = 1
        inc["gross_won"] = int(gross_won)
        inc["tax_paid"] = int(tax_paid)
        inc["net_coins"] = int(gross_won) - int(tax_paid) - int(wagered)
    elif drew:
        inc["draws"] = 1
        inc["net_coins"] = -int(wagered)
    else:
        inc["losses"] = 1
        inc["net_coins"] = -int(wagered)

    update = {
        "$inc": inc,
        "$set": {"name": name, "updated_at": _now(), "last_played": _now()},
    }

    # Streak handling
    if won:
        doc = await col.find_one({"_id": int(user_id)}, {"win_streak": 1, "best_streak": 1})
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
        [("wins", -1), ("net_coins", -1)]
    ).limit(limit).to_list(length=limit)


async def persist_game(game: RPSGame):
    col = _games_col()
    if col is None:
        return
    try:
        await col.update_one(
            {"_id": int(game.chat_id)},
            {"$set": {
                "chat_id": int(game.chat_id),
                "host_id": int(game.host_id),
                "host_name": game.host_name,
                "entry_fee": int(game.entry_fee),
                "players": game.players,
                "eliminated": game.eliminated,
                "state": game.state,
                "round_no": int(game.round_no),
                "round_id": game.round_id,
                "round_moves": {str(k): v for k, v in game.round_moves.items()},
                "winner_id": game.winner_id,
                "gross_pool": int(game.gross_pool),
                "tax_amount": int(game.tax_amount),
                "net_prize": int(game.net_prize),
                "payout_done": bool(game.payout_done),
                "refund_done": bool(game.refund_done),
                "created_at": game.created_at,
                "updated_at": _now(),
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[RPS persist] {type(e).__name__}: {e}", flush=True)


async def remove_persisted_game(chat_id: int):
    col = _games_col()
    if col is None:
        return
    try:
        await col.delete_one({"_id": int(chat_id)})
    except Exception:
        pass


async def recover_active_games() -> int:
    """On boot: mark in-flight games as CANCELLED and refund players.

    The engine cannot safely resume timers, so it commits a full refund.
    """
    col = _games_col()
    if col is None:
        return 0

    from core.database import add_coins

    count = 0
    async for doc in col.find({"state": {"$in": [STATE_COLLECTING, STATE_ACTIVE, STATE_SETTLING]}}):
        try:
            entry = int(doc.get("entry_fee", 0))
            for p in doc.get("players", []):
                if entry > 0 and p.get("paid"):
                    try:
                        await add_coins(int(p["user_id"]), entry)
                    except Exception as e:
                        print(f"[RPS recover refund] {type(e).__name__}: {e}", flush=True)
            await col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"state": STATE_CANCELLED, "refund_done": True,
                          "cancelled_on_boot": True, "updated_at": _now()}},
            )
            count += 1
        except Exception as e:
            print(f"[RPS recover outer] {type(e).__name__}: {e}", flush=True)
    return count
