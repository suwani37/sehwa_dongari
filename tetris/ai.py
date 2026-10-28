"""Frame-budgeted, reachable-placement AI. No network or trained model required."""
from collections import deque
from dataclasses import dataclass
import random
from time import perf_counter

from tetris.board import Board
from tetris.piece import Piece, kick_offsets, spawn_piece

DIFFICULTIES = {
    "easy": (1.8, 4),
    "normal": (0.85, 1),
    "hard": (0.5, 1),
}


@dataclass(frozen=True)
class Plan:
    piece: Piece
    actions: tuple[str, ...]
    value: float
    start: Piece | None = None
    use_hold: bool = False


def evaluate(board: Board, piece: Piece, strategy="easy") -> float:
    simulated = Board(board.columns, board.rows)
    simulated.grid = [row[:] for row in board.grid]
    cleared = simulated.lock(piece)
    heights, holes = [], 0
    for x in range(board.columns):
        seen = False
        height = 0
        for y in range(board.rows):
            if simulated.grid[y][x] is not None:
                if not seen:
                    height = board.rows - y
                seen = True
            elif seen:
                holes += 1
        heights.append(height)
    bumpiness = sum(abs(a - b) for a, b in zip(heights, heights[1:]))
    if strategy != "easy":
        # Build an open well for attacks; dig instead when the stack is dangerous.
        well = board.columns - 1
        for row in reversed(board.grid):
            if row.count("G") >= board.columns - 2 and row.count(None) == 1:
                well = row.index(None)
                break
        maximum = max(heights, default=0)
        danger = maximum >= 15 or holes >= 4
        surface = sum(abs(heights[x] - heights[x + 1])
                      for x in range(board.columns - 1)
                      if x != well and x + 1 != well)
        prepared = sum(all(value is not None for x, value in enumerate(row) if x != well)
                       and row[well] is None for row in simulated.grid)
        concentration = sum((sum(value is not None for x, value in enumerate(row)
                                 if x != well) / (board.columns - 1)) ** 4
                            for row in simulated.grid)
        attack = (0, 0, 1, 2, 4)[cleared]
        return (attack * (24 if strategy == "normal" else 32) + cleared * 4
                + (150 if simulated.is_empty() else 0)
                - (6 if cleared == 1 and not danger else 0)
                - holes * 11 - sum(heights) * .5 - maximum * .65
                - surface * .45
                + (0 if danger else prepared * 4 + concentration * 2 - heights[well] * 2))
    return (cleared * 9 + (10 if cleared == 4 else 0)
            + (50 if simulated.is_empty() else 0)
            - holes * 7.5 - sum(heights) * .45
            - bumpiness * .35 - max(heights, default=0) * .3)


def placement_search(board: Board, start: Piece, strategy="easy"):
    """Yield after each BFS node and return ranked reachable landing plans."""
    snapshot = Board(board.columns, board.rows)
    snapshot.grid = [row[:] for row in board.grid]
    if not snapshot.can_place(start):
        return []
    def key(piece):
        return (piece.x, piece.y, piece.rotation)
    queue = deque([start])
    parents = {key(start): None}
    landings = set()
    plans = []
    while queue:
        piece = queue.popleft()
        current = key(piece)
        cells = frozenset(piece.cells())
        if not snapshot.can_place(piece.moved(0, 1)) and all(y >= 0 for _, y in cells):
            if cells not in landings:
                landings.add(cells)
                actions = []
                cursor = current
                while parents[cursor] is not None:
                    previous, action = parents[cursor]
                    actions.append(action)
                    cursor = previous
                plans.append(Plan(piece, tuple(reversed(actions)), evaluate(snapshot, piece, strategy), start))
        neighbors = [(piece.moved(-1, 0), "left"), (piece.moved(1, 0), "right")]
        if piece.kind != "O":
            for direction, action in ((1, "cw"), (-1, "ccw")):
                rotated = piece.rotated(direction)
                for dx, dy in kick_offsets(piece.kind, piece.rotation, rotated.rotation):
                    candidate = rotated.moved(dx, dy)
                    if snapshot.can_place(candidate):
                        neighbors.append((candidate, action))
                        break
        neighbors.append((piece.moved(0, 1), "down"))
        for candidate, action in neighbors:
            candidate_key = key(candidate)
            if candidate.y < -2 or candidate_key in parents:
                continue
            if snapshot.can_place(candidate):
                parents[candidate_key] = (current, action)
                queue.append(candidate)
        yield None
    plans.sort(key=lambda plan: (-plan.value, len(plan.actions), plan.piece.x))
    return plans


