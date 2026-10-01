# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/card_engine.py — Card Game Logic (equal-sum, turns, auto-play)
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from database.mongo import db


# ─── Constants ─────────────────────────────────────────────────────────────────
ENTRY_FEE_MIN = 100
ENTRY_FEE_MAX = 500_000
MAX_PLAYERS_LIMIT = 10
LOBBY_SECONDS = 120          # 2 minutes
TURN_SECONDS = 60            # 60 sec per turn
GAME_FEE_PERCENT = 0.10      # 10% fee
WINNER_XP = 100              # per win
LOSER_XP = 10                # consolation XP
CARD_LABELS = ["a", "b", "c", "d"]

# In-memory active games keyed by chat_id
ACTIVE_GAMES: dict[int, "CardGame"] = {}


# ─── Helpers ───────────────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc)


def _card_sum_ok(hands: list[list[int]]) -> bool:
    if not hands:
        return False
    target = sum(hands[0])
    return all(sum(h) == target for h in hands) and len(hands[0]) == 4


def _generate_equal_hands(player_count: int) -> list[list[int]]:
    target = random.randint(12, 30)

    hands: list[list[int]] = []
    for _ in range(player_count):
        for attempt in range(200):
            cards = [random.randint(1, 10) for _ in range(3)]
            remaining = target - sum(cards)
            if 1 <= remaining <= 10:
                cards.append(remaining)
                random.shuffle(cards)
                hands.append(cards)
                break
        else:
            base = target // 4
            cards = [base] * 4
            rem = target - sum(cards)
            for i in range(rem):
                cards[i % 4] += 1
            hands.append(cards)

    if not _card_sum_ok(hands):
        base = target // 4
        rem = target % 4
        fallback = [base] * 4
        for i in range(rem):
            fallback[i] += 1
        hands = [fallback.copy() for _ in range(player_count)]

    return hands


# ─── Card Game Class ──────────────────────────────────────────────────────────
class CardGame:
    def __init__(self, chat_id: int, entry_fee: int, max_players: int, creator_id: int):
        self.chat_id = int(chat_id)
        self.entry_fee = int(entry_fee)
        self.max_players = int(max_players)
        self.creator_id = int(creator_id)

        self.players: list[dict] = []
        self.state = "lobby"
        self.round = 0
        self.turn_index = 0
        self.round_plays: dict[int, int] = {}
        self.total_points: dict[int, int] = {}
        self.start_time: Optional[datetime] = None
        self.turn_task: Optional[asyncio.Task] = None
        self.lobby_task: Optional[asyncio.Task] = None
        self.winner_id: Optional[int] = None
        self.payout_done = False

        # ✅ Message tracking
        self.game_messages: list[int] = []        # delete at end
        self.pinned_msg_id: Optional[int] = None   # pin during game

    def has_player(self, user_id: int) -> bool:
        return any(p["user_id"] == int(user_id) for p in self.players)

    def get_player(self, user_id: int) -> Optional[dict]:
        for p in self.players:
            if p["user_id"] == int(user_id):
                return p
        return None

    def add_player(self, user_id: int, name: str, mention: str, hand: list[int] | None = None) -> bool:
        if self.has_player(user_id):
            return False
        if len(self.players) >= self.max_players:
            return False
        self.players.append({
            "user_id": int(user_id),
            "name": name,
            "mention": mention,
            "hand": hand or [],
            "used": [False, False, False, False],
            "round_scores": [],
        })
        self.total_points[int(user_id)] = 0
        return True

    def is_full(self) -> bool:
        return len(self.players) >= self.max_players

    def current_player(self) -> Optional[dict]:
        if not self.players:
            return None
        self.turn_index %= len(self.players)
        return self.players[self.turn_index]

    def next_turn(self):
        self.turn_index = (self.turn_index + 1) % max(1, len(self.players))

    def reset_round_plays(self):
        self.round_plays = {}

    def all_played_this_round(self) -> bool:
        return len(self.round_plays) == len(self.players)

    def remaining_cards(self, user_id: int) -> list[str]:
        p = self.get_player(user_id)
        if not p:
            return []
        return [CARD_LABELS[i] for i, used in enumerate(p["used"]) if not used]

    def use_card(self, user_id: int, card_label: str) -> tuple[bool, str, int | None]:
        p = self.get_player(user_id)
        if not p:
            return False, "not_player", None

        card_label = card_label.lower().strip()
        if card_label not in CARD_LABELS:
            return False, "invalid_card", None

        idx = CARD_LABELS.index(card_label)
        if p["used"][idx]:
            return False, "already_used", None

        if int(user_id) in self.round_plays:
            return False, "already_played_round", None

        p["used"][idx] = True
        value = p["hand"][idx]
        self.round_plays[int(user_id)] = idx
        return True, "ok", value

    def auto_play(self, user_id: int) -> tuple[bool, str, int | None]:
        p = self.get_player(user_id)
        if not p:
            return False, "not_player", None
        if int(user_id) in self.round_plays:
            return False, "already_played_round", None
        for i, used in enumerate(p["used"]):
            if not used:
                p["used"][i] = True
                self.round_plays[int(user_id)] = i
                return True, "ok", p["hand"][i]
        return False, "no_cards", None

    def is_finished(self) -> bool:
        return self.state == "finished"

    def to_summary(self) -> str:
        lines = []
        for p in self.players:
            lines.append(f"• {p['name']} — {self.total_points.get(p['user_id'], 0)}")
        return "\n".join(lines)


# ─── Game Registry ────────────────────────────────────────────────────────────
def get_game(chat_id: int) -> Optional[CardGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def create_game(chat_id: int, entry_fee: int, max_players: int, creator_id: int) -> CardGame:
    existing = ACTIVE_GAMES.get(int(chat_id))
    if existing and existing.is_finished():
        ACTIVE_GAMES.pop(int(chat_id), None)

    game = CardGame(chat_id, entry_fee, max_players, creator_id)
    ACTIVE_GAMES[int(chat_id)] = game
    return game


def remove_game(chat_id: int):
    ACTIVE_GAMES.pop(int(chat_id), None)


# ─── Database (leaderboard) ────────────────────────────────────────────────────
def _lb_col():
    return db["card_game_stats"] if db is not None else None


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
                "total_points": 0,
                "streak": 0,
                "best_streak": 0,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_game_result(user_id: int, name: str, points: int, won: bool):
    col = _lb_col()
    if col is None:
        return
    await ensure_stats(user_id, name)

    inc = {"played": 1, "total_points": int(points)}
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


async def top_leaders(limit: int = 10):
    col = _lb_col()
    if col is None:
        return []
    return await col.find().sort([("won", -1), ("total_points", -1)]).limit(limit).to_list(length=limit)
