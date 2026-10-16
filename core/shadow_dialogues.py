# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/shadow_dialogues.py — 🎭 Shadow Syndicate Dialogue Engine
#  Character dialogues, scenes, variations
# --------------------------------------------------------------------------------

import random

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 1 — MISSION START
# ══════════════════════════════════════════════════════════════════════════════
MISSION_START = [
    "🌑 <b>SHADOW SYNDICATE: OPERATION NIGHTFALL</b>\n\n"
    "The city has gone silent.\n"
    "A classified artifact has disappeared from the Monarch's vault.\n"
    "Four people know the truth.\n"
    "Only one of them is hiding the real secret.\n\n"
    "The investigation begins now...",

    "🌒 <b>OPERATION NIGHTFALL — PHASE 1</b>\n\n"
    "Midnight. The vault is empty.\n"
    "No alarms. No witnesses. No escape route.\n"
    "Someone in this room knows exactly what happened.\n\n"
    "Let the interrogation begin...",

    "🌃 <b>SHADOW SYNDICATE ACTIVATED</b>\n\n"
    "The artifact is gone.\n"
    "Four suspects. One thief. Zero mercy.\n"
    "The Monarch has summoned everyone to the war room.\n\n"
    "Trust no one.",
]

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 2 — MONARCH DIALOGUES
# ══════════════════════════════════════════════════════════════════════════════
MONARCH_LINES = [
    "Someone inside my own circle betrayed me. I want answers, not excuses.",
    "I built this empire on loyalty. Someone forgot what that word means.",
    "The vault was sealed. The guards were loyal. Yet here we are.",
    "I did not summon you here for comfort. I summoned you for a verdict.",
    "Every minute we waste, the thief gains another step.",
    "My patience has a limit. It is approaching fast.",
    "You were all trusted. Now only one of you is innocent.",
    "I don't want theories. I want the truth. Now.",
    "The artifact is priceless. Your loyalty is not. Prove it.",
    "Someone is going to pay for this. Make sure it's not you.",
]