def attack_search(state, start, strategy):
    """Search reachable current and held placements, yielding each BFS step."""
    plans = yield from placement_search(state.board, start, strategy)
    if state.can_hold:
        kind = state.hold_kind or state.next_queue[0]
        held_start = spawn_piece(kind, state.board.columns)
        held = yield from placement_search(state.board, held_start, strategy)
        plans.extend(Plan(p.piece, p.actions, p.value - .5, held_start, True) for p in held)
    plans.sort(key=lambda p: (-p.value, len(p.actions), p.use_hold, p.piece.x))
    return plans


def action_piece(board, piece, action):
    if action in ("left", "right", "down"):
        result = piece.moved(-1 if action == "left" else 1 if action == "right" else 0,
                             1 if action == "down" else 0)
        return result if board.can_place(result) else None
    rotated = piece.rotated(1 if action == "cw" else -1)
    for dx, dy in kick_offsets(piece.kind, piece.rotation, rotated.rotation):
        result = rotated.moved(dx, dy)
        if board.can_place(result):
            return result
    return None


def rebase_actions(board, plan, actual):
    """Validate the entire route before execution, accounting for gravity."""
    expected = plan.start
    if expected is None or (actual.kind, actual.x, actual.rotation) != (
            expected.kind, expected.x, expected.rotation) or actual.y < expected.y:
        return None
    route = []
    for action in plan.actions:
        expected = action_piece(board, expected, action)
        if expected is None:
            return None
        if action == "down" and actual.y >= expected.y:
            continue
        actual = action_piece(board, actual, action)
        if actual is None:
            return None
        route.append(action)
    return tuple(route) if actual == plan.piece else None


class AIController:
    def __init__(self, difficulty="normal", rng=None):
        if difficulty not in DIFFICULTIES:
            raise ValueError(difficulty)
        self.interval, self.choice_width = DIFFICULTIES[difficulty]
        self.difficulty = difficulty
        self.ready = None
        self.rng = rng or random.Random()
        self.serial = None
        self.age = 0.0
        self.search = None
        self.start = None
        self.node_budget = 96
        self.time_budget = 0.002
        self.clock = perf_counter

    def update(self, elapsed, state):
        if state.ended or state.paused or state.active is None:
            return
        if self.serial != state.spawn_serial:
            self.serial = state.spawn_serial
            self.age = 0.0
            self.search = None
            self.ready = None
        self.age += elapsed
        easy = self.difficulty == "easy"
        if easy and self.age < self.interval:
            return
        if easy and self.search is not None and self.start != state.active:
            self.search = None
        if self.search is None and self.ready is None:
            self.start = state.active
            self.search = (placement_search(state.board, self.start) if easy
                           else attack_search(state, self.start, self.difficulty))
        if self.ready is None:
            deadline = self.clock() + self.time_budget
            for _ in range(self.node_budget):
                try:
                    next(self.search)
                except StopIteration as done:
                    self.ready = done.value
                    self.search = None
                    break
                if self.clock() >= deadline:
                    break
        if self.ready is None or self.age < self.interval:
            return
        plans, self.ready = self.ready, None
        if not plans:
            state.hard_drop()
            return
        if easy:
            if state.active != self.start:
                return
            plan = plans[self.rng.randrange(min(self.choice_width, len(plans)))]
            route = plan.actions
        else:
            for plan in plans:
                actual = plan.start if plan.use_hold else state.active
                route = rebase_actions(state.board, plan, actual)
                if route is not None and (not plan.use_hold or state.can_hold):
                    break
            else:
                return
            if plan.use_hold and not state.hold():
                return
        for action in route:
            if action == "left":
                valid = state.move(-1, 0)
            elif action == "right":
                valid = state.move(1, 0)
            elif action == "down":
                valid = state.step_down()
            else:
                valid = state.rotate(1 if action == "cw" else -1)
            if not valid:
                return
        if state.active == plan.piece:
            state.hard_drop()
