# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/shadow_engine.py — 🎭 Shadow Syndicate Game Engine
#  Raja-Mantri-Chor-Sipahi modern version
#  4 players: Monarch, Strategist, Sentinel, Phantom
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
ROLE_MONARCH     = "monarch"
ROLE_STRATEGIST  = "strategist"
ROLE_SENTINEL    = "sentinel"
ROLE_PHANTOM     = "phantom"

ROLE_EMOJI = {
    ROLE_MONARCH:    "👑",
    ROLE_STRATEGIST: "🧠",
    ROLE_SENTINEL:   "🛡️",
    ROLE_PHANTOM:    "🃏",
}
ROLE_LABEL = {
    ROLE_MONARCH:    "THE MONARCH",
    ROLE_STRATEGIST: "THE STRATEGIST",
    ROLE_SENTINEL:   "THE SENTINEL",
    ROLE_PHANTOM:    "THE PHANTOM",
}

# Rewards
REWARD_MONARCH_ALWAYS    = 1000
REWARD_STRATEGIST_CORRECT = 800
REWARD_STRATEGIST_WRONG   = 0
REWARD_SENTINEL_ALWAYS    = 500
REWARD_PHANTOM_CORRECT    = 0     # Phantom caught
REWARD_PHANTOM_WRONG      = 800   # Phantom escaped

STATE_LOBBY      = "LOBBY"
STATE_INTRO      = "INTRO"
STATE_ASSIGNED   = "ASSIGNED"
STATE_GUESSING   = "GUESSING"
STATE_REVEALING  = "REVEALING"
STATE_FINISHED   = "FINISHED"
STATE_CANCELLED  = "CANCELLED"
TERMINAL = (STATE_FINISHED, STATE_CANCELLED)

MIN_PLAYERS = 4
MAX_PLAYERS = 4

LOBBY_SECONDS = 60
GUESS_SECONDS = 30

# Timeout penalty (counts as wrong guess)
TIMEOUT_COUNTS_AS_WRONG = True

ACTIVE_GAMES: dict[int, "ShadowGame"] = {}
USER_ACTIVE: dict[int, int] = {}