MONARCH_FOLLOWUP = [
    "Strategist, the fate of this operation is in your hands. Choose carefully.",
    "Strategist, I'm watching. Do not disappoint me.",
    "Strategist, one name. Say it.",
    "Strategist, the entire Syndicate is waiting on your judgment.",
    "Strategist, you know what's at stake. Decide.",
    "Strategist, this is your moment. Don't waste it.",
]

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 3 — STRATEGIST DIALOGUES
# ══════════════════════════════════════════════════════════════════════════════
STRATEGIST_LINES = [
    "Your Majesty, accusations without evidence are dangerous. Give me a moment. I will find the truth.",
    "Someone here is lying. The question is who can keep the lie alive.",
    "I have two suspects and one decision. I won't waste this opportunity.",
    "If I choose wrong, the real culprit walks away.",
    "Three people claim innocence. That's three too many.",
    "The Phantom is clever. But cleverness leaves patterns.",
    "I've seen this before. The quiet one. Always the quiet one.",
    "Everyone here has an alibi. Only one of them is real.",
    "The truth doesn't hide. It waits to be discovered.",
    "I'll need absolute focus. One wrong word and we lose.",
    "The Phantom made a mistake tonight. I intend to find it.",
    "Patience, Your Majesty. A rushed verdict is a lost verdict.",
]

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 4 — SENTINEL & PHANTOM EXCHANGES
# ══════════════════════════════════════════════════════════════════════════════
INTERROGATION_EXCHANGES = [
    (
        "🛡️ THE SENTINEL:\n\"Nobody leaves this room until the missing artifact is found.\"",
        "🃏 THE PHANTOM:\n\"Big words for someone who hasn't caught anyone yet.\"",
        "🛡️ THE SENTINEL:\n\"Keep joking. One mistake is all I need.\"",
        "🃏 THE PHANTOM:\n\"Then I suggest you stop looking at everyone except the person standing right beside you.\"",
    ),
    (
        "🛡️ THE SENTINEL:\n\"Two suspects. Both with shifty eyes.\"",
        "🃏 THE PHANTOM:\n\"Maybe your eyes are the shifty ones.\"",
        "🛡️ THE SENTINEL:\n\"Careful. I don't need evidence to make you disappear.\"",
        "🃏 THE PHANTOM:\n\"But you do need it to catch the real thief, don't you?\"",
    ),
    (
        "🛡️ THE SENTINEL:\n\"The vault was breached from inside. That narrows it down.\"",
        "🃏 THE PHANTOM:\n\"Or maybe you breached it yourself and blamed the room.\"",
        "🛡️ THE SENTINEL:\n\"That's a bold accusation.\"",
        "🃏 THE PHANTOM:\n\"Bold times call for bold accusations.\"",
    ),
    (
        "🛡️ THE SENTINEL:\n\"I've already checked everyone's past. All clean. Suspiciously clean.\"",
        "🃏 THE PHANTOM:\n\"Maybe you're just a bad reader.\"",
        "🛡️ THE SENTINEL:\n\"Or maybe someone paid to erase their record.\"",
        "🃏 THE PHANTOM:\n\"Now you're thinking like a detective. Finally.\"",
    ),
    (
        "🛡️ THE SENTINEL:\n\"Whoever did this had inside access.\"",
        "🃏 THE PHANTOM:\n\"Or outside help. Or both. Or neither. Let's see.\"",
        "🛡️ THE SENTINEL:\n\"You're enjoying this.\"",
        "🃏 THE PHANTOM:\n\"Only because I'm innocent. The guilty don't smile.\"",
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 5 — CROSS CHARACTER EXCHANGES (4-way)
# ══════════════════════════════════════════════════════════════════════════════
CROSS_EXCHANGES = [
    (
        "👑 THE MONARCH:\n\"Sentinel, report. What have you discovered?\"",
        "🛡️ THE SENTINEL:\n\"Two suspects. No confirmed evidence.\"",
        "🧠 THE STRATEGIST:\n\"Then evidence is not what we lack. We lack the courage to make a decision.\"",
        "🃏 THE PHANTOM:\n\"Or perhaps you are all searching for a crime that never happened.\"",
    ),
    (
        "👑 THE MONARCH:\n\"Strategist, have you narrowed it down?\"",
        "🧠 THE STRATEGIST:\n\"Two names remain. One will be cleared. One will fall.\"",
        "🛡️ THE SENTINEL:\n\"Say the word and I'll secure the room.\"",
        "🃏 THE PHANTOM:\n\"So dramatic. The truth is always less cinematic.\"",
    ),
    (
        "👑 THE MONARCH:\n\"I want this resolved before sunrise.\"",
        "🛡️ THE SENTINEL:\n\"Understood, Your Majesty.\"",
        "🧠 THE STRATEGIST:\n\"Rushing won't help. But pressure creates cracks.\"",
        "🃏 THE PHANTOM:\n\"Then let's hope the cracks show on someone else.\"",
    ),
    (
        "🧠 THE STRATEGIST:\n\"Something doesn't add up. The timeline is off.\"",
        "🛡️ THE SENTINEL:\n\"Meaning?\"",
        "🧠 THE STRATEGIST:\n\"Meaning the thief knew the vault's timing. This was planned.\"",
        "🃏 THE PHANTOM:\n\"Or the vault was always meant to be opened.\"",
    ),
    (
        "👑 THE MONARCH:\n\"Enough games. Someone in this room is guilty.\"",
        "🃏 THE PHANTOM:\n\"Everyone in this room is guilty of something. The question is what.\"",
        "🛡️ THE SENTINEL:\n\"Then we'll start with you.\"",
        "🧠 THE STRATEGIST:\n\"No. We start with facts. Patience, Sentinel.\"",
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 6 — FINAL INTERROGATION
# ══════════════════════════════════════════════════════════════════════════════
FINAL_INTERROGATION = [
    "⚠️ <b>FINAL DECISION</b>\n\n"
    "The evidence has been presented.\n"
    "The Monarch awaits an answer.\n"
    "The Sentinel is ready to act.\n"
    "The Phantom is running out of time.\n\n"
    "Strategist, make your choice.",

    "⚖️ <b>THE VERDICT APPROACHES</b>\n\n"
    "The vault remains empty.\n"
    "The room grows colder.\n"
    "One name will change everything.\n\n"
    "Strategist, the Syndicate awaits your accusation.",

    "🎭 <b>MOMENT OF TRUTH</b>\n\n"
    "Three faces. One lie.\n"
    "The Monarch taps the table.\n"
    "Time is no longer your ally.\n\n"
    "Strategist, choose now.",
]

# ══════════════════════════════════════════════════════════════════════════════
#  SCENE 7 — REVEAL (CORRECT / WRONG)
# ══════════════════════════════════════════════════════════════════════════════
REVEAL_CORRECT = [
    "⚖️ <b>CASE CLOSED</b>\n\n"
    "The Strategist saw through the deception.\n"
    "The Phantom's identity has been exposed.\n"
    "The Monarch's authority remains unchallenged.\n\n"
    "The right suspect was chosen.",

    "🎯 <b>PRECISION STRIKE</b>\n\n"
    "The accusation landed perfectly.\n"
    "The Phantom's mask fell in front of everyone.\n"
    "The artifact will return to its vault.\n\n"
    "Justice has been served.",
]

REVEAL_WRONG = [
    "💀 <b>OPERATION COMPROMISED</b>\n\n"
    "The Strategist accused the wrong person.\n"
    "The Phantom slips through the investigation.\n"
    "The real culprit escapes while the Strategist loses the entire reward.\n\n"
    "The city will remember this mistake.",

    "🩸 <b>THE PHANTOM WALKS FREE</b>\n\n"
    "Wrong suspect. Wrong verdict.\n"
    "The Sentinel was innocent.\n"
    "The Phantom's laughter echoes through the empty vault.\n\n"
    "The Syndicate has failed tonight.",
]

# ══════════════════════════════════════════════════════════════════════════════
#  RANDOM HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def get_mission_start() -> str:
    return random.choice(MISSION_START)


def get_monarch_line() -> str:
    return random.choice(MONARCH_LINES)


def get_monarch_followup() -> str:
    return random.choice(MONARCH_FOLLOWUP)


def get_strategist_line() -> str:
    return random.choice(STRATEGIST_LINES)


def get_interrogation() -> tuple:
    return random.choice(INTERROGATION_EXCHANGES)


def get_cross_exchange() -> tuple:
    return random.choice(CROSS_EXCHANGES)


def get_final_interrogation() -> str:
    return random.choice(FINAL_INTERROGATION)


def get_reveal(correct: bool) -> str:
    return random.choice(REVEAL_CORRECT if correct else REVEAL_WRONG)
