# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/wordseek_engine.py — 🎯 WordSeek Game Engine
# --------------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from database.mongo import db


# ── Constants ──
MAX_ATTEMPTS = 30
WORD_LENGTHS = (4, 5, 6)
BASE_SCORE = {4: 20, 5: 25, 6: 30}
ATTEMPT_BONUS_DIVISOR = 2
HINT_PENALTY = 5

TILE_GREEN = "🟩"
TILE_YELLOW = "🟨"
TILE_RED = "🟥"

# Per-game locks
_GAME_LOCKS: dict = {}


def _game_lock(chat_id: int) -> asyncio.Lock:
    lock = _GAME_LOCKS.get(int(chat_id))
    if lock is None:
        lock = asyncio.Lock()
        _GAME_LOCKS[int(chat_id)] = lock
    return lock


def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
#  WORD DICTIONARIES
#  Curated English words — no proper nouns, no offensive content
# ══════════════════════════════════════════════════════════════════════════════

WORDS_4 = [
    "able", "acid", "aged", "also", "area", "army", "away", "baby", "back", "ball",
    "band", "bank", "base", "bath", "bear", "beat", "been", "beer", "bell", "belt",
    "best", "bike", "bird", "blow", "blue", "boat", "body", "bomb", "bond", "bone",
    "book", "boom", "born", "boss", "both", "bowl", "bulk", "burn", "bush", "busy",
    "cake", "call", "calm", "came", "camp", "card", "care", "case", "cash", "cast",
    "cell", "chat", "chip", "city", "club", "coal", "coat", "code", "cold", "come",
    "cook", "cool", "cope", "copy", "core", "cost", "crew", "crop", "dark", "data",
    "date", "dawn", "days", "dead", "deal", "dean", "dear", "debt", "deep", "deny",
    "desk", "dial", "died", "diet", "disc", "disk", "does", "done", "door", "dose",
    "down", "draw", "drew", "drop", "drug", "dual", "duke", "dust", "duty", "each",
    "earn", "ease", "east", "easy", "edge", "else", "even", "ever", "evil", "exit",
    "face", "fact", "fail", "fair", "fall", "farm", "fast", "fate", "fear", "feed",
    "feel", "feet", "fell", "felt", "file", "fill", "film", "find", "fine", "fire",
    "firm", "fish", "five", "flat", "flow", "food", "foot", "ford", "form", "fort",
    "four", "free", "from", "fuel", "full", "fund", "gain", "game", "gate", "gave",
    "gear", "gene", "gift", "girl", "give", "glad", "goal", "goes", "gold", "golf",
    "gone", "good", "gray", "grew", "grey", "grow", "gulf", "hair", "half", "hall",
    "hand", "hang", "hard", "harm", "hate", "have", "head", "hear", "heat", "held",
    "hell", "help", "here", "hero", "high", "hill", "hire", "hold", "hole", "holy",
    "home", "hope", "host", "hour", "huge", "hung", "hunt", "hurt", "idea", "inch",
    "into", "iron", "item", "jack", "jane", "jean", "john", "join", "jump", "june",
    "jury", "just", "keen", "keep", "kent", "kept", "kick", "kill", "kind", "king",
    "knee", "knew", "know", "lack", "lady", "laid", "lake", "land", "lane", "last",
    "late", "lead", "left", "less", "life", "lift", "like", "line", "link", "list",
    "live", "load", "loan", "lock", "long", "look", "lord", "lose", "loss", "lost",
    "love", "luck", "made", "mail", "main", "make", "male", "many", "mark", "mass",
    "matt", "meal", "mean", "meat", "meet", "menu", "mere", "mike", "mile", "milk",
    "mill", "mind", "mine", "miss", "mode", "mood", "moon", "more", "most", "move",
    "much", "must", "name", "navy", "near", "neck", "need", "news", "next", "nice",
    "nick", "nine", "none", "nose", "note", "okay", "once", "only", "onto", "open",
    "oral", "over", "pace", "pack", "page", "paid", "pain", "pair", "palm", "park",
    "part", "pass", "past", "path", "peak", "pick", "pink", "pipe", "plan", "play",
    "plot", "plug", "plus", "poem", "poet", "pole", "poll", "pool", "poor", "port",
    "post", "pull", "pure", "push", "race", "rail", "rain", "rank", "rare", "rate",
    "read", "real", "rear", "rely", "rent", "rest", "rice", "rich", "ride", "ring",
    "rise", "risk", "road", "rock", "role", "roll", "roof", "room", "root", "rose",
    "rule", "rush", "safe", "said", "sale", "salt", "same", "sand", "save", "seat",
    "seed", "seek", "seem", "seen", "self", "sell", "send", "sent", "sept", "ship",
    "shop", "shot", "show", "shut", "sick", "side", "sign", "silk", "sing", "sink",
    "site", "size", "skin", "slip", "slow", "snow", "soft", "soil", "sold", "sole",
    "some", "song", "soon", "sort", "soul", "spot", "star", "stay", "step", "stop",
    "such", "suit", "sure", "take", "tale", "talk", "tall", "tank", "tape", "task",
    "team", "tear", "tell", "tend", "term", "test", "text", "than", "that", "them",
    "then", "they", "thin", "this", "thus", "till", "time", "tiny", "told", "toll",
    "tone", "took", "tool", "tour", "town", "tree", "trip", "true", "turn", "twin",
    "type", "unit", "upon", "used", "user", "vary", "vast", "very", "vice", "view",
    "vote", "wage", "wait", "wake", "walk", "wall", "want", "ward", "warm", "warn",
    "wash", "wave", "ways", "weak", "wear", "week", "well", "went", "were", "west",
    "what", "when", "whom", "wide", "wife", "wild", "will", "wind", "wine", "wing",
    "wire", "wise", "wish", "with", "wood", "word", "wore", "work", "yard", "yeah",
    "year", "your", "zero", "zone",
]

