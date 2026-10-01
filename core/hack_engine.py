# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/hack_engine.py — 🛸 ELARA HACK GAME engine
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from database.mongo import db


# ─── Constants ─────────────────────────────────────────────────────────────────
ENTRY_MIN = 100
ENTRY_MAX = 500_000
VALID_LENGTHS = (3, 4, 5, 6)
TURN_SECONDS = 40
GAME_FEE_PERCENT = 0.10
WINNER_XP = 100
LOSER_XP = 10
MAX_MISSES = 2

# games[chat_id] = HackGame
ACTIVE_GAMES: dict[int, "HackGame"] = {}


def _now():
    return datetime.now(timezone.utc)


# ─── Mastermind scoring (Hacks / Glitches) ─────────────────────────────────────
def score_guess(secret: str, guess: str) -> tuple[int, int]:
    if not secret or not guess or len(secret) != len(guess):
        return 0, 0

    n = len(secret)
    secret_used = [False] * n
    guess_used = [False] * n

    # Step 1: exact positions
    hacks = 0
    for i in range(n):
        if guess[i] == secret[i]:
            hacks += 1
            secret_used[i] = True
            guess_used[i] = True

    # Step 2: remaining digit matches
    glitches = 0
    for i in range(n):
        if guess_used[i]:
            continue
        for j in range(n):
            if secret_used[j]:
                continue
            if guess[i] == secret[j]:
                glitches += 1
                secret_used[j] = True
                guess_used[i] = True
                break

    return hacks, glitches


# ─── Secret Code Generation ────────────────────────────────────────────────────
def generate_secret(length: int) -> str:
    """Generate unique-digit, non-zero secret code.
    - Digits from 1-9 (no zero)
    - No repeated digits
    """
    length = int(length)
    available = [str(d) for d in range(1, 10)]   # 1-9
    if length > len(available):
        length = len(available)
    return "".join(random.sample(available, length))


# ─── Guess Validation ──────────────────────────────────────────────────────────
def is_valid_guess(guess: str, length: int) -> tuple[bool, str]:
    """Validate user's guess.

    Rules:
    - Must be a number (all digits)
    - Length must match code_length
    - No zero (0)
    - No repeated digits

    Returns:
        (is_valid: bool, reason: str)
        reason is one of: "ok", "not_number", "wrong_length", "has_zero", "repeated"
    """
    if not guess or not guess.isdigit():
        return False, "not_number"
    if len(guess) != int(length):
        return False, "wrong_length"
    if "0" in guess:
        return False, "has_zero"
    if len(set(guess)) != len(guess):
        return False, "repeated"
    return True, "ok"


def max_guesses_for(length: int) -> int:
    return int(length) * 10


# ─── HackGame class ────────────────────────────────────────────────────────────
class HackGame:
    def __init__(self, chat_id: int, host_id: int, host_name: str, host_mention: str,
                 entry_amount: int, currency: str, code_length: int):
        self.chat_id = int(chat_id)
        self.host_id = int(host_id)
        self.host_name = host_name
        self.host_mention = host_mention
        self.entry_amount = int(entry_amount)
        self.currency = (currency or "coins").lower()
        self.code_length = int(code_length)

        self.players: list[dict] = []
        self.kicked: list[dict] = []
        self.state = "lobby"                     # lobby | running | finished
        self.secret_code: Optional[str] = None
        self.max_guesses = max_guesses_for(self.code_length)
        self.remaining_guesses = self.max_guesses
        self.turn_index = 0
        self.turn_task: Optional[asyncio.Task] = None
        self.lobby_task: Optional[asyncio.Task] = None
        self.created_at = _now()
        self.winner_id: Optional[int] = None
        self.payout_done = False
        self.used_guesses: set[str] = set()
        self.game_messages: list[int] = []
        self.pinned_msg_id: Optional[int] = None

    def has_player(self, user_id: int) -> bool:
        return any(p["user_id"] == int(user_id) for p in self.players)

    def get_player(self, user_id: int) -> Optional[dict]:
        for p in self.players:
            if p["user_id"] == int(user_id):
                return p
        return None

    def add_player(self, user_id: int, name: str, mention: str) -> bool:
        if self.has_player(user_id):
            return False
        self.players.append({
            "user_id": int(user_id),
            "name": name,
            "mention": mention,
            "guesses_used": 0,
            "misses": 0,
        })
        return True

    def kick_player(self, user_id: int) -> Optional[dict]:
        """Remove player from active list, add to kicked. Fee stays in pot."""
        p = self.get_player(user_id)
        if not p:
            return None
        self.players.remove(p)
        self.kicked.append(p)
        if self.players:
            self.turn_index %= len(self.players)
        else:
            self.turn_index = 0
        return p

    def current_player(self) -> Optional[dict]:
        if not self.players:
            return None
        self.turn_index %= len(self.players)
        return self.players[self.turn_index]

    def next_turn(self):
        if not self.players:
            return
        self.turn_index = (self.turn_index + 1) % len(self.players)

    def prize_pool(self) -> int:
        total_players = len(self.players) + len(self.kicked)
        return self.entry_amount * total_players

    def is_finished(self) -> bool:
        return self.state == "finished"


# ─── Registry ─────────────────────────────────────────────────────────────────
def get_game(chat_id: int) -> Optional[HackGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def create_game(chat_id: int, host_id: int, host_name: str, host_mention: str,
                entry_amount: int, currency: str, code_length: int) -> HackGame:
    existing = ACTIVE_GAMES.get(int(chat_id))
    if existing and existing.is_finished():
        ACTIVE_GAMES.pop(int(chat_id), None)

    game = HackGame(chat_id, host_id, host_name, host_mention,
                    entry_amount, currency, code_length)
    ACTIVE_GAMES[int(chat_id)] = game
    return game


def remove_game(chat_id: int):
    ACTIVE_GAMES.pop(int(chat_id), None)


# ─── DB stats ─────────────────────────────────────────────────────────────────
def _lb_col():
    return db["hack_game_stats"] if db is not None else None


async def ensure_stats(user_id: int, name: str):
    col = _lb_col()
    if col is None:
        return
    await col.update_one(
        {"_id": int(user_id)},
        {
            "$set": {"name": name, "updated_at": _now()},
            "$setOnInsert": {
                "_id": int(user_id),
                "played": 0,
                "won": 0,
                "streak": 0,
                "best_streak": 0,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_result(user_id: int, name: str, won: bool):
    col = _lb_col()
    if col is None:
        return
    await ensure_stats(user_id, name)
    inc = {"played": 1}
    if won:
        inc["won"] = 1
        doc = await col.find_one({"_id": int(user_id)}, {"streak": 1, "best_streak": 1})
        current = int(doc.get("streak", 0)) + 1 if doc else 1
        best = max(current, int(doc.get("best_streak", 0)) if doc else 0)
        await col.update_one(
            {"_id": int(user_id)},
            {"$inc": inc, "$set": {"streak": current, "best_streak": best, "updated_at": _now()}},
        )
    else:
        await col.update_one(
            {"_id": int(user_id)},
            {"$inc": inc, "$set": {"streak": 0, "updated_at": _now()}},
        )


async def top_hackers(limit: int = 10):
    col = _lb_col()
    if col is None:
        return []
    return await col.find().sort([("won", -1), ("streak", -1)]).limit(limit).to_list(length=limit)