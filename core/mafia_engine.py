# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/mafia_engine.py — 🎭 MAFIA Game Engine
#  1 Mafia, 1 Detective, rest Villagers. No Doctor.
#  Paid + Free mode. Vote eliminates 1 player per round.
#  All text in English.
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
ROLE_MAFIA     = "mafia"
ROLE_DETECTIVE = "detective"
ROLE_VILLAGER  = "villager"

ROLE_EMOJI = {
    ROLE_MAFIA:     "🔪",
    ROLE_DETECTIVE: "🕵️",
    ROLE_VILLAGER:  "👥",
}
ROLE_LABEL = {
    ROLE_MAFIA:     "MAFIA",
    ROLE_DETECTIVE: "DETECTIVE",
    ROLE_VILLAGER:  "VILLAGER",
}

STATE_LOBBY     = "LOBBY"
STATE_NIGHT     = "NIGHT"
STATE_DAY       = "DAY"
STATE_VOTING    = "VOTING"
STATE_FINISHED  = "FINISHED"
STATE_CANCELLED = "CANCELLED"
TERMINAL = (STATE_FINISHED, STATE_CANCELLED)

MIN_PLAYERS   = 4
MAX_PLAYERS   = 10
LOBBY_SECONDS = 60
NIGHT_SECONDS = 30
DAY_SECONDS   = 45
VOTE_SECONDS  = 30

ENTRY_MIN = 100
ENTRY_MAX = 500_000
GAME_FEE_PERCENT = 0.10
WINNER_XP = 150
LOSER_XP  = 20
SPECTATOR_XP = 5

ACTIVE_GAMES: dict[int, "MafiaGame"] = {}
USER_ACTIVE: dict[int, int] = {}