WORDS_5 = [
    "about", "above", "abuse", "actor", "acute", "admit", "adopt", "adult", "after",
    "again", "agent", "agree", "ahead", "alarm", "album", "alert", "alike", "alive",
    "allow", "alone", "along", "alter", "among", "anger", "angle", "angry", "apart",
    "apple", "apply", "arena", "argue", "arise", "array", "aside", "asset", "audio",
    "audit", "avoid", "award", "aware", "badly", "baker", "bases", "basic", "basis",
    "beach", "began", "begin", "begun", "being", "below", "bench", "birth", "black",
    "blame", "blind", "block", "blood", "board", "boost", "booth", "bound", "brain",
    "brand", "bread", "break", "breed", "brief", "bring", "broad", "broke", "brown",
    "build", "built", "buyer", "catch", "cause", "chain", "chair", "chaos", "charm",
    "chart", "chase", "cheap", "check", "chest", "chief", "child", "china", "chose",
    "civil", "claim", "class", "clean", "clear", "click", "climb", "clock", "close",
    "cloud", "coach", "coast", "could", "count", "court", "cover", "craft", "crash",
    "cream", "crime", "cross", "crowd", "crown", "curve", "cycle", "daily", "dance",
    "dated", "dealt", "death", "debut", "delay", "depth", "doing", "doubt", "dozen",
    "draft", "drama", "drawn", "dream", "dress", "drill", "drink", "drive", "drove",
    "dying", "eager", "early", "earth", "eight", "elite", "empty", "enemy", "enjoy",
    "enter", "entry", "equal", "error", "event", "every", "exact", "exist", "extra",
    "faith", "false", "fault", "fiber", "field", "fifth", "fifty", "fight", "final",
    "first", "fixed", "flash", "fleet", "floor", "fluid", "focus", "force", "forth",
    "forty", "forum", "found", "frame", "frank", "fraud", "fresh", "front", "fruit",
    "fully", "funny", "giant", "given", "glass", "globe", "going", "grace", "grade",
    "grand", "grant", "grass", "great", "green", "gross", "group", "grown", "guard",
    "guess", "guest", "guide", "happy", "heart", "heavy", "hence", "horse", "hotel",
    "house", "human", "ideal", "image", "index", "inner", "input", "issue", "japan",
    "joint", "judge", "known", "label", "large", "laser", "later", "laugh", "layer",
    "learn", "lease", "least", "leave", "legal", "level", "light", "limit", "links",
    "lives", "local", "logic", "loose", "lower", "lucky", "lunch", "lying", "magic",
    "major", "maker", "march", "match", "maybe", "mayor", "meant", "media", "metal",
    "might", "minor", "minus", "mixed", "model", "money", "month", "moral", "motor",
    "mount", "mouse", "mouth", "movie", "music", "needs", "never", "newly", "night",
    "noise", "north", "noted", "novel", "nurse", "occur", "ocean", "offer", "often",
    "order", "other", "ought", "outer", "owner", "paint", "panel", "paper", "party",
    "peace", "phase", "phone", "photo", "piece", "pilot", "pitch", "place", "plain",
    "plane", "plant", "plate", "point", "pound", "power", "press", "price", "pride",
    "prime", "print", "prior", "prize", "proof", "proud", "prove", "queen", "quick",
    "quiet", "quite", "radio", "raise", "range", "rapid", "ratio", "reach", "ready",
    "refer", "right", "rival", "river", "robin", "rough", "round", "route", "royal",
    "rural", "scale", "scene", "scope", "score", "sense", "serve", "seven", "shall",
    "shape", "share", "sharp", "sheet", "shelf", "shell", "shift", "shine", "shirt",
    "shock", "shoot", "short", "shown", "sight", "since", "sixth", "sixty", "sized",
    "skill", "sleep", "slide", "small", "smart", "smile", "smith", "smoke", "solid",
    "solve", "sorry", "sound", "south", "space", "spare", "speak", "speed", "spend",
    "spent", "split", "spoke", "sport", "staff", "stage", "stake", "stand", "start",
    "state", "steam", "steel", "stick", "still", "stock", "stone", "stood", "store",
    "storm", "story", "strip", "stuck", "study", "stuff", "style", "sugar", "suite",
    "super", "sweet", "table", "taken", "taste", "taxes", "teach", "teeth", "thank",
    "theft", "their", "theme", "there", "these", "thick", "thing", "think", "third",
    "those", "three", "threw", "throw", "tight", "times", "tired", "title", "today",
    "topic", "total", "touch", "tough", "tower", "track", "trade", "train", "treat",
    "trend", "trial", "tried", "tries", "truck", "truly", "trust", "truth", "twice",
    "under", "undue", "union", "unity", "until", "upper", "upset", "urban", "usage",
    "usual", "valid", "value", "video", "virus", "visit", "vital", "voice", "waste",
    "watch", "water", "wheel", "where", "which", "while", "white", "whole", "whose",
    "woman", "women", "world", "worry", "worse", "worst", "worth", "would", "wound",
    "write", "wrong", "wrote", "young", "youth",
]

