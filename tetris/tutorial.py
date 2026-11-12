"""Independent, deterministic practice missions using the real game rules."""
from dataclasses import dataclass
import random

from tetris.piece import Piece
from tetris.preferences import PlayerSettings
from tetris.state import GameState


@dataclass(frozen=True)
class Lesson:
    action: str
    target: int
    controls: tuple[str, ...]


LESSONS = (
    Lesson("left", 2, ("left", "right")),
    Lesson("right", 2, ("left", "right")),
    Lesson("rotate_cw", 1, ("rotate_cw", "rotate_ccw")),
    Lesson("rotate_ccw", 1, ("rotate_cw", "rotate_ccw")),
    Lesson("soft_drop", 3, ("soft_drop",)),
    Lesson("hard_drop", 1, ("hard_drop",)),
    Lesson("hold", 1, ("hold",)),
    Lesson("clear", 1, ("left", "right", "rotate_cw", "hard_drop")),
)


class TutorialSession:
    def __init__(self, preferences=None, lesson_index=0):
        self.preferences = preferences or PlayerSettings()
        self.index = lesson_index
        self.finished = False
        self.retry()

    @property
    def lesson(self):
        return LESSONS[self.index]

    @property
    def complete(self):
        return self.progress >= self.lesson.target

    @property
    def active(self):
        return self.state.active

    @property
    def needs_retry(self):
        return not self.complete and self.active is None and not self.state.clearing_rows

    def retry(self):
        self.state = GameState(rng=random.Random(0), timing=self.preferences, defer_spawn=True)
        self.state.active = Piece("T", 3, 5)
        self.state.next_queue[0] = "I"
        if self.lesson.action == "clear":
            self.state.active = Piece("I", 3, 5)
            self.state.board.grid[-1] = [None if 3 <= x <= 6 else "G" for x in range(10)]
        self.progress = 0
        self.soft_timer = 0.0

    def advance(self):
        if not self.complete or self.finished:
            return False
        if self.index == len(LESSONS) - 1:
            self.finished = True
        else:
            self.index += 1
            self.retry()
        return True

    def _record(self, action, amount=1):
        if self.lesson.action == action:
            self.progress = min(self.lesson.target, self.progress + amount)

    def move(self, dx, dy):
        if self.complete or self.finished:
            return False
        if self.state.move(dx, dy):
            if dx:
                self._record("left" if dx < 0 else "right", abs(dx))
            return True
        return False

    def perform(self, action):
        if self.complete or self.finished or self.active is None:
            return False
        if action in ("left", "right"):
            return self.move(-1 if action == "left" else 1, 0)
        # The clear mission permits positioning, but keeps its I piece available.
        allowed = self.lesson.controls
        if action not in allowed:
            return False
        if action.startswith("rotate_"):
            old = self.active
            valid = self.state.rotate(1 if action == "rotate_cw" else -1)
            if valid and old != self.active:
                self._record(action)
                return True
        elif action == "soft_drop" and self.state.step_down(soft=True):
            self._record(action)
            return True
        elif action == "hard_drop":
            self.state.hard_drop()
            self._record(action)
            return True
        elif action == "hold" and self.state.hold():
            self._record(action)
            return True
        return False

    def tick(self, elapsed, soft_drop=False):
        elapsed = max(0.0, elapsed)
        if self.finished:
            return
        # Only animate an earned clear; practice has no gravity or lock deadline.
        if self.state.clearing_rows:
            self.state.tick(elapsed)
            if self.state.lines:
                self._record("clear")
            return
        self.state.clear_notice_timer = max(0.0, self.state.clear_notice_timer - elapsed)
        self.state.perfect_clear_timer = max(0.0, self.state.perfect_clear_timer - elapsed)
        if self.complete or not soft_drop or self.lesson.action != "soft_drop":
            self.soft_timer = 0.0
            return
        self.soft_timer += elapsed
        interval = self.preferences.soft_drop_ms / 1000.0
        while self.soft_timer + 1e-9 >= interval:
            self.soft_timer = max(0.0, self.soft_timer - interval)
            if not self.perform("soft_drop"):
                self.soft_timer = 0.0
                break
