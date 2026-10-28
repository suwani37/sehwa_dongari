"""User timing, language, and up to two keys per action."""
from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import sys
import pygame

FRAME_MS = 1000.0 / 60.0
OPTIONS = (
    ("das_ms", "DAS", 0, 1000, FRAME_MS),
    ("arr_ms", "ARR", 0, 150, FRAME_MS),
    ("soft_drop_ms", "SOFT DROP", 10, 200, 10),
    ("lock_delay_ms", "LOCK DELAY", 100, 1000, 50),
)
ACTIONS = ("left", "right", "soft_drop", "hard_drop", "rotate_cw",
           "rotate_ccw", "hold", "pause", "quit")


def default_keys():
    return {
        "left": [pygame.K_LEFT, None], "right": [pygame.K_RIGHT, None],
        "soft_drop": [pygame.K_DOWN, None], "hard_drop": [pygame.K_SPACE, None],
        "rotate_cw": [pygame.K_UP, pygame.K_x], "rotate_ccw": [pygame.K_z, None],
        "hold": [pygame.K_c, pygame.K_LSHIFT], "pause": [pygame.K_ESCAPE, pygame.K_p],
        "quit": [pygame.K_q, None],
    }


def _settings_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "SuwanTetris" / "player_settings.json"
    return Path(__file__).resolve().parent.parent / "player_settings.json"


SETTINGS_PATH = _settings_path()


@dataclass
class PlayerSettings:
    das_ms: float = 12 * FRAME_MS
    arr_ms: float = 2 * FRAME_MS
    soft_drop_ms: float = 50.0
    lock_delay_ms: float = 300.0
    language: str = "en"
    keys: dict = field(default_factory=default_keys)

    def adjust(self, name: str, direction: int) -> None:
        for key, _, low, high, step in OPTIONS:
            if key == name:
                value = getattr(self, key)
                value = (round(value / step) + direction) * step
                setattr(self, key, max(low, min(high, value)))
                return
        raise ValueError(name)

    def matches(self, action: str, key: int) -> bool:
        return key in self.keys[action]

    def bind(self, action: str, slot: int, key: int | None) -> bool:
        if action not in ACTIONS or slot not in (0, 1):
            return False
        if key is not None and (type(key) is not int or key <= 0):
            return False
        if key is not None:
            for other, values in self.keys.items():
                if other != action and key in values:
                    return False
        values = list(self.keys[action])
        if key is not None and key in values:
            values[values.index(key)] = None
        values[slot] = key
        if action == "pause" and not any(v is not None for v in values):
            return False
        self.keys[action] = values
        return True

    def reset_timings(self):
        defaults = PlayerSettings()
        for key, *_ in OPTIONS:
            setattr(self, key, getattr(defaults, key))

    def reset_keys(self):
        self.keys = default_keys()

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        result = cls()
        for key, _, low, high, _ in OPTIONS:
            value = data.get(key)
            if type(value) in (int, float) and math.isfinite(value):
                setattr(result, key, max(low, min(high, value)))
        if data.get("language") in ("en", "ko"):
            result.language = data["language"]
        saved = data.get("keys")
        if isinstance(saved, dict):
            candidate = default_keys()
            for action in ACTIONS:
                values = saved.get(action)
                if isinstance(values, list):
                    candidate[action] = [v if type(v) is int and 0 < v <= 2147483647
                                         else None for v in (values + [None, None])[:2]]
            used = set()
            for action in ACTIONS:
                for slot, value in enumerate(candidate[action]):
                    if value in used:
                        candidate[action][slot] = None
                    elif value is not None:
                        used.add(value)
            if not any(candidate["pause"]):
                # Always retain a way to open the pause menu.
                for action in ACTIONS:
                    candidate[action] = [None if v == pygame.K_ESCAPE else v
                                         for v in candidate[action]]
                candidate["pause"][0] = pygame.K_ESCAPE
            result.keys = candidate
        return result

    def save(self, path: Path = SETTINGS_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["schema_version"] = 2
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
