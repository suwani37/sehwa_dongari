"""Tetris rules and timers independent of Pygame."""

from collections import deque
import random

from tetris import settings
from tetris.board import Board
from tetris.attacks import LockEvent
from tetris.piece import Piece, SevenBag, kick_offsets, spawn_piece
from tetris.preferences import PlayerSettings

LINE_POINTS = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
T_SPIN_POINTS = {0: 400, 1: 800, 2: 1200, 3: 1600}
MINI_T_SPIN_POINTS = {0: 100, 1: 200, 2: 400}
PERFECT_CLEAR_POINTS = {1: 800, 2: 1200, 3: 1600, 4: 2000}
BACK_TO_BACK_TETRIS_PERFECT_CLEAR = 3200


class GameState:
    def __init__(self, rng: random.Random | None = None,
                 timing: PlayerSettings | None = None, mode: str = "marathon", defer_spawn: bool = False) -> None:
        if mode not in ("sprint40", "blitz", "marathon", "battle"):
            raise ValueError(mode)
        self.mode = mode
        self.defer_spawn = defer_spawn
        self.awaiting_spawn = False
        self.spawn_serial = 0
        self.lock_events = deque()
        self.elapsed_time = 0.0
        self.finished = False
        self.finish_reason = ""
        self.timing = timing or PlayerSettings()
        self.board = Board(settings.BOARD_COLUMNS, settings.BOARD_ROWS)
        self.bag = SevenBag(rng)
        self.next_queue: deque[str] = deque()
        self.hold_kind: str | None = None
        self.can_hold = True
        self.game_over = False
        self.paused = False
        self.lines = 0
        self.score = 0
        self.back_to_back = False
        self.last_clear = ""
        self.last_clear_type = ""
        self.last_clear_perfect = False
        self.clear_notice_timer = 0.0
        self.clearing_rows: tuple[int, ...] = ()
        self.clear_timer = 0.0
        self.perfect_clear_timer = 0.0
        self._pending_spin = "none"
        self.active: Piece | None = None
        self.gravity_timer = 0.0
        self.soft_drop_timer = 0.0
        self.soft_dropping = False
        self.lock_timer = 0.0
        self.lock_resets = 0
        self.last_rotation = False
        self.last_kick_index = None
        self._fill_queue()
        self._spawn_next()

    @property
    def ended(self) -> bool:
        return self.game_over or self.finished

    @property
    def time_remaining(self) -> float:
        return max(0.0, 120.0 - self.elapsed_time)

    @property
    def level(self) -> int:
        return self.lines // settings.LINES_PER_LEVEL + 1

    @property
    def gravity_interval(self) -> float:
        if self.mode == "battle":
            return 0.6
        return max(0.05, 0.6 * 0.82 ** (self.level - 1))

    @property
    def ghost(self) -> Piece | None:
        if self.active is None:
            return None
        piece = self.active
        while self.board.can_place(piece.moved(0, 1)):
            piece = piece.moved(0, 1)
        return piece

    def _fill_queue(self) -> None:
        while len(self.next_queue) < 5:
            self.next_queue.append(self.bag.draw())

    def _spawn(self, kind: str) -> None:
        self.awaiting_spawn = False
        self.spawn_serial += 1
        self.active = spawn_piece(kind, self.board.columns)
        self.gravity_timer = 0.0
        self.soft_drop_timer = 0.0
        self.soft_dropping = False
        self.lock_timer = 0.0
        self.lock_resets = 0
        self.last_rotation = False
        self.last_kick_index = None
        if not self.board.can_place(self.active):
            self.game_over = True

    def _spawn_next(self) -> None:
        kind = self.next_queue.popleft()
        self._fill_queue()
        self._spawn(kind)

    def is_grounded(self) -> bool:
        return self.active is not None and not self.board.can_place(self.active.moved(0, 1))

    def _after_manipulation(self, was_grounded: bool) -> None:
        if was_grounded and self.lock_resets < settings.MAX_LOCK_RESETS:
            self.lock_timer = 0.0
            self.lock_resets += 1
        elif not self.is_grounded():
            self.lock_timer = 0.0

    def move(self, dx: int, dy: int) -> bool:
        if self.ended or self.paused or self.active is None:
            return False
        candidate = self.active.moved(dx, dy)
        if not self.board.can_place(candidate):
            return False
        was_grounded = self.is_grounded()
        self.active = candidate
        self.last_rotation = False
        self.last_kick_index = None
        if dx:
            self._after_manipulation(was_grounded)
        elif not self.is_grounded():
            self.lock_timer = 0.0
        return True

    def rotate(self, direction: int = 1) -> bool:
        if self.ended or self.paused or self.active is None:
            return False
        old = self.active
        rotated = old.rotated(direction)
        if old.kind == "O":
            return True
        for kick_index, (dx, dy) in enumerate(kick_offsets(old.kind, old.rotation, rotated.rotation)):
            candidate = rotated.moved(dx, dy)
            if self.board.can_place(candidate):
                was_grounded = self.is_grounded()
                self.active = candidate
                self.last_rotation = True
                self.last_kick_index = kick_index
                self._after_manipulation(was_grounded)
                return True
        return False

    def step_down(self, soft: bool = False) -> bool:
        if self.move(0, 1):
            if soft:
                self.score += 1
            return True
        return False

    def hard_drop(self) -> None:
        if self.ended or self.paused or self.active is None:
            return
        distance = 0
        while self.board.can_place(self.active.moved(0, 1)):
            self.active = self.active.moved(0, 1)
            distance += 1
        if distance:
            self.last_rotation = False
            self.last_kick_index = None
        self.score += distance * 2
        self._lock_active()

    def _spin_type(self) -> str:
        piece = self.active
        if piece is None or piece.kind != "T" or not self.last_rotation:
            return "none"
        cx, cy = piece.x + 1, piece.y + 1
        corners = ((cx - 1, cy - 1), (cx + 1, cy - 1),
                   (cx - 1, cy + 1), (cx + 1, cy + 1))
        occupied = [self.board.is_occupied(x, y) for x, y in corners]
        if sum(occupied) < 3:
            return "none"
        front = ((0, 1), (1, 3), (2, 3), (0, 2))[piece.rotation % 4]
        if all(occupied[index] for index in front) or self.last_kick_index == 4:
            return "full"
        return "mini"

    def _is_t_spin(self) -> bool:
        return self._spin_type() != "none"

    def _lock_active(self) -> None:
        assert self.active is not None
        if any(y < 0 for _, y in self.active.cells()):
            self.game_over = True
            return
        spin = self._spin_type()
        self.board.place(self.active)
        self.active = None
        rows = self.board.full_rows()
        if rows:
            self.clearing_rows = rows
            self.clear_timer = settings.LINE_CLEAR_DELAY
            self._pending_spin = spin
        else:
            self._complete_lock(0, spin)

    def _complete_lock(self, cleared: int, spin: str) -> None:
        if spin == "mini" and cleared == 3:
            spin = "full"
        level = self.level
        points = MINI_T_SPIN_POINTS if spin == "mini" else T_SPIN_POINTS if spin == "full" else LINE_POINTS
        base = points[cleared]
        difficult = cleared > 0 and (spin != "none" or cleared == 4)
        was_back_to_back = difficult and self.back_to_back
        if was_back_to_back:
            base += base // 2
        self.score += base * level
        self.lines += cleared
        perfect_clear = cleared > 0 and self.board.is_empty()
        if spin != "none":
            label = "T-SPIN MINI" if spin == "mini" else "T-SPIN"
            if cleared:
                label += " " + ("SINGLE", "DOUBLE", "TRIPLE")[cleared - 1]
        else:
            label = ("", "SINGLE", "DOUBLE", "TRIPLE", "TETRIS")[cleared]
        if label:
            self.last_clear_type = label
            self.last_clear_perfect = perfect_clear
            self.clear_notice_timer = 2.0
        if perfect_clear:
            bonus = (BACK_TO_BACK_TETRIS_PERFECT_CLEAR
                     if cleared == 4 and self.back_to_back
                     else PERFECT_CLEAR_POINTS[cleared])
            self.score += bonus * level
            self.perfect_clear_timer = settings.PERFECT_CLEAR_EFFECT_TIME
        self.last_clear = "PERFECT CLEAR" if perfect_clear else label
        if cleared:
            self.back_to_back = difficult
        self.can_hold = True
        if self.mode == "sprint40" and self.lines >= 40:
            self.finished = True
            self.finish_reason = "complete"
        if self.mode == "blitz" and self.time_remaining <= 1e-9:
            self.finished = True
            self.finish_reason = "time"
        if self.defer_spawn:
            self.lock_events.append(LockEvent(cleared, spin, perfect_clear, was_back_to_back))
        if not self.ended:
            if self.defer_spawn:
                self.awaiting_spawn = True
            else:
                self._spawn_next()

    def hold(self) -> bool:
        if self.ended or self.paused or self.active is None or not self.can_hold:
            return False
        current_kind = self.active.kind
        if self.hold_kind is None:
            self.hold_kind = current_kind
            self._spawn_next()
        else:
            swap_kind = self.hold_kind
            self.hold_kind = current_kind
            self._spawn(swap_kind)
        self.can_hold = False
        return True

    def tick(self, elapsed: float, soft_drop: bool = False) -> None:
        if self.ended or self.paused:
            return
        elapsed = max(0.0, elapsed)
        if self.mode == "blitz":
            elapsed = min(elapsed, self.time_remaining)
        self.elapsed_time += elapsed
        self._tick_board(elapsed, soft_drop)
        if self.mode == "blitz" and self.time_remaining <= 1e-9:
            self.finished = True
            self.finish_reason = "time"
            # A piece locked before the deadline keeps its earned clear score.
            if self.clearing_rows:
                self._resolve_clear()
            self.active = None

    def _resolve_clear(self):
        rows = self.clearing_rows
        self.board.clear_rows(rows)
        self.clearing_rows = ()
        self.clear_timer = 0.0
        spin = self._pending_spin
        self._pending_spin = "none"
        self._complete_lock(len(rows), spin)

    def _tick_board(self, elapsed: float, soft_drop: bool) -> None:
        self.clear_notice_timer = max(0.0, self.clear_notice_timer - elapsed)
        self.perfect_clear_timer = max(0.0, self.perfect_clear_timer - elapsed)
        if self.clearing_rows:
            self.clear_timer = max(0.0, self.clear_timer - elapsed)
            if self.clear_timer <= 1e-9:
                self._resolve_clear()
            return
        if self.active is None:
            return
        if soft_drop != self.soft_dropping:
            # Never reinterpret accumulated gravity time at the faster drop rate.
            self.gravity_timer = self.soft_drop_timer = 0.0
            self.soft_dropping = soft_drop
        interval = (min(self.gravity_interval, self.timing.soft_drop_ms / 1000.0)
                    if soft_drop else self.gravity_interval)
        timer = self.soft_drop_timer if soft_drop else self.gravity_timer
        timer += elapsed
        while timer + 1e-9 >= interval:
            timer = max(0.0, timer - interval)
            if not self.step_down(soft=soft_drop):
                timer = 0.0
                break
        if soft_drop:
            self.soft_drop_timer = timer
        else:
            self.gravity_timer = timer
        if self.is_grounded():
            self.lock_timer += elapsed
            if self.lock_timer + 1e-9 >= self.timing.lock_delay_ms / 1000.0:
                self._lock_active()
        else:
            self.lock_timer = 0.0
