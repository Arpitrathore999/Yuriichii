"""Small, framework-independent UNO rules engine for Elara's UNO Mini App.

This engine is a starting point for server-authoritative multiplayer. Do not trust
client-provided hands or turns in a public deployment; store Game objects server-side.
"""
from dataclasses import dataclass, field
from random import shuffle, choice
from typing import Optional

COLORS = ("red", "yellow", "green", "blue")

@dataclass
class Card:
    color: Optional[str]
    value: str  # 0-9, skip, reverse, draw2, wild, wild4

    def as_dict(self):
        return {"color": self.color, "value": self.value}

@dataclass
class Game:
    player_ids: list[str]
    hands: dict[str, list[Card]] = field(default_factory=dict)
    deck: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    turn: int = 0
    direction: int = 1
    current_color: Optional[str] = None
    status: str = "lobby"
    winner: Optional[str] = None

    @classmethod
    def create(cls, player_ids: list[str]):
        if not 2 <= len(player_ids) <= 6:
            raise ValueError("UNO needs 2–6 players")
        game = cls(player_ids=list(player_ids))
        game.deck = _make_deck()
        shuffle(game.deck)
        game.hands = {pid: [game.deck.pop() for _ in range(7)] for pid in player_ids}
        # First discard must be a number card to keep opening effects simple.
        idx = next((i for i, c in enumerate(game.deck) if c.value.isdigit()), None)
        if idx is None:
            raise RuntimeError("Could not find opening card")
        game.discard.append(game.deck.pop(idx))
        game.current_color = game.discard[-1].color
        game.status = "playing"
        return game

    def playable(self, player_id: str):
        if self.status != "playing" or self.player_ids[self.turn] != player_id:
            return []
        top = self.discard[-1]
        return [i for i, c in enumerate(self.hands[player_id])
                if c.value in ("wild", "wild4") or c.color == self.current_color or c.value == top.value]

    def play(self, player_id: str, card_index: int, chosen_color: Optional[str] = None):
        if self.status != "playing" or self.player_ids[self.turn] != player_id:
            raise ValueError("Not your turn")
        hand = self.hands[player_id]
        if not 0 <= card_index < len(hand):
            raise ValueError("Invalid card index")
        card = hand[card_index]
        if card.value not in ("wild", "wild4") and not (
            card.color == self.current_color or card.value == self.discard[-1].value
        ):
            raise ValueError("Card does not match")
        if card.value in ("wild", "wild4"):
            if chosen_color not in COLORS:
                raise ValueError("Choose a valid colour")
            self.current_color = chosen_color
        else:
            self.current_color = card.color
        hand.pop(card_index)
        self.discard.append(card)
        if not hand:
            self.winner, self.status = player_id, "finished"
            return {"winner": player_id, "status": self.status}
        step = self.direction
        if card.value == "reverse":
            self.direction *= -1
            if len(self.player_ids) == 2:
                step = 2 * self.direction
            else:
                step = self.direction
        elif card.value == "skip":
            step = 2 * self.direction
        elif card.value in ("draw2", "wild4"):
            target = self.player_ids[(self.turn + self.direction) % len(self.player_ids)]
            count = 2 if card.value == "draw2" else 4
            self._draw(target, count)
            step = 2 * self.direction
        self.turn = (self.turn + step) % len(self.player_ids)
        return {"winner": None, "status": self.status, "next_player": self.player_ids[self.turn]}

    def draw(self, player_id: str, count: int = 1):
        if self.status != "playing" or self.player_ids[self.turn] != player_id:
            raise ValueError("Not your turn")
        self._draw(player_id, count)
        self.turn = (self.turn + self.direction) % len(self.player_ids)
        return self.player_ids[self.turn]

    def _draw(self, player_id: str, count: int):
        for _ in range(count):
            if not self.deck:
                if len(self.discard) <= 1:
                    break
                top = self.discard.pop()
                self.deck, self.discard = self.discard, [top]
                shuffle(self.deck)
            if self.deck:
                self.hands[player_id].append(self.deck.pop())

def _make_deck():
    deck = []
    for color in COLORS:
        deck.append(Card(color, "0"))
        for value in [str(n) for n in range(1, 10)] + ["skip", "reverse", "draw2"]:
            deck.extend([Card(color, value), Card(color, value)])
    deck.extend([Card(None, "wild") for _ in range(4)])
    deck.extend([Card(None, "wild4") for _ in range(4)])
    return deck