WORDS_6 = [
    "abroad", "accept", "access", "accuse", "across", "action", "active", "actual",
    "advice", "advise", "affair", "affect", "afford", "afraid", "agency", "agenda",
    "almost", "always", "amount", "animal", "annual", "answer", "anyone", "anyway",
    "appeal", "appear", "around", "arrive", "artist", "aspect", "assess", "assist",
    "assume", "assure", "attach", "attack", "attend", "author", "autumn", "avenue",
    "backed", "barely", "battle", "beauty", "became", "become", "before", "behalf",
    "behind", "belief", "belong", "beside", "better", "beyond", "bishop", "bitter",
    "blamed", "border", "boring", "borrow", "bottom", "bought", "branch", "brands",
    "breach", "breath", "bridge", "bright", "brings", "broken", "broker", "budget",
    "bureau", "butter", "button", "buying", "camera", "campus", "canada", "cancel",
    "cancer", "candle", "carbon", "career", "caring", "castle", "casual", "caught",
    "cellar", "center", "centre", "chance", "change", "charge", "choice", "choose",
    "chosen", "church", "circle", "client", "closed", "closer", "coffee", "column",
    "combat", "coming", "common", "comply", "copper", "corner", "costly", "cotton",
    "county", "couple", "course", "covers", "create", "credit", "crisis", "critic",
    "custom", "damage", "danger", "dealer", "debate", "decade", "decent", "decide",
    "deeply", "defeat", "defend", "define", "degree", "demand", "depend", "deploy",
    "deputy", "derive", "desire", "detail", "detect", "device", "differ", "dinner",
    "direct", "doctor", "dollar", "domain", "double", "driven", "driver", "during",
    "easily", "eating", "editor", "effect", "effort", "eighth", "either", "emerge",
    "empire", "employ", "enable", "ending", "energy", "engage", "engine", "enough",
    "ensure", "entire", "entity", "equity", "escape", "estate", "ethnic", "exceed",
    "except", "excess", "expand", "expect", "expert", "export", "extend", "extent",
    "fabric", "factor", "fairly", "fallen", "family", "famous", "father", "fellow",
    "female", "figure", "filter", "finish", "fiscal", "flower", "flying", "follow",
    "forced", "forest", "forget", "formal", "format", "former", "foster", "fought",
    "fourth", "french", "friend", "future", "garden", "gather", "gender", "gentle",
    "german", "giving", "global", "golden", "ground", "growth", "guilty", "handed",
    "handle", "happen", "hardly", "headed", "health", "hearing", "heavily", "height",
    "hidden", "holder", "honest", "impact", "import", "impose", "income", "indeed",
    "injury", "inside", "intact", "intend", "intent", "invest", "island", "itself",
    "jersey", "killed", "labour", "latest", "latter", "launch", "lawyer", "leader",
    "league", "leaves", "legacy", "length", "lesson", "letter", "likely", "linked",
    "liquid", "listen", "little", "living", "losing", "mainly", "making", "manage",
    "manner", "manual", "margin", "marine", "marked", "market", "master", "matter",
    "mature", "medium", "member", "memory", "mental", "merely", "merger", "method",
    "middle", "mighty", "mining", "minute", "mirror", "mobile", "modern", "modest",
    "module", "moment", "morning", "mother", "motion", "murder", "museum", "mutual",
    "myself", "narrow", "nation", "native", "nature", "nearby", "nearly", "nights",
    "nobody", "normal", "notice", "notion", "number", "object", "obtain", "office",
    "offset", "online", "option", "orange", "orders", "origin", "others", "output",
    "packed", "parent", "partly", "patent", "people", "period", "permit", "person",
    "phrase", "picked", "planet", "player", "please", "plenty", "pocket", "poetry",
    "police", "policy", "poorly", "postal", "potato", "powder", "praise", "prayer",
    "prefer", "pretty", "prince", "prison", "profit", "proper", "proven", "public",
    "pursue", "racial", "random", "rarely", "rather", "rating", "reader", "really",
    "reason", "recall", "recent", "record", "reduce", "reform", "regard", "regime",
    "region", "regret", "reject", "relate", "relief", "remain", "remote", "remove",
    "repair", "repeat", "report", "rescue", "resign", "resist", "resort", "result",
    "resume", "retail", "retain", "retire", "return", "reveal", "review", "reward",
    "riding", "rights", "robust", "rocket", "ruling", "safety", "salary", "sample",
    "saving", "saying", "scheme", "school", "screen", "script", "search", "season",
    "second", "secret", "sector", "secure", "select", "seller", "senior", "senses",
    "series", "server", "settle", "severe", "sexual", "should", "signal", "silent",
    "silver", "simple", "simply", "singer", "single", "sister", "slight", "smooth",
    "social", "solely", "sought", "source", "soviet", "speech", "spirit", "spread",
    "spring", "square", "stable", "status", "steady", "stereo", "stolen", "strain",
    "stream", "street", "stress", "strict", "strike", "string", "strong", "struck",
    "studio", "submit", "sudden", "suffer", "summer", "supply", "surely", "survey",
    "switch", "symbol", "system", "tablet", "tackle", "target", "taught", "temple",
    "tender", "tennis", "theory", "thirty", "though", "thread", "threat", "throat",
    "thrown", "ticket", "timber", "tissue", "tongue", "toward", "travel", "treaty",
    "trying", "twelve", "twenty", "unable", "unfair", "unique", "united", "unlike",
    "update", "useful", "valley", "vanish", "vendor", "versus", "victim", "viewer",
    "virtue", "vision", "volume", "walker", "warmth", "wealth", "weapon", "weekly",
    "weight", "whilst", "window", "winner", "winter", "wisdom", "within", "wonder",
    "wooden", "worker", "worthy", "writer", "yellow",
]


