"""Shared battle damage rules for human and AI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LockEvent:
    lines: int
    spin: str = "none"
    perfect: bool = False
    back_to_back: bool = False


def combo_bonus(streak: int) -> int:
    if streak < 3:
        return 0
    if streak <= 5:
        return 1
    if streak <= 9:
        return 2
    return 3


def attack_lines(event: LockEvent, streak: int) -> int:
    if event.lines == 0:
        return 0
    if event.perfect:
        return 10
    table = ({1: 1, 2: 2} if event.spin == "mini" else
             {1: 2, 2: 4, 3: 6} if event.spin == "full" else
             {1: 0, 2: 1, 3: 2, 4: 4})
    difficult = event.spin != "none" or event.lines == 4
    return table[event.lines] + int(event.back_to_back and difficult) + combo_bonus(streak)
