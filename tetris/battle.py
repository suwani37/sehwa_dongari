"""Two-board battle clock, garbage queues, cancellation, and results."""
from collections import deque
from dataclasses import dataclass, field
import random

from tetris.ai import AIController
from tetris.attacks import attack_lines
from tetris.preferences import PlayerSettings
from tetris.state import GameState


@dataclass
class GarbagePacket:
    count: int
    hole: int
    ready_at: float


@dataclass
class BattleSide:
    state: GameState
    incoming: deque = field(default_factory=deque)
    combo: int = 0
    sent: int = 0
    received: int = 0
    last_sent: int = 0
    sent_notice: float = 0.0

    @property
    def pending(self):
        return sum(packet.count for packet in self.incoming)

    def cancel(self, count):
        while count and self.incoming:
            packet = self.incoming[0]
            cancelled = min(count, packet.count)
            packet.count -= cancelled
            count -= cancelled
            if packet.count == 0:
                self.incoming.popleft()
        return count


class BattleMatch:
    def __init__(self, preferences=None, difficulty="normal", seed=None):
        seed = random.SystemRandom().randrange(2**32) if seed is None else seed
        self.difficulty = difficulty
        self.player = GameState(random.Random(seed), preferences or PlayerSettings(),
                                mode="battle", defer_spawn=True)
        self.ai = GameState(random.Random(seed), PlayerSettings(), mode="battle", defer_spawn=True)
        self.sides = (BattleSide(self.player), BattleSide(self.ai))
        self.controller = AIController(difficulty, random.Random(seed ^ 0xA11CE))
        self.rng = random.Random(seed ^ 0xB4771E)
        self.last_holes = [None, None]
        self.time = 0.0
        self.paused = False
        self.finished = False
        self.winner = None

    def set_paused(self, paused):
        if not self.finished:
            self.paused = paused
            self.player.paused = self.ai.paused = paused

    def enqueue(self, target, count):
        if count <= 0:
            return
        choices = [x for x in range(self.sides[target].state.board.columns)
                   if x != self.last_holes[target]]
        hole = self.rng.choice(choices)
        self.last_holes[target] = hole
        self.sides[target].incoming.append(GarbagePacket(count, hole, self.time + 1.0))

    def _rise_ready(self, side):
        remaining = 4
        while remaining and side.incoming:
            packet = side.incoming[0]
            if packet.ready_at > self.time + 1e-9:
                break
            count = min(remaining, packet.count)
            overflow = side.state.board.add_garbage(count, packet.hole)
            packet.count -= count
            remaining -= count
            side.received += count
            if not packet.count:
                side.incoming.popleft()
            if overflow:
                side.state.game_over = True
                break

    def resolve_locks(self):
        """Resolve both sides together, avoiding human/AI update-order advantage."""
        outgoing = [0, 0]
        no_clear = [False, False]
        for index, side in enumerate(self.sides):
            while side.state.lock_events:
                event = side.state.lock_events.popleft()
                if event.lines:
                    side.combo += 1
                else:
                    side.combo = 0
                    no_clear[index] = True
                outgoing[index] += attack_lines(event, side.combo)
            outgoing[index] = side.cancel(outgoing[index])
        simultaneous = min(outgoing)
        outgoing = [value - simultaneous for value in outgoing]
        for index, count in enumerate(outgoing):
            if count:
                self.enqueue(1 - index, count)
                side = self.sides[index]
                side.sent += count
                side.last_sent = count
                side.sent_notice = 1.5
        for index, side in enumerate(self.sides):
            if no_clear[index] and not side.state.game_over:
                self._rise_ready(side)
            if side.state.awaiting_spawn and not side.state.game_over:
                side.state._spawn_next()
        lost = [side.state.game_over for side in self.sides]
        if any(lost):
            self.finished = True
            self.winner = "draw" if all(lost) else "ai" if lost[0] else "player"
            self.player.paused = self.ai.paused = True

    def tick(self, elapsed, soft_drop=False):
        if self.paused or self.finished:
            return
        elapsed = max(0.0, elapsed)
        self.time += elapsed
        for side in self.sides:
            side.sent_notice = max(0.0, side.sent_notice - elapsed)
        self.controller.update(elapsed, self.ai)
        self.player.tick(elapsed, soft_drop=soft_drop)
        self.ai.tick(elapsed)
        self.resolve_locks()