WORDSET_BY_LEN = {
    4: set(WORDS_4),
    5: set(WORDS_5),
    6: set(WORDS_6),
}
ANSWER_POOL_BY_LEN = {4: WORDS_4, 5: WORDS_5, 6: WORDS_6}


def get_random_word(length: int) -> Optional[str]:
    pool = ANSWER_POOL_BY_LEN.get(int(length))
    if not pool:
        return None
    return random.choice(pool)


def is_valid_word(word: str, length: int) -> bool:
    ws = WORDSET_BY_LEN.get(int(length))
    if ws is None:
        return False
    return word.lower() in ws


# ══════════════════════════════════════════════════════════════════════════════
#  TILE CALCULATION — Wordle algorithm (handles duplicates correctly)
# ══════════════════════════════════════════════════════════════════════════════
def calculate_tiles(secret: str, guess: str) -> list[str]:
    """Wordle-style tile calculation with proper duplicate handling.

    Algorithm:
    1. First pass — mark GREEN for exact position matches
    2. Second pass — mark YELLOW for letters present elsewhere,
       respecting the number of remaining occurrences in the secret
    3. Everything else — RED
    """
    secret = secret.lower()
    guess = guess.lower()
    n = len(secret)

    if len(guess) != n:
        return [TILE_RED] * len(guess)

    result = [TILE_RED] * n
    secret_used = [False] * n

    # Pass 1 — green
    for i in range(n):
        if guess[i] == secret[i]:
            result[i] = TILE_GREEN
            secret_used[i] = True

    # Pass 2 — yellow (respecting remaining counts)
    for i in range(n):
        if result[i] == TILE_GREEN:
            continue
        for j in range(n):
            if secret_used[j]:
                continue
            if guess[i] == secret[j]:
                result[i] = TILE_YELLOW
                secret_used[j] = True
                break

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════════════════════════
class WordSeekGame:
    def __init__(self, chat_id: int, length: int, starter_id: int, starter_name: str):
        self.chat_id = int(chat_id)
        self.length = int(length)
        self.starter_id = int(starter_id)
        self.starter_name = starter_name
        self.secret = get_random_word(self.length) or ""
        self.max_attempts = MAX_ATTEMPTS
        self.attempts = 0
        self.guesses: list[dict] = []
        self.status = "active"
        self.winner_id: Optional[int] = None
        self.winner_name: Optional[str] = None
        self.created_at = _now()
        self.ended_at: Optional[datetime] = None
        self.hints_used = 0
        self.hint_letters: list[str] = []

    def is_active(self) -> bool:
        return self.status == "active"

    def add_guess(self, user_id: int, user_name: str, word: str, tiles: list[str]):
        self.guesses.append({
            "user_id": int(user_id),
            "user_name": user_name,
            "word": word,
            "tiles": tiles,
        })
        self.attempts += 1

    def check_win(self, word: str) -> bool:
        return word.lower() == self.secret.lower()

    def finish_win(self, user_id: int, user_name: str):
        self.status = "won"
        self.winner_id = int(user_id)
        self.winner_name = user_name
        self.ended_at = _now()

    def finish_lost(self):
        self.status = "lost"
        self.ended_at = _now()

    def finish_cancelled(self):
        self.status = "cancelled"
        self.ended_at = _now()

    def remaining_attempts(self) -> int:
        return max(0, self.max_attempts - self.attempts)

    def calculate_score(self) -> int:
        """Base + attempt bonus - hint penalty (applied by caller)."""
        base = BASE_SCORE.get(self.length, 20)
        bonus = self.remaining_attempts() // ATTEMPT_BONUS_DIVISOR
        return base + bonus


