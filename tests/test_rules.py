"""Checks for the game rules that NEXT and HOLD depend on."""

import os
import random
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

import pygame

from tetris.board import Board
from tetris.game import Game
from tetris.piece import COLORS, Piece, SHAPES, SevenBag, kick_offsets, spawn_piece
from tetris.state import GameState
from tetris.renderer import Renderer
from tetris.preferences import PlayerSettings, OPTIONS
from tetris import settings


class TetrisRulesTests(unittest.TestCase):
    def test_every_shape_has_four_cells_in_every_rotation(self):
        self.assertEqual(set(SHAPES), set("IOTSZJL"))
        for kind in SHAPES:
            for rotation in range(4):
                self.assertEqual(len(set(Piece(kind, 0, 0, rotation).cells())), 4)

    def test_seven_bag_has_each_kind_once(self):
        bag = SevenBag(random.Random(123))
        self.assertEqual({bag.draw() for _ in range(7)}, set(SHAPES))
        self.assertEqual({bag.draw() for _ in range(7)}, set(SHAPES))

    def test_hold_once_until_piece_locks(self):
        state = GameState(random.Random(123))
        first = state.active.kind
        following = state.next_queue[0]
        self.assertTrue(state.hold())
        self.assertEqual(state.hold_kind, first)
        self.assertEqual(state.active.kind, following)
        self.assertFalse(state.hold())
        state.hard_drop()
        self.assertTrue(state.can_hold)
        self.assertTrue(state.hold())
        self.assertEqual(state.active.kind, first)

    def test_hard_drop_locks_and_spawns_next(self):
        state = GameState(random.Random(1))
        following = state.next_queue[0]
        state.hard_drop()
        self.assertEqual(state.active.kind, following)
        self.assertEqual(sum(cell is not None for row in state.board.grid for cell in row), 4)

    def test_wall_and_occupied_cells_block_movement(self):
        board = Board(10, settings.BOARD_ROWS)
        self.assertFalse(board.can_place(Piece("O", -1, 0)))
        board.lock(Piece("O", 0, settings.BOARD_ROWS - 2))
        self.assertFalse(board.can_place(Piece("O", 0, settings.BOARD_ROWS - 3)))
        self.assertFalse(board.can_place(Piece("O", 0, settings.BOARD_ROWS - 1)))

    def test_hidden_rows_and_srs_kicks(self):
        self.assertEqual(settings.BOARD_ROWS, 22)
        self.assertEqual(settings.VISIBLE_ROWS, 20)
        self.assertEqual(settings.HIDDEN_ROWS, 2)
        self.assertEqual(kick_offsets("T", 0, 1),
                         ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)))
        self.assertEqual(kick_offsets("I", 0, 1),
                         ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)))
        state = GameState(random.Random(2))
        self.assertTrue(any(y < settings.HIDDEN_ROWS for _, y in state.active.cells()))
        self.assertTrue(any(y >= settings.HIDDEN_ROWS for _, y in state.active.cells()))
        for _ in range(4):
            self.assertTrue(state.rotate())
        self.assertEqual(state.active.rotation, 0)

    def test_lock_delay_and_spawn_collision(self):
        state = GameState(random.Random(3))
        state.active = Piece("O", 0, settings.BOARD_ROWS - 2)
        state.tick(settings.LOCK_DELAY / 2)
        self.assertEqual(sum(cell is not None for row in state.board.grid for cell in row), 0)
        state.tick(settings.LOCK_DELAY / 2)
        self.assertEqual(sum(cell is not None for row in state.board.grid for cell in row), 4)
        edge = GameState(random.Random(3))
        edge.active = Piece("O", 0, 0)
        edge.board.grid[2][0] = "I"
        edge.tick(settings.LOCK_DELAY)
        self.assertFalse(edge.game_over)
        self.assertEqual(edge.board.grid[0][0], "O")
        blocked = GameState(random.Random(3))
        spawn = spawn_piece(blocked.next_queue[0], settings.BOARD_COLUMNS)
        x, y = next(spawn.cells())
        blocked.board.grid[y][x] = "I"
        blocked._spawn_next()
        self.assertTrue(blocked.game_over)

    def test_tetris_scoring_and_back_to_back(self):
        state = GameState(random.Random(5))
        for expected in (2800, 7200):
            for row in state.board.grid[-4:]:
                row[:9] = ["J"] * 9
            state.active = Piece("I", 7, settings.BOARD_ROWS - 4, 1)
            state.hard_drop()
            self.assertEqual(state.score, 0 if expected == 2800 else 2800)
            self.assertEqual(len(state.clearing_rows), 4)
            self.assertIsNone(state.active)
            state.tick(settings.LINE_CLEAR_DELAY / 2)
            self.assertEqual(len(state.clearing_rows), 4)
            state.tick(settings.LINE_CLEAR_DELAY / 2)
            self.assertEqual(state.score, expected)
            self.assertTrue(state.board.is_empty())
            self.assertGreater(state.perfect_clear_timer, 0)
        self.assertEqual(state.lines, 8)

    def test_single_perfect_clear_bonus_and_flash(self):
        state = GameState(random.Random(6))
        state.board.grid[-1][:6] = ["J"] * 6
        state.active = Piece("I", 6, settings.BOARD_ROWS - 2)
        state.hard_drop()
        self.assertEqual(state.clearing_rows, (settings.BOARD_ROWS - 1,))
        self.assertEqual(state.lines, 0)
        self.assertIsNone(state.active)
        pygame.font.init()
        try:
            screen = pygame.Surface((settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT))
            renderer = Renderer(screen)
            renderer.draw(state)
            state.tick(settings.LINE_CLEAR_DELAY)
            state.tick(0.1)
            renderer.draw(state)
        finally:
            pygame.font.quit()
        self.assertEqual(state.lines, 1)
        self.assertEqual(state.score, 900)
        self.assertEqual(state.last_clear, "PERFECT CLEAR")
        self.assertTrue(state.board.is_empty())
        self.assertIsNotNone(state.active)

    def test_double_and_triple_perfect_clear_scores(self):
        for piece, expected in (
            (Piece("O", 8, settings.BOARD_ROWS - 2), 1500),
            (Piece("J", 0, settings.BOARD_ROWS - 3, 1), 2100),
        ):
            with self.subTest(kind=piece.kind):
                state = GameState(random.Random(6))
                occupied = set(piece.cells())
                rows = sorted({y for _, y in occupied})
                for y in rows:
                    for x in range(settings.BOARD_COLUMNS):
                        if (x, y) not in occupied:
                            state.board.grid[y][x] = "Z"
                state.active = piece
                state.hard_drop()
                state.tick(settings.LINE_CLEAR_DELAY)
                self.assertEqual(state.score, expected)
                self.assertTrue(state.board.is_empty())

    def test_nonperfect_clear_has_no_bonus(self):
        state = GameState(random.Random(6))
        state.board.grid[-1][:8] = ["J"] * 8
        state.active = Piece("O", 8, settings.BOARD_ROWS - 2)
        state.hard_drop()
        state.tick(settings.LINE_CLEAR_DELAY)
        self.assertEqual(state.score, 100)
        self.assertEqual(state.perfect_clear_timer, 0)
        self.assertFalse(state.board.is_empty())

    def test_t_spin_corner_scoring(self):
        state = GameState(random.Random(5))
        state.active = Piece("T", 4, settings.BOARD_ROWS - 4)
        state.last_rotation = True
        for x, y in ((4, 18), (6, 18), (4, 20)):
            state.board.grid[y][x] = "J"
        state.hard_drop()
        self.assertEqual(state.score, 400)

    def test_ghost_lands_on_the_floor(self):
        state = GameState(random.Random(5))
        self.assertIsNotNone(state.ghost)
        self.assertFalse(state.board.can_place(state.ghost.moved(0, 1)))
        pygame.font.init()
        try:
            screen = pygame.Surface((settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT))
            renderer = Renderer(screen)
            renderer.draw(state)
            x, y = next(state.ghost.cells())
            pixel = screen.get_at(renderer._cell_rect(x, y).center)[:3]
            self.assertNotEqual(pixel, settings.BOARD_BACKGROUND)
        finally:
            pygame.font.quit()

    def test_i_piece_uses_its_own_wall_kick(self):
        state = GameState(random.Random(1))
        state.active = Piece("I", -2, 3, 1)
        self.assertTrue(state.board.can_place(state.active))
        self.assertTrue(state.rotate(1))
        self.assertEqual((state.active.x, state.active.rotation), (0, 2))

    def test_soft_drop_scores_and_pause_stops_time(self):
        state = GameState(random.Random(1))
        start = state.active
        state.paused = True
        state.tick(1.0, soft_drop=True)
        self.assertEqual(state.active, start)
        state.paused = False
        state.tick(0.05, soft_drop=True)
        self.assertEqual(state.active.y, start.y + 1)
        self.assertEqual(state.score, 1)

    def test_timing_settings_save_load_and_limits(self):
        prefs = PlayerSettings()
        self.assertAlmostEqual(prefs.das_ms, 200)
        self.assertAlmostEqual(prefs.arr_ms, 1000 / 30)
        for _ in range(40):
            prefs.adjust("das_ms", -1)
            prefs.adjust("arr_ms", -1)
        self.assertEqual((prefs.das_ms, prefs.arr_ms), (0, 0))
        prefs.adjust("lock_delay_ms", 1)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            prefs.save(path)
            self.assertEqual(PlayerSettings.load(path), prefs)

    def test_menu_and_settings_screens_render(self):
        pygame.font.init()
        try:
            screen = pygame.Surface((settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT))
            renderer = Renderer(screen)
            renderer.draw_menu()
            renderer.draw_settings(PlayerSettings())
            for index in range(len(OPTIONS)):
                self.assertTrue(screen.get_rect().contains(renderer.setting_minus_rect(index)))
                self.assertTrue(screen.get_rect().contains(renderer.setting_plus_rect(index)))
            self.assertTrue(screen.get_rect().contains(renderer.settings_back_rect()))
        finally:
            pygame.font.quit()

    def test_renderer_draws_game_state(self):
        pygame.font.init()
        try:
            screen = pygame.Surface((settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT))
            state = GameState(random.Random(4))
            renderer = Renderer(screen)
            renderer.draw(state)
            self.assertEqual(renderer.board_rect.left, settings.BOARD_LEFT)
            self.assertEqual(settings.WINDOW_WIDTH, 938)
            state.hold()
            renderer.draw(state)
            color = COLORS[state.hold_kind]
            self.assertTrue(any(
                screen.get_at((x, y))[:3] == color
                for x in range(settings.MARGIN, settings.MARGIN + settings.HOLD_PANEL_WIDTH)
                for y in range(110, 180)
            ))
            state.game_over = True
            Renderer(screen).draw(state)
        finally:
            pygame.font.quit()

    def test_completed_row_is_removed(self):
        board = Board(10, settings.BOARD_ROWS)
        board.grid[-1][:8] = ["I"] * 8
        self.assertEqual(board.lock(Piece("O", 8, settings.BOARD_ROWS - 2)), 1)
        self.assertTrue(all(cell is None for cell in board.grid[0]))
        self.assertEqual(board.grid[-1][8:], ["O", "O"])


if __name__ == "__main__":
    unittest.main()