def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════════════════════════
class ShadowGame:
    def __init__(self, chat_id: int, host_id: int, host_name: str, host_mention: str):
        self.chat_id      = int(chat_id)
        self.chat_name    = ""
        self.host_id      = int(host_id)
        self.host_name    = host_name
        self.host_mention = host_mention

        self.players: list[dict] = []   # {user_id, name, mention, role}
        self.state      = STATE_LOBBY
        self.round_id   = random.randint(100000, 999999)

        # Guessing
        self.strategist_id: Optional[int] = None
        self.monarch_id:    Optional[int] = None
        self.sentinel_id:   Optional[int] = None
        self.phantom_id:    Optional[int] = None
        self.suspects: list[int] = []  # [sentinel_id, phantom_id] in random order
        self.guess_result: Optional[str] = None  # "correct" | "wrong" | "timeout"
        self.guessed_id: Optional[int] = None

        # Rewards tracking
        self.rewards: dict[int, int] = {}
        self.payout_done = False

        # Message tracking
        self.game_messages: list[int] = []
        self.lobby_message_id: Optional[int] = None
        self.guess_message_id: Optional[int] = None

        self.lobby_task: Optional[asyncio.Task] = None
        self.guess_task: Optional[asyncio.Task] = None

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
        self.players.append({
            "user_id": int(uid),
            "name": name,
            "mention": mention,
            "role": None,
        })
        return True

    def remove_player(self, uid) -> bool:
        p = self.get_player(uid)
        if not p:
            return False
        self.players.remove(p)
        return True

    def is_full(self) -> bool:  return len(self.players) >= MAX_PLAYERS
    def can_start(self) -> bool: return len(self.players) == MAX_PLAYERS

    # ── Role assignment ───────────────────────────────────────────────────
    def assign_roles(self):
        uids = [p["user_id"] for p in self.players]
        random.shuffle(uids)

        role_map = {
            uids[0]: ROLE_MONARCH,
            uids[1]: ROLE_STRATEGIST,
            uids[2]: ROLE_SENTINEL,
            uids[3]: ROLE_PHANTOM,
        }

        for p in self.players:
            p["role"] = role_map[p["user_id"]]

        self.monarch_id    = uids[0]
        self.strategist_id = uids[1]
        self.sentinel_id   = uids[2]
        self.phantom_id    = uids[3]

        # Suspects for guessing (Sentinel + Phantom, shuffled)
        self.suspects = [self.sentinel_id, self.phantom_id]
        random.shuffle(self.suspects)

    # ── Guess handling ────────────────────────────────────────────────────
    def submit_guess(self, caller_uid: int, target_uid: int) -> tuple[bool, str]:
        if self.state != STATE_GUESSING:
            return False, "Not in guessing phase."
        if int(caller_uid) != int(self.strategist_id):
            return False, "Only the Strategist can accuse."
        if target_uid not in self.suspects:
            return False, "Invalid target."

        self.guessed_id = int(target_uid)
        if int(target_uid) == int(self.phantom_id):
            self.guess_result = "correct"
        else:
            self.guess_result = "wrong"
        return True, self.guess_result

    def handle_timeout(self) -> None:
        """Timeout = wrong guess."""
        self.guessed_id = None
        self.guess_result = "wrong"

    def calculate_rewards(self) -> dict[int, int]:
        """Compute rewards based on result."""
        rewards = {}

        # Monarch always
        rewards[self.monarch_id] = REWARD_MONARCH_ALWAYS

        # Strategist
        if self.guess_result == "correct":
            rewards[self.strategist_id] = REWARD_STRATEGIST_CORRECT
        else:
            rewards[self.strategist_id] = REWARD_STRATEGIST_WRONG

        # Sentinel always
        rewards[self.sentinel_id] = REWARD_SENTINEL_ALWAYS

        # Phantom
        if self.guess_result == "correct":
            rewards[self.phantom_id] = REWARD_PHANTOM_CORRECT
        else:
            rewards[self.phantom_id] = REWARD_PHANTOM_WRONG

        self.rewards = rewards
        return rewards

    def cancel_timers(self):
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for attr in ("lobby_task", "guess_task"):
            t = getattr(self, attr, None)
            if t and not t.done() and t is not current:
                t.cancel()
            setattr(self, attr, None)

    def is_terminal(self) -> bool:
        return self.state in TERMINAL


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
def get_game(chat_id: int) -> Optional[ShadowGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def get_user_game(uid: int) -> Optional[ShadowGame]:
    cid = USER_ACTIVE.get(int(uid))
    if cid is None:
        return None
    g = ACTIVE_GAMES.get(int(cid))
    if not g or g.is_terminal():
        USER_ACTIVE.pop(int(uid), None)
        return None
    return g


def create_game(chat_id, host_id, host_name, host_mention) -> ShadowGame:
    g = ShadowGame(chat_id, host_id, host_name, host_mention)
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
    return db["shadow_stats"] if db is not None else None


def _games_col():
    return db["shadow_games"] if db is not None else None


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
                "correct_guesses": 0,
                "wrong_guesses": 0,
                "wins_as_monarch": 0,
                "wins_as_strategist": 0,
                "wins_as_sentinel": 0,
                "wins_as_phantom": 0,
                "total_coins_won": 0,
                "last_played": None,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_result(user_id: int, name: str, *, role: str,
                        won: bool = False, correct_guess: Optional[bool] = None,
                        coins_won: int = 0):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, name)

    inc = {"games_played": 1, "total_coins_won": int(coins_won)}
    if role == ROLE_MONARCH:
        inc["wins_as_monarch"] = 1
    elif role == ROLE_STRATEGIST:
        inc["wins_as_strategist"] = 1 if correct_guess else 0
        if correct_guess is True:
            inc["correct_guesses"] = 1
        elif correct_guess is False:
            inc["wrong_guesses"] = 1
    elif role == ROLE_SENTINEL:
        inc["wins_as_sentinel"] = 1
    elif role == ROLE_PHANTOM:
        inc["wins_as_phantom"] = 1 if not correct_guess else 0

    await col.update_one(
        {"_id": int(user_id)},
        {"$inc": inc, "$set": {"name": name, "updated_at": _now(), "last_played": _now()}},
    )


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
        [("total_coins_won", -1), ("correct_guesses", -1)]
    ).limit(limit).to_list(length=limit)


async def persist_game(game: ShadowGame):
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
                "players": game.players,
                "state": game.state,
                "round_id": game.round_id,
                "monarch_id": game.monarch_id,
                "strategist_id": game.strategist_id,
                "sentinel_id": game.sentinel_id,
                "phantom_id": game.phantom_id,
                "guess_result": game.guess_result,
                "rewards": {str(k): v for k, v in game.rewards.items()},
                "payout_done": bool(game.payout_done),
                "created_at": game.created_at,
                "updated_at": _now(),
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[Shadow persist] {type(e).__name__}: {e}", flush=True)


async def remove_persisted_game(chat_id: int):
    col = _games_col()
    if col is None:
        return
    try:
        await col.delete_one({"_id": int(chat_id)})
    except Exception:
        pass


async def recover_active_games() -> int:
    """On boot: mark in-flight games CANCELLED (no rewards paid)."""
    col = _games_col()
    if col is None:
        return 0
    count = 0
    async for doc in col.find({"state": {"$in": [STATE_LOBBY, STATE_INTRO, STATE_ASSIGNED, STATE_GUESSING, STATE_REVEALING]}}):
        try:
            await col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"state": STATE_CANCELLED, "cancelled_on_boot": True, "updated_at": _now()}},
            )
            count += 1
        except Exception:
            pass
    return count
