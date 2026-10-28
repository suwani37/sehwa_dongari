"""Board occupancy, collision checks, and completed rows."""

from tetris.piece import Piece


class Board:
    def __init__(self, columns: int, rows: int) -> None:
        self.columns = columns
        self.rows = rows
        self.grid: list[list[str | None]] = [
            [None] * columns for _ in range(rows)
        ]

    def can_place(self, piece: Piece) -> bool:
        for x, y in piece.cells():
            if x < 0 or x >= self.columns or y >= self.rows:
                return False
            if y >= 0 and self.grid[y][x] is not None:
                return False
        return True

    def place(self, piece: Piece) -> None:
        """Place a landed piece without clearing rows yet."""
        for x, y in piece.cells():
            if y < 0:
                raise ValueError("Cannot lock a piece above the board")
            self.grid[y][x] = piece.kind

    def full_rows(self) -> tuple[int, ...]:
        return tuple(y for y, row in enumerate(self.grid)
                     if all(cell is not None for cell in row))

    def clear_rows(self, rows: tuple[int, ...]) -> None:
        if not rows:
            return
        removed = set(rows)
        remaining = [row for y, row in enumerate(self.grid) if y not in removed]
        self.grid = [[None] * self.columns for _ in rows] + remaining

    def is_empty(self) -> bool:
        return all(cell is None for row in self.grid for cell in row)

    def lock(self, piece: Piece) -> int:
        """Place and clear immediately, useful for rule-level callers."""
        self.place(piece)
        rows = self.full_rows()
        self.clear_rows(rows)
        return len(rows)

    def is_occupied(self, x: int, y: int) -> bool:
        """Walls and the floor count as filled for T-spin corner checks."""
        if x < 0 or x >= self.columns or y >= self.rows:
            return True
        return y >= 0 and self.grid[y][x] is not None

    def add_garbage(self, count: int, hole: int) -> bool:
        """Push rows up; report overflow instead of silently discarding blocks."""
        if not 0 <= hole < self.columns or not 0 <= count <= self.rows:
            raise ValueError("Invalid garbage packet")
        if not count:
            return False
        overflow = any(cell is not None for row in self.grid[:count] for cell in row)
        garbage = [[None if x == hole else "G" for x in range(self.columns)]
                   for _ in range(count)]
        self.grid = self.grid[count:] + garbage
        return overflow
