"""Timing, routing, modes, and settings regressions; never launches the EXE."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import pygame

from tetris.controls import HorizontalRepeat
from tetris.game import Game
from tetris.i18n import EN, KO, TUTORIAL
from tetris.piece import Piece
from tetris.preferences import ACTIONS, FRAME_MS, PlayerSettings
from tetris.renderer import Renderer
from tetris.state import GameState
from tetris import settings

DT = 1 / 60


def key(code, event_type=pygame.KEYDOWN):
    return pygame.event.Event(event_type, key=code)


class MovementProbe:
    def __init__(self):
        self.active = object()
        self.x = 0

    def move(self, dx, dy):
        if abs(self.x + dx) > 20:
            return False
        self.x += dx
        return True


class UpdateTests(unittest.TestCase):
    def test_soft_drop_never_spends_previous_gravity_time(self):
        for carry in (0.0, .10, .30, .55):
            with self.subTest(carry=carry):
                state = GameState(timing=PlayerSettings(soft_drop_ms=50))
                state.active = Piece("O", 4, 3)
                state.gravity_timer = carry
                positions = []
                for _ in range(3):
                    state.tick(DT, soft_drop=True)
                    positions.append(state.active.y)
                self.assertEqual(positions, [3, 3, 4])
                self.assertEqual(state.score, 1)
                state.tick(DT, soft_drop=False)
                state.tick(DT, soft_drop=True)
                self.assertEqual(state.active.y, 4)

    def test_soft_drop_keydown_does_not_move_twice(self):
        game = Game(PlayerSettings(soft_drop_ms=50))
        game.start("marathon")
        game.state.active = Piece("O", 4, 3)
        game.state.gravity_timer = .55
        game.handle_event(key(pygame.K_DOWN))
        self.assertEqual(game.state.active.y, 3)
        game.tick(.05)
        self.assertEqual(game.state.active.y, 4)
        game.handle_event(key(pygame.K_DOWN))  # Duplicate OS repeat is ignored.
        self.assertEqual(game.state.active.y, 4)

    def test_das_12_frames_and_arr_2_frames(self):
        prefs, repeat, state = PlayerSettings(), HorizontalRepeat(), MovementProbe()
        repeat.update(DT, 1, state, prefs)
        self.assertEqual(state.x, 1)
        for _ in range(11):
            repeat.update(DT, 1, state, prefs)
        self.assertEqual(state.x, 1)
        repeat.update(DT, 1, state, prefs)
        self.assertEqual(state.x, 2)
        repeat.update(DT, 1, state, prefs)
        self.assertEqual(state.x, 2)
        repeat.update(DT, 1, state, prefs)
        self.assertEqual(state.x, 3)

    def test_hard_drop_freezes_one_frame_without_clearing_charge(self):
        prefs, repeat, state = PlayerSettings(), HorizontalRepeat(), MovementProbe()
        repeat.update(DT, 1, state, prefs)
        for _ in range(12):
            repeat.update(DT, 1, state, prefs)
        repeat.arr_elapsed = prefs.arr_ms / 1000 - DT
        charge, phase, x = repeat.das_elapsed, repeat.arr_elapsed, state.x
        repeat.after_hard_drop()
        repeat.update(DT, 1, state, prefs)
        self.assertEqual((repeat.das_elapsed, repeat.arr_elapsed, state.x), (charge, phase, x))
        repeat.update(DT, 1, state, prefs)
        self.assertEqual(state.x, x + 1)

    def test_held_direction_survives_real_hard_drop(self):
        game = Game(PlayerSettings(das_ms=0, arr_ms=0))
        game.start("marathon")
        game.handle_event(key(pygame.K_LEFT))
        game.tick(DT)
        game.tick(DT)
        self.assertTrue(game.horizontal.charged)
        game.handle_event(key(pygame.K_SPACE))
        spawn = game.state.active
        self.assertIn(pygame.K_LEFT, game.held.order)
        game.tick(DT)
        self.assertEqual(game.state.active.x, spawn.x)
        self.assertTrue(game.horizontal.charged)
        game.tick(DT)
        self.assertEqual(min(x for x, _ in game.state.active.cells()), 0)

    def test_release_and_opposite_key_priority(self):
        game = Game(PlayerSettings())
        game.start("marathon")
        game.handle_event(key(pygame.K_LEFT))
        game.handle_event(key(pygame.K_RIGHT))
        self.assertEqual(game.held.direction(game.preferences), 1)
        game.handle_event(key(pygame.K_RIGHT, pygame.KEYUP))
        self.assertEqual(game.held.direction(game.preferences), -1)
        game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertEqual(game.view, "pause")
        self.assertFalse(game.held.order)

    def test_defaults_and_exact_fractional_arr_roundtrip(self):
        prefs = PlayerSettings()
        self.assertAlmostEqual(prefs.das_ms / FRAME_MS, 12)
        self.assertAlmostEqual(prefs.arr_ms / FRAME_MS, 2)
        self.assertEqual(prefs.lock_delay_ms, 300)
        prefs.language = "ko"
        with TemporaryDirectory() as folder:
            file = Path(folder) / "prefs.json"
            prefs.save(file)
            loaded = PlayerSettings.load(file)
            self.assertEqual(loaded, prefs)
            self.assertAlmostEqual(loaded.arr_ms, 1000 / 30)
            file.write_text(json.dumps({"das_ms":140,"arr_ms":0,"lock_delay_ms":500}), encoding="utf8")
            loaded = PlayerSettings.load(file)
            self.assertEqual((loaded.das_ms,loaded.arr_ms,loaded.lock_delay_ms),(140,0,500))

    def test_two_binding_slots_conflicts_and_pause_safety(self):
        prefs = PlayerSettings()
        self.assertTrue(prefs.bind("left", 1, pygame.K_a))
        self.assertFalse(prefs.bind("right", 1, pygame.K_a))
        self.assertFalse(prefs.bind("left", 2, pygame.K_d))
        self.assertTrue(prefs.bind("pause", 1, None))
        self.assertFalse(prefs.bind("pause", 0, None))
        self.assertEqual(len(prefs.keys["left"]), 2)
        with TemporaryDirectory() as folder:
            file = Path(folder) / "prefs.json"
            prefs.save(file)
            self.assertEqual(PlayerSettings.load(file).keys, prefs.keys)

    def test_four_main_tabs_and_mode_selection(self):
        game = Game(PlayerSettings())
        game.handle_event(key(pygame.K_RETURN))
        self.assertEqual(game.view, "modes")
        self.assertIsNone(game.state)
        game.handle_event(key(pygame.K_RETURN))
        self.assertEqual((game.view, game.state.mode), ("game", "sprint40"))
        game.open("menu")
        game.selected = 3
        game.handle_event(key(pygame.K_RETURN))
        self.assertEqual((game.view, game.origin), ("tutorial", "menu"))
        self.assertTrue(game.running)
        game.open("menu")
        game.selected = 2
        game.handle_event(key(pygame.K_RETURN))
        self.assertFalse(game.running)

    def test_pause_settings_and_tutorial_preserve_game_and_time(self):
        prefs = PlayerSettings()
        game = Game(prefs)
        game.start("blitz")
        game.tick(1)
        state, piece, elapsed = game.state, game.state.active, game.state.elapsed_time
        game.handle_event(key(pygame.K_ESCAPE))
        self.assertEqual(game.view, "pause")
        game.selected = 1
        game.handle_event(key(pygame.K_RETURN))
        self.assertEqual((game.view, game.origin), ("settings", "pause"))
        game.selected = 3
        with patch.object(PlayerSettings, "save"):
            game.handle_event(key(pygame.K_LEFT))
        self.assertEqual(state.timing.lock_delay_ms, 250)
        game.tick(30)
        game.handle_event(key(pygame.K_ESCAPE))
        self.assertEqual(game.view, "pause")
        game.selected = 2
        game.handle_event(key(pygame.K_RETURN))
        self.assertEqual(game.view, "tutorial")
        game.tick(30)
        game.handle_event(key(pygame.K_ESCAPE))
        self.assertIs(game.state, state)
        self.assertEqual((state.active, state.elapsed_time), (piece, elapsed))
        self.assertTrue(state.paused)
        game.handle_event(key(pygame.K_ESCAPE))
        game.tick(DT)
        self.assertEqual(game.view, "game")
        self.assertGreater(state.elapsed_time, elapsed)

    def test_rebinding_and_language_from_settings_events(self):
        game = Game(PlayerSettings())
        game.open("settings", "menu")
        game.selected = 4
        with patch.object(PlayerSettings, "save"):
            game.handle_event(key(pygame.K_RIGHT))
            self.assertEqual(game.preferences.language, "ko")
            game.handle_event(key(pygame.K_TAB))
            game.slot = 1
            game.handle_event(key(pygame.K_RETURN))
            self.assertEqual(game.capturing, ("left", 1))
            game.handle_event(key(pygame.K_a))
            self.assertEqual(game.preferences.keys["left"][1], pygame.K_a)
            game.handle_event(key(pygame.K_DELETE))
            self.assertIsNone(game.preferences.keys["left"][1])

    def test_sprint_finishes_at_40_after_line_effect(self):
        state = GameState(mode="sprint40")
        state.lines = 39
        state.board.grid[-1][:6] = ["J"] * 6
        state.active = Piece("I", 6, settings.BOARD_ROWS - 2)
        state.hard_drop()
        self.assertFalse(state.finished)
        state.tick(.2)
        self.assertTrue(state.finished)
        self.assertEqual((state.lines, state.finish_reason), (40, "complete"))
        self.assertIsNone(state.active)
        elapsed = state.elapsed_time
        state.tick(10)
        self.assertEqual(state.elapsed_time, elapsed)

    def test_blitz_timeout_and_pause(self):
        state = GameState(mode="blitz")
        state.elapsed_time = 119.95
        state.paused = True
        state.tick(5)
        self.assertEqual(state.elapsed_time, 119.95)
        state.paused = False
        state.tick(.1)
        self.assertEqual(state.elapsed_time, 120)
        self.assertTrue(state.finished)
        self.assertEqual(state.finish_reason, "time")
        self.assertIsNone(state.active)

    def test_all_localized_screens_and_tutorial_layout(self):
        pygame.font.init()
        try:
            screen = pygame.Surface((settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT))
            for language in ("en", "ko"):
                prefs = PlayerSettings(language=language)
                renderer = Renderer(screen, prefs)
                renderer.draw_menu(3)
                renderer.draw_modes(2)
                renderer.draw_settings(prefs)
                renderer.draw_settings(prefs, 3, 1, 1, ("hard_drop",1))
                for page in range(len(TUTORIAL[language])):
                    _, paragraphs, height = renderer.tutorial_layout(page)
                    self.assertLessEqual(height, 496)
                    renderer.draw_tutorial(page)
                state = GameState(mode="blitz")
                state.paused = True
                renderer.draw_pause(state)
                state.finished = True
                state.finish_reason = "time"
                renderer.draw_result(state)
            self.assertEqual(set(EN), set(KO))
        finally:
            pygame.font.quit()


if __name__ == "__main__":
    unittest.main()
