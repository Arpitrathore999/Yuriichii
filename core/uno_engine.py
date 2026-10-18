"""Server-authoritative classic UNO rules engine (2-6 players)."""
from dataclasses import dataclass, field
from random import shuffle
from typing import Optional
COLORS = ('red','yellow','green','blue')
@dataclass
class Card:
    color: Optional[str]
    value: str
    def as_dict(self): return {'color': self.color, 'value': self.value}
def make_deck():
    d=[]
    for c in COLORS:
        d.append(Card(c,'0'))
        for v in [str(i) for i in range(1,10)]+['skip','reverse','draw2']:
            d.extend([Card(c,v),Card(c,v)])
    d += [Card(None,'wild') for _ in range(4)] + [Card(None,'wild4') for _ in range(4)]
    shuffle(d); return d
@dataclass
class Game:
    player_ids: list[str]
    names: dict[str,str] = field(default_factory=dict)
    hands: dict[str,list[Card]] = field(default_factory=dict)
    deck: list[Card] = field(default_factory=make_deck)
    discard: list[Card] = field(default_factory=list)
    turn: int = 0
    direction: int = 1
    current_color: str = 'red'
    status: str = 'lobby'
    winner: Optional[str] = None
    uno_pending: set[str] = field(default_factory=set)
    last_action: str = 'Waiting for players.'
    def add_player(self,pid,name):
        if self.status!='lobby': raise ValueError('Game already started')
        if pid in self.player_ids: return
        if len(self.player_ids)>=6: raise ValueError('Lobby is full (6 players max).')
        self.player_ids.append(pid); self.names[pid]=name
    def start(self):
        if not 2<=len(self.player_ids)<=6: raise ValueError('UNO needs 2–6 players.')
        self.deck=make_deck(); self.hands={p:[self.deck.pop() for _ in range(7)] for p in self.player_ids}; self.discard=[]
        while True:
            c=self.deck.pop()
            if c.color is not None and c.value.isdigit(): self.discard.append(c); self.current_color=c.color; break
            self.deck.insert(0,c)
        self.turn=0; self.direction=1; self.status='playing'; self.winner=None; self.last_action='Game started.'
    @property
    def current_player(self): return self.player_ids[self.turn] if self.player_ids else None
    def _refill(self):
        if not self.deck and len(self.discard)>1:
            top=self.discard.pop(); self.deck=self.discard; self.discard=[top]; shuffle(self.deck)
    def _draw(self,pid,n=1):
        for _ in range(n):
            self._refill()
            if self.deck: self.hands[pid].append(self.deck.pop())
    def can_play(self,c):
        top=self.discard[-1]
        return c.color is None or c.color==self.current_color or c.value==top.value
    def play(self,pid,index,color=None):
        if self.status!='playing': raise ValueError('Game is not running.')
        if pid!=self.current_player: raise ValueError('It is not your turn.')
        hand=self.hands[pid]
        if not 0<=index<len(hand): raise ValueError('Invalid card.')
        c=hand[index]
        if not self.can_play(c): raise ValueError('That card does not match the current colour or symbol.')
        if c.value=='wild4' and any(card.color==self.current_color for i,card in enumerate(hand) if i!=index):
            raise ValueError('Wild Draw Four can only be played when you have no card matching the current colour.')
        if c.color is None and color not in COLORS: raise ValueError('Choose a colour for a wild card.')
        if c.color is not None and color is not None: raise ValueError('Only wild cards can choose a colour.')
        hand.pop(index); self.discard.append(c); self.current_color=color if c.color is None else c.color
        self.uno_pending.discard(pid)
        if not hand:
            self.status='finished'; self.winner=pid; self.last_action=f'{self.names.get(pid,pid)} won!'; return
        step=self.direction; n=len(self.player_ids)
        if c.value=='reverse':
            self.direction*=-1; step=self.direction
            if n==2: step=2*self.direction
        elif c.value=='skip': step=2*self.direction
        elif c.value in ('draw2','wild4'):
            target=self.player_ids[(self.turn+self.direction)%n]
            self._draw(target,2 if c.value=='draw2' else 4); step=2*self.direction
        self.turn=(self.turn+step)%n
        self.last_action=f'{self.names.get(pid,pid)} played {c.value}.'
    def draw(self,pid):
        if self.status!='playing' or pid!=self.current_player: raise ValueError('It is not your turn.')
        self._draw(pid,1); self.last_action=f'{self.names.get(pid,pid)} drew a card.'
        # Classic simplified rule: drawing ends the turn; drawn card is not immediately played.
        self.turn=(self.turn+self.direction)%len(self.player_ids)
    def call_uno(self,pid):
        if pid not in self.hands or len(self.hands[pid])!=1: raise ValueError('UNO can be called when you have one card.')
        self.uno_pending.add(pid); self.last_action=f'{self.names.get(pid,pid)} called UNO!'
    def state_for(self,pid):
        return {'status':self.status,'players':[{'id':p,'name':self.names.get(p,p),'count':len(self.hands.get(p,[])),'is_turn':p==self.current_player,'is_me':p==pid} for p in self.player_ids], 'hand':[c.as_dict() for c in self.hands.get(pid,[])], 'top':self.discard[-1].as_dict() if self.discard else None,'current_color':self.current_color,'draw_count':len(self.deck),'direction':self.direction,'current_player':self.current_player,'winner':self.winner,'last_action':self.last_action,'uno_called':pid in self.uno_pending}