# ── Active games registry ──
ACTIVE_GAMES: dict[int, WordSeekGame] = {}


def get_game(chat_id: int) -> Optional[WordSeekGame]:
    return ACTIVE_GAMES.get(int(chat_id))


def create_game(chat_id: int, length: int, starter_id: int, starter_name: str) -> WordSeekGame:
    game = WordSeekGame(chat_id, length, starter_id, starter_name)
    ACTIVE_GAMES[int(chat_id)] = game
    return game


def remove_game(chat_id: int):
    ACTIVE_GAMES.pop(int(chat_id), None)


# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE — Stats, Leaderboard, Persistence
# ══════════════════════════════════════════════════════════════════════════════
def _stats_col():
    return db["wordseek_stats"] if db is not None else None


def _games_col():
    return db["wordseek_games"] if db is not None else None


async def ensure_stats(user_id: int, username: str, first_name: str):
    col = _stats_col()
    if col is None:
        return
    await col.update_one(
        {"_id": int(user_id)},
        {
            "$set": {
                "username": username or "",
                "first_name": first_name or "",
                "updated_at": _now(),
            },
            "$setOnInsert": {
                "_id": int(user_id),
                "games_played": 0,
                "games_won": 0,
                "games_lost": 0,
                "total_guesses": 0,
                "points": 0,
                "win_streak": 0,
                "best_streak": 0,
                "avg_guesses_per_win": 0.0,
                "wins_guesses_sum": 0,
                "last_game": None,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def record_win(user_id: int, username: str, first_name: str, points: int, guesses_used: int):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, username, first_name)

    doc = await col.find_one({"_id": int(user_id)}) or {}
    new_streak = int(doc.get("win_streak", 0)) + 1
    best_streak = max(new_streak, int(doc.get("best_streak", 0)))
    new_wins = int(doc.get("games_won", 0)) + 1
    sum_guesses = int(doc.get("wins_guesses_sum", 0)) + int(guesses_used)
    avg = sum_guesses / new_wins if new_wins > 0 else 0.0

    await col.update_one(
        {"_id": int(user_id)},
        {
            "$inc": {
                "games_played": 1,
                "games_won": 1,
                "total_guesses": int(guesses_used),
                "points": int(points),
            },
            "$set": {
                "win_streak": new_streak,
                "best_streak": best_streak,
                "wins_guesses_sum": sum_guesses,
                "avg_guesses_per_win": avg,
                "last_game": _now(),
                "updated_at": _now(),
                "username": username or "",
                "first_name": first_name or "",
            },
        },
    )


async def record_loss(user_id: int, username: str, first_name: str, guesses_used: int = 0):
    col = _stats_col()
    if col is None:
        return
    await ensure_stats(user_id, username, first_name)
    await col.update_one(
        {"_id": int(user_id)},
        {
            "$inc": {
                "games_played": 1,
                "games_lost": 1,
                "total_guesses": int(guesses_used),
            },
            "$set": {
                "win_streak": 0,
                "last_game": _now(),
                "updated_at": _now(),
            },
        },
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
    return await col.find().sort([
        ("points", -1),
        ("games_won", -1),
        ("avg_guesses_per_win", 1),
    ]).limit(limit).to_list(length=limit)


async def persist_game(game: WordSeekGame):
    col = _games_col()
    if col is None:
        return
    await col.update_one(
        {"_id": int(game.chat_id)},
        {
            "$set": {
                "chat_id": int(game.chat_id),
                "length": int(game.length),
                "starter_id": int(game.starter_id),
                "starter_name": game.starter_name,
                "secret": game.secret,
                "max_attempts": int(game.max_attempts),
                "attempts": int(game.attempts),
                "guesses": game.guesses,
                "status": game.status,
                "winner_id": game.winner_id,
                "winner_name": game.winner_name,
                "hints_used": int(game.hints_used),
                "hint_letters": game.hint_letters,
                "created_at": game.created_at,
                "updated_at": _now(),
            }
        },
        upsert=True,
    )


async def remove_persisted_game(chat_id: int):
    col = _games_col()
    if col is None:
        return
    await col.delete_one({"_id": int(chat_id)})


async def recover_active_games() -> int:
    """On bot restart, restore active games from DB."""
    col = _games_col()
    if col is None:
        return 0
    count = 0
    try:
        async for doc in col.find({"status": "active"}):
            try:
                game = WordSeekGame(
                    chat_id=doc["chat_id"],
                    length=doc["length"],
                    starter_id=doc["starter_id"],
                    starter_name=doc.get("starter_name", ""),
                )
                game.secret = doc.get("secret", game.secret)
                game.max_attempts = int(doc.get("max_attempts", MAX_ATTEMPTS))
                game.attempts = int(doc.get("attempts", 0))
                game.guesses = doc.get("guesses", [])
                game.hint_letters = doc.get("hint_letters", [])
                game.hints_used = int(doc.get("hints_used", 0))
                ACTIVE_GAMES[int(doc["chat_id"])] = game
                count += 1
            except Exception as e:
                print(f"[WordSeek recovery] {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"[WordSeek recovery outer] {type(e).__name__}: {e}", flush=True)
    return count
