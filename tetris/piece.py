"""The seven tetrominoes, SRS wall kicks, and shuffled supply."""

from dataclasses import dataclass
import random

SHAPES = {
    "I": ("....", "IIII", "....", "...."),
    "O": ("OO", "OO"),
    "T": (".T.", "TTT", "..."),
    "S": (".SS", "SS.", "..."),
    "Z": ("ZZ.", ".ZZ", "..."),
    "J": ("J..", "JJJ", "..."),
    "L": ("..L", "LLL", "..."),
}

COLORS = {
    "G": (117, 130, 148),
    "I": (55, 208, 225),
    "O": (244, 208, 63),
    "T": (174, 100, 231),
    "S": (85, 204, 112),
    "Z": (232, 88, 101),
    "J": (76, 118, 225),
    "L": (241, 153, 67),
}

# SRS kick offsets use screen coordinates: positive y points down.
# Transition keys are (old orientation, new orientation), where 0 is spawn.
_JLSTZ_KICKS = {
    (0, 1): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (1, 0): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (1, 2): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (2, 1): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (2, 3): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (3, 2): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (3, 0): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (0, 3): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
}

_I_KICKS = {
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)),
}


def kick_offsets(kind: str, old: int, new: int) -> tuple[tuple[int, int], ...]:
    if kind == "O":
        return ((0, 0),)
    table = _I_KICKS if kind == "I" else _JLSTZ_KICKS
    return table[(old, new)]


@dataclass(frozen=True)
class Piece:
    kind: str
    x: int
    y: int
    rotation: int = 0

    @property
    def size(self) -> int:
        return len(SHAPES[self.kind])

    def cells(self):
        size = self.size
        for row, pattern in enumerate(SHAPES[self.kind]):
            for column, value in enumerate(pattern):
                if value == ".":
                    continue
                x, y = column, row
                for _ in range(self.rotation % 4):
                    x, y = size - 1 - y, x
                yield self.x + x, self.y + y

    def moved(self, dx: int, dy: int):
        return Piece(self.kind, self.x + dx, self.y + dy, self.rotation)

    def rotated(self, direction: int = 1):
        if self.kind == "O":
            return self
        return Piece(self.kind, self.x, self.y, (self.rotation + direction) % 4)


def spawn_piece(kind: str, board_columns: int) -> Piece:
    size = len(SHAPES[kind])
    return Piece(kind, (board_columns - size) // 2, 1)


class SevenBag:
    """Draw all seven kinds before starting another shuffled bag."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._bag: list[str] = []

    def draw(self) -> str:
        if not self._bag:
            self._bag = list(SHAPES)
            self._rng.shuffle(self._bag)
        return self._bag.pop()