def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════════════════════════
class MafiaGame:
    def __init__(self, chat_id: int, host_id: int, host_name: str,
                 host_mention: str, entry_fee: int = 0, is_paid: bool = True):
        self.chat_id      = int(chat_id)
        self.host_id      = int(host_id)
        self.host_name    = host_name
        self.host_mention = host_mention
        self.entry_fee    = int(entry_fee)
        self.is_paid      = bool(is_paid)

        self.players:   list[dict] = []
        self.roles:     dict[int, str] = {}
        self.alive:     list[int] = []
        self.dead:      list[int] = []

        self.state      = STATE_LOBBY
        self.day_no     = 0
        self.round_id:  Optional[str] = None

        self.night_kill:  Optional[int] = None
        self.night_check: Optional[int] = None
        self.night_kill_done  = False
        self.night_check_done = False

        self.votes: dict[int, int] = {}

        self.winner_side: Optional[str] = None

        self.lobby_task: Optional[asyncio.Task] = None
        self.phase_task: Optional[asyncio.Task] = None

        self.lobby_message_id: Optional[int] = None
        self.phase_message_id: Optional[int] = None

        self.payout_done = False
        self.refund_done = False
        self.gross_pool  = 0
        self.tax_amount  = 0
        self.net_prize   = 0

        self.created_at  = _now()
        self.finished_at: Optional[datetime] = None

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
            "user_id": int(uid), "name": name, "mention": mention,
            "paid": False, "alive": True,
        })
        return True

    def is_full(self) -> bool:  return len(self.players) >= MAX_PLAYERS
    def can_start(self) -> bool: return len(self.players) >= MIN_PLAYERS

    def alive_players(self) -> list[dict]:
        return [p for p in self.players if p["user_id"] in self.alive]

    def alive_count(self) -> int:
        return len(self.alive)

    def get_mafia(self) -> Optional[int]:
        for uid, r in self.roles.items():
            if r == ROLE_MAFIA:
                return uid
        return None

    def get_detective(self) -> Optional[int]:
        for uid, r in self.roles.items():
            if r == ROLE_DETECTIVE:
                return uid
        return None

    def assign_roles(self):
        """1 Mafia, 1 Detective, rest Villagers."""
        uids = [p["user_id"] for p in self.players]
        random.shuffle(uids)

        self.roles = {}
        self.roles[uids[0]] = ROLE_MAFIA
        self.roles[uids[1]] = ROLE_DETECTIVE
        for uid in uids[2:]:
            self.roles[uid] = ROLE_VILLAGER

        self.alive = list(uids)
        self.dead = []

    def submit_night_kill(self, target_uid: int) -> tuple[bool, str]:
        if self.state != STATE_NIGHT:
            return False, "not_night"
        if self.night_kill_done:
            return False, "already_done"
        mafia_uid = self.get_mafia()
        if not mafia_uid:
            return False, "no_mafia"
        if int(target_uid) == int(mafia_uid):
            return False, "self_target"
        if int(target_uid) not in self.alive:
            return False, "not_alive"
        self.night_kill = int(target_uid)
        self.night_kill_done = True
        return True, "ok"

    def submit_night_check(self, target_uid: int) -> tuple[bool, str]:
        if self.state != STATE_NIGHT:
            return False, "not_night"
        if self.night_check_done:
            return False, "already_done"
        det_uid = self.get_detective()
        if not det_uid:
            return False, "no_detective"
        if int(target_uid) == int(det_uid):
            return False, "self_target"
        if int(target_uid) not in self.alive:
            return False, "not_alive"
        self.night_check = int(target_uid)
        self.night_check_done = True
        return True, "ok"

    def resolve_night(self) -> Optional[int]:
        if self.night_kill_done and self.night_kill:
            victim = self.night_kill
            if victim in self.alive:
                self.alive.remove(victim)
                self.dead.append(victim)
                return victim
        return None

    def submit_vote(self, voter_uid: int, target_uid: int) -> tuple[bool, str]:
        if self.state != STATE_VOTING:
            return False, "not_voting"
        voter_uid = int(voter_uid)
        target_uid = int(target_uid)
        if voter_uid not in self.alive:
            return False, "not_alive"
        if target_uid not in self.alive and target_uid != -1:
            return False, "target_not_alive"
        if voter_uid == target_uid:
            return False, "self_vote"
        self.votes[voter_uid] = target_uid
        return True, "ok"

    def tally_votes(self) -> tuple[Optional[int], dict]:
        if not self.votes:
            return None, {}
        counts: dict[int, int] = {}
        for target in self.votes.values():
            if target == -1:
                continue
            counts[target] = counts.get(target, 0) + 1
        if not counts:
            return None, counts

        max_count = max(counts.values())
        top = [uid for uid, c in counts.items() if c == max_count]
        if len(top) > 1:
            return None, counts
        return top[0], counts

    def eliminate(self, uid: int):
        uid = int(uid)
        if uid in self.alive:
            self.alive.remove(uid)
        if uid not in self.dead:
            self.dead.append(uid)

    def check_winner(self) -> Optional[str]:
        mafia_uid = self.get_mafia()
        if mafia_uid is None:
            return None
        if mafia_uid not in self.alive:
            return "villagers"
        if self.alive_count() <= 2:
            return "mafia"
        return None

    def cancel_timers(self):
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for attr in ("lobby_task", "phase_task"):
            t = getattr(self, attr, None)
            if t and not t.done() and t is not current:
                t.cancel()
            setattr(self, attr, None)

    def is_terminal(self) -> bool:
        return self.state in TERMINAL


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
def get_game(chat_id: int) -> Optional[MafiaGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def get_user_game(uid: int) -> Optional[MafiaGame]:
    cid = USER_ACTIVE.get(int(uid))
    if cid is None:
        return None
    g = ACTIVE_GAMES.get(int(cid))
    if not g or g.is_terminal():
        USER_ACTIVE.pop(int(uid), None)
        return None
    return g


def create_game(chat_id, host_id, host_name, host_mention,
                entry_fee=0, is_paid=True) -> MafiaGame:
    g = MafiaGame(chat_id, host_id, host_name, host_mention, entry_fee, is_paid)
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
    return db["mafia_stats"] if db is not None else None


def _games_col():
    return db["mafia_games"] if db is not None else None


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
                "villager_wins": 0,
                "mafia_wins": 0,
                "detective_wins": 0,
                "losses": 0,
                "coins_wagered": 0,
                "gross_won": 0,
                "tax_paid": 0,
                "net_coins": 0,
                "mafia_kills": 0,
                "detective_catches": 0,
                "correct_votes": 0,
                "win_streak": 0,
                "best_streak": 0,
                "last_played": None,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_result(user_id: int, name: str, *, role: str, won: bool,
                        wagered: int = 0, gross_won: int = 0, tax_paid: int = 0):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, name)

    inc = {"games_played": 1, "coins_wagered": int(wagered)}
    if won:
        if role == ROLE_MAFIA:
            inc["mafia_wins"] = 1
        elif role == ROLE_DETECTIVE:
            inc["detective_wins"] = 1
        else:
            inc["villager_wins"] = 1
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

    if won:
        doc = await col.find_one({"_id": int(user_id)}, {"win_streak": 1, "best_streak": 1})
        cur = int((doc or {}).get("win_streak", 0)) + 1
        best = max(cur, int((doc or {}).get("best_streak", 0)))
        update["$set"]["win_streak"] = cur
        update["$set"]["best_streak"] = best
    else:
        update["$set"]["win_streak"] = 0

    await col.update_one({"_id": int(user_id)}, update)


async def bump_mafia_kills(user_id: int):
    col = _stats_col()
    if col is None:
        return
    try:
        await col.update_one({"_id": int(user_id)}, {"$inc": {"mafia_kills": 1}})
    except Exception:
        pass


async def bump_detective_catches(user_id: int):
    col = _stats_col()
    if col is None:
        return
    try:
        await col.update_one({"_id": int(user_id)}, {"$inc": {"detective_catches": 1}})
    except Exception:
        pass


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
        [("net_coins", -1), ("gross_won", -1)]
    ).limit(limit).to_list(length=limit)


async def persist_game(game: MafiaGame):
    col = _games_col()
    if col is None:
        return
    try:
        await col.update_one(
            {"_id": int(game.chat_id)},
            {"$set": {
                "chat_id": int(game.chat_id),
                "host_id": int(game.host_id),
                "entry_fee": int(game.entry_fee),
                "is_paid": bool(game.is_paid),
                "players": game.players,
                "roles": {str(k): v for k, v in game.roles.items()},
                "alive": list(game.alive),
                "dead": list(game.dead),
                "state": game.state,
                "day_no": int(game.day_no),
                "winner_side": game.winner_side,
                "payout_done": bool(game.payout_done),
                "refund_done": bool(game.refund_done),
                "updated_at": _now(),
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[Mafia persist] {type(e).__name__}: {e}", flush=True)


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
    async for doc in col.find({"state": {"$in": [STATE_LOBBY, STATE_NIGHT, STATE_DAY, STATE_VOTING]}}):
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
            print(f"[Mafia recover] {type(e).__name__}: {e}", flush=True)
    return count
