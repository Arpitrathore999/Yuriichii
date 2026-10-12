# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/wordchain_engine.py — 🔗 Word Chain Game Engine
#  9 modes, lobby system, turn timers, elimination, leaderboard
#  + Dynamic timer & word-length progression
#  + Fixed cancel_timers (no self-cancel during finish)
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from database.mongo import db


# ══════════════════════════════════════════════════════════════════════════════
#  MODE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
MODE_CLASSIC = "classic"
MODE_ELIMINATION = "elimination"
MODE_MIXED = "mixed"
MODE_BANNED = "banned"
MODE_CHOSEN = "chosen"
MODE_RANDOM = "random"
MODE_REQUIRED = "required"
MODE_HARD = "hard"
MODE_CHAOS = "chaos"

MODE_CONFIG = {
    MODE_CLASSIC: {"label": "🎯 ᴄʟᴀꜱꜱɪᴄ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": False},
    MODE_ELIMINATION: {"label": "⚔️ ᴇʟɪᴍɪɴᴀᴛɪᴏɴ", "min_players": 5, "max_players": 30, "lobby_seconds": 90, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": True},
    MODE_MIXED: {"label": "🌀 ᴍɪxᴇᴅ ᴇʟɪᴍɪɴᴀᴛɪᴏɴ", "min_players": 4, "max_players": 30, "lobby_seconds": 90, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": True},
    MODE_BANNED: {"label": "🚫 ʙᴀɴɴᴇᴅ ʟᴇᴛᴛᴇʀꜱ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": False},
    MODE_CHOSEN: {"label": "✍️ ᴄʜᴏꜱᴇɴ ꜰɪʀꜱᴛ ʟᴇᴛᴛᴇʀ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": False},
    MODE_RANDOM: {"label": "🎲 ʀᴀɴᴅᴏᴍ ꜰɪʀꜱᴛ ʟᴇᴛᴛᴇʀ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": False},
    MODE_REQUIRED: {"label": "🔠 ʀᴇQᴜɪʀᴇᴅ ʟᴇᴛᴛᴇʀ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": False},
    MODE_HARD: {"label": "🔥 ʜᴀʀᴅ ᴍᴏᴅᴇ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": True},
    MODE_CHAOS: {"label": "🌪 ᴄʜᴀᴏꜱ ᴍᴏᴅᴇ", "min_players": 2, "max_players": 50, "lobby_seconds": 60, "max_lobby_seconds": 180, "turn_seconds": 40, "min_word_len": 3, "max_word_len": 15, "timeout_eliminates": True},
}

CHAOS_EVENTS = [
    {"name": "🚫 ʙᴀɴɴᴇᴅ ʟᴇᴛᴛᴇʀ", "kind": "banned", "duration": 3},
    {"name": "🔠 ʀᴇQᴜɪʀᴇᴅ ʟᴇᴛᴛᴇʀ", "kind": "required", "duration": 3},
    {"name": "📏 ʟᴏɴɢᴇʀ ᴡᴏʀᴅꜱ", "kind": "min_len_up", "duration": 3},
    {"name": "⏱ ꜰᴀꜱᴛᴇʀ ᴛᴜʀɴꜱ", "kind": "timer_down", "duration": 3},
]


# ══════════════════════════════════════════════════════════════════════════════
#  DICTIONARY
# ══════════════════════════════════════════════════════════════════════════════
_DATA_DIR = Path("data")
_WORDS_FILE = _DATA_DIR / "wordseek_words.txt"
_WORDS_URL = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"

_VALID_WORDS: set[str] = set()
_WORDS_BY_LETTER: dict[str, list[str]] = {}
_DICT_LOADED = False
_DICT_LOCK = asyncio.Lock()


async def ensure_dictionary_loaded():
    global _DICT_LOADED
    if _DICT_LOADED:
        return
    async with _DICT_LOCK:
        if _DICT_LOADED:
            return
        _DATA_DIR.mkdir(exist_ok=True)
        if _WORDS_FILE.exists() and _WORDS_FILE.stat().st_size > 100_000:
            _load_file(_WORDS_FILE)
            _DICT_LOADED = True
            print(f"[WordChain] dict loaded from cache: {len(_VALID_WORDS)} words", flush=True)
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                async with s.get(_WORDS_URL) as r:
                    if r.status == 200:
                        text = await r.text()
                        _WORDS_FILE.write_text(text, encoding="utf-8")
                        _load_file(_WORDS_FILE)
                        _DICT_LOADED = True
                        print(f"[WordChain] dict downloaded: {len(_VALID_WORDS)} words", flush=True)
                        return
        except Exception as e:
            print(f"[WordChain] download failed: {type(e).__name__}: {e}", flush=True)
        _load_fallback()
        _DICT_LOADED = True
        print(f"[WordChain] dict fallback: {len(_VALID_WORDS)} words", flush=True)


def _load_file(path: Path):
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        w = line.strip().lower()
        if not w or not w.isalpha():
            continue
        if not (3 <= len(w) <= 15):
            continue
        _VALID_WORDS.add(w)
    _build_letter_index()


def _load_fallback():
    fallback = [
        "apple", "banana", "cat", "dog", "elephant", "fish", "grape", "house",
        "ice", "jungle", "kite", "lemon", "monkey", "nest", "orange", "piano",
        "queen", "rabbit", "sun", "tiger", "umbrella", "van", "water", "xray",
        "yellow", "zebra", "book", "table", "chair", "window", "garden", "flower",
        "river", "mountain", "ocean", "forest", "cloud", "thunder", "storm",
    ]
    for w in fallback:
        _VALID_WORDS.add(w)
    _build_letter_index()


def _build_letter_index():
    global _WORDS_BY_LETTER
    _WORDS_BY_LETTER = {}
    for w in _VALID_WORDS:
        if w:
            _WORDS_BY_LETTER.setdefault(w[0], []).append(w)


def is_english_word(word: str) -> bool:
    return word.lower() in _VALID_WORDS


def random_word_starting_with(letter: str) -> Optional[str]:
    words = _WORDS_BY_LETTER.get((letter or "").lower(), [])
    return random.choice(words) if words else None


def dict_size() -> int:
    return len(_VALID_WORDS)


# ══════════════════════════════════════════════════════════════════════════════
#  LOCKS
# ══════════════════════════════════════════════════════════════════════════════
_GAME_LOCKS: dict[int, asyncio.Lock] = {}


def _game_lock(chat_id: int) -> asyncio.Lock:
    lock = _GAME_LOCKS.get(int(chat_id))
    if lock is None:
        lock = asyncio.Lock()
        _GAME_LOCKS[int(chat_id)] = lock
    return lock


def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════════════════════════
class WordChainGame:
    def __init__(self, chat_id: int, mode: str, starter_id: int, starter_name: str):
        self.chat_id = int(chat_id)
        self.mode = mode
        self.cfg = MODE_CONFIG.get(mode, MODE_CONFIG[MODE_CLASSIC])
        self.starter_id = int(starter_id)
        self.starter_name = starter_name

        self.players: list[dict] = []
        self.player_order: list[int] = []
        self.turn_index: int = 0

        self.status = "lobby"
        self.last_word: Optional[str] = None
        self.required_letter: Optional[str] = None
        self.used_words: set[str] = set()
        self.round_no: int = 0

        self.banned_letters: set[str] = set()
        self.required_letter_anywhere: Optional[str] = None
        self.chosen_first_letter: Optional[str] = None
        self.chaos_events: list[dict] = []

        self.winner_id: Optional[int] = None
        self.winner_name: Optional[str] = None
        self.elimination_order: list[int] = []

        self.lobby_task: Optional[asyncio.Task] = None
        self.turn_task: Optional[asyncio.Task] = None
        self.lobby_deadline: Optional[datetime] = None
        self.turn_deadline: Optional[datetime] = None
        self.turn_started_by_player: Optional[int] = None

        self.lobby_message_id: Optional[int] = None
        self.board_message_id: Optional[int] = None

        self.created_at = _now()
        self.ended_at: Optional[datetime] = None
        self.max_lobby_extend: int = self.cfg.get("max_lobby_seconds", 180)

    # ── Player helpers ──
    def alive_players(self) -> list[dict]:
        return [p for p in self.players if p["alive"]]

    def player_count(self) -> int:
        return len(self.players)

    def has_player(self, user_id: int) -> bool:
        return any(p["user_id"] == int(user_id) for p in self.players)

    def get_player(self, user_id: int) -> Optional[dict]:
        for p in self.players:
            if p["user_id"] == int(user_id):
                return p
        return None

    def add_player(self, user_id: int, name: str) -> bool:
        if self.has_player(user_id):
            return False
        if len(self.players) >= self.cfg["max_players"]:
            return False
        self.players.append({"user_id": int(user_id), "name": name, "alive": True})
        return True

    def remove_player(self, user_id: int) -> bool:
        p = self.get_player(user_id)
        if not p:
            return False
        self.players.remove(p)
        return True

    def is_full(self) -> bool:
        return len(self.players) >= self.cfg["max_players"]

    def can_start(self) -> bool:
        return len(self.players) >= self.cfg["min_players"]

    # ── Turn ──
    def current_player(self) -> Optional[dict]:
        alive = self.alive_players()
        if not alive:
            return None
        while True:
            if self.turn_index >= len(self.players):
                self.turn_index = 0
            p = self.players[self.turn_index]
            if p["alive"]:
                return p
            self.turn_index = (self.turn_index + 1) % len(self.players)
            if self.turn_index == 0 and not any(x["alive"] for x in self.players):
                return None

    def next_turn(self):
        if not self.players:
            return
        self.turn_index = (self.turn_index + 1) % len(self.players)
        for _ in range(len(self.players)):
            if self.players[self.turn_index]["alive"]:
                return
            self.turn_index = (self.turn_index + 1) % len(self.players)

    # ── Dynamic progression ──
    def current_min_len(self) -> int:
        tier = min(len(self.used_words) // 5, 5)
        return [3, 4, 5, 6, 7, 8][tier]

    def current_turn_seconds(self) -> int:
        tier = min(len(self.used_words) // 5, 5)
        base = [40, 35, 30, 25, 20, 10][tier]
        for ev in self.chaos_events:
            if ev.get("kind") == "timer_down":
                base = min(base, ev.get("value", base))
        return base

    # ── Validation ──
    def validate_word(self, word: str, user_id: int) -> tuple[bool, str]:
        w = (word or "").strip().lower()
        if not w or not w.isalpha():
            return False, "invalid_characters"

        min_len = self.current_min_len()
        max_len = self.cfg["max_word_len"]
        for ev in self.chaos_events:
            if ev.get("kind") == "min_len_up":
                min_len = max(min_len, ev.get("value", min_len))

        if len(w) < min_len:
            return False, f"too_short (min {min_len})"
        if len(w) > max_len:
            return False, f"too_long (max {max_len})"
        if not is_english_word(w):
            return False, "not_in_dictionary"

        if self.last_word is None:
            if self.chosen_first_letter and not w.startswith(self.chosen_first_letter.lower()):
                return False, f"must_start_with:{self.chosen_first_letter.upper()}"
            if self.required_letter and not w.startswith(self.required_letter.lower()):
                return False, f"must_start_with:{self.required_letter.upper()}"
        else:
            required = self.last_word[-1].lower()
            if not w.startswith(required):
                return False, f"must_start_with:{required.upper()}"

        for b in self.banned_letters:
            if b.lower() in w:
                return False, f"banned_letter:{b.upper()}"

        for ev in self.chaos_events:
            if ev.get("kind") == "banned" and ev.get("letter"):
                if ev["letter"].lower() in w:
                    return False, f"banned_letter:{ev['letter'].upper()}"

        if self.required_letter_anywhere and self.required_letter_anywhere.lower() not in w:
            return False, f"required_letter:{self.required_letter_anywhere.upper()}"

        for ev in self.chaos_events:
            if ev.get("kind") == "required" and ev.get("letter"):
                if ev["letter"].lower() not in w:
                    return False, f"required_letter:{ev['letter'].upper()}"

        if w in self.used_words:
            return False, "already_used"

        return True, "ok"

    def apply_word(self, word: str, user_id: int):
        w = word.lower().strip()
        self.used_words.add(w)
        self.last_word = w
        self.required_letter = w[-1].upper()

    def eliminate(self, user_id: int):
        p = self.get_player(user_id)
        if p and p["alive"]:
            p["alive"] = False
            self.elimination_order.append(user_id)

    def check_winner(self) -> Optional[dict]:
        alive = self.alive_players()
        if len(alive) == 1:
            return alive[0]
        return None

    def finish(self, winner_id: Optional[int] = None, winner_name: Optional[str] = None):
        self.status = "finished"
        self.winner_id = winner_id
        self.winner_name = winner_name
        self.ended_at = _now()

    def cancel(self):
        self.status = "cancelled"
        self.ended_at = _now()

    def cancel_timers(self):
        """✅ FIXED: Don't cancel the current running task."""
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for attr in ("lobby_task", "turn_task"):
            t = getattr(self, attr, None)
            if t and not t.done() and t is not current:
                t.cancel()
            setattr(self, attr, None)


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
ACTIVE_GAMES: dict[int, WordChainGame] = {}
USER_ACTIVE: dict[int, int] = {}


def get_game(chat_id: int) -> Optional[WordChainGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def get_user_game(user_id: int) -> Optional[WordChainGame]:
    cid = USER_ACTIVE.get(int(user_id))
    if cid is None:
        return None
    game = ACTIVE_GAMES.get(int(cid))
    if not game or game.status in ("finished", "cancelled"):
        USER_ACTIVE.pop(int(user_id), None)
        return None
    return game


def create_game(chat_id: int, mode: str, starter_id: int, starter_name: str) -> WordChainGame:
    game = WordChainGame(chat_id, mode, starter_id, starter_name)
    ACTIVE_GAMES[int(chat_id)] = game
    return game


def remove_game(chat_id: int):
    game = ACTIVE_GAMES.pop(int(chat_id), None)
    if not game:
        return
    # Don't call cancel_timers here — caller handles it
    for p in game.players:
        if USER_ACTIVE.get(p["user_id"]) == int(chat_id):
            USER_ACTIVE.pop(p["user_id"], None)


# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
def _stats_col():
    return db["wordchain_stats"] if db is not None else None


def _games_col():
    return db["wordchain_games"] if db is not None else None


async def ensure_stats(user_id: int, username: str, first_name: str):
    col = _stats_col()
    if col is None:
        return
    await col.update_one(
        {"_id": int(user_id)},
        {
            "$set": {"username": username or "", "first_name": first_name or "", "updated_at": _now()},
            "$setOnInsert": {
                "_id": int(user_id),
                "games_played": 0, "games_won": 0, "games_lost": 0,
                "words_submitted": 0, "longest_word": "", "longest_word_len": 0,
                "win_streak": 0, "best_streak": 0, "points": 0,
                "mode_stats": {}, "last_played": None, "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_result(user_id: int, username: str, first_name: str, won: bool,
                        word_count: int = 0, longest_word: str = "", points: int = 0,
                        mode: str = "classic"):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, username, first_name)
    doc = await col.find_one({"_id": int(user_id)}) or {}
    new_streak = int(doc.get("win_streak", 0)) + 1 if won else 0
    best_streak = max(new_streak, int(doc.get("best_streak", 0)))
    prev_longest_len = int(doc.get("longest_word_len", 0))
    new_longest = longest_word if len(longest_word) > prev_longest_len else doc.get("longest_word", "")
    new_longest_len = max(prev_longest_len, len(longest_word))

    inc = {"games_played": 1, "words_submitted": int(word_count), "points": int(points)}
    if won:
        inc["games_won"] = 1
    else:
        inc["games_lost"] = 1

    update = {
        "$inc": inc,
        "$set": {
            "win_streak": new_streak, "best_streak": best_streak,
            "longest_word": new_longest, "longest_word_len": new_longest_len,
            "last_played": _now(), "updated_at": _now(),
            f"mode_stats.{mode}.played": 1,
        },
    }
    if won:
        update["$inc"][f"mode_stats.{mode}.won"] = 1
    await col.update_one({"_id": int(user_id)}, update)


async def get_stats(user_id: int):
    col = _stats_col()
    return await col.find_one({"_id": int(user_id)}) if col is not None else None


async def top_players(limit: int = 10):
    col = _stats_col()
    if col is None:
        return []
    return await col.find().sort([("points", -1), ("games_won", -1)]).limit(limit).to_list(length=limit)


async def persist_game(game: WordChainGame):
    col = _games_col()
    if col is None:
        return
    try:
        await col.update_one(
            {"_id": int(game.chat_id)},
            {"$set": {
                "chat_id": int(game.chat_id), "mode": game.mode,
                "starter_id": int(game.starter_id), "starter_name": game.starter_name,
                "players": game.players, "player_order": game.player_order,
                "turn_index": int(game.turn_index), "status": game.status,
                "last_word": game.last_word, "required_letter": game.required_letter,
                "used_words": list(game.used_words),
                "winner_id": game.winner_id, "winner_name": game.winner_name,
                "created_at": game.created_at, "updated_at": _now(),
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[WordChain persist] {type(e).__name__}: {e}", flush=True)


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
    count = 0
    try:
        async for doc in col.find({"status": {"$in": ["lobby", "running"]}}):
            try:
                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"status": "cancelled", "cancelled_on_restart": True}},
                )
                count += 1
            except Exception:
                pass
    except Exception as e:
        print(f"[WordChain recovery] {type(e).__name__}: {e}", flush=True)
    return count


# ══════════════════════════════════════════════════════════════════════════════
#  SCORING
# ══════════════════════════════════════════════════════════════════════════════
def compute_points(mode: str, word_count: int, longest_word_len: int, won: bool) -> int:
    base = 10 + word_count * 2 + longest_word_len
    if won:
        base += 30
    if mode == MODE_HARD:
        base = int(base * 1.5)
    elif mode in (MODE_ELIMINATION, MODE_MIXED):
        base = int(base * 1.2)
    elif mode == MODE_CHAOS:
        base = int(base * 1.3)
    return max(0, base)
