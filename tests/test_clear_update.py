"""Clear labels, mini/full recognition, tutorial scope, and default landing time."""
import unittest
from unittest.mock import patch
import pygame
from tetris import settings
from tetris.game import Game
from tetris.i18n import TUTORIAL, text
from tetris.piece import Piece
from tetris.preferences import PlayerSettings
from tetris.renderer import Renderer
from tetris.state import GameState


class ClearUpdateTests(unittest.TestCase):
    def spin_setup(self, spin="mini", cleared=0):
        state = GameState()
        rotation = 1 if cleared in (2, 3) else 0
        if spin == "full" and cleared == 2:
            rotation = 2
        state.active = Piece("T", 4, 18, rotation)
        cells = set(state.active.cells())
        if cleared:
            rows = {1: (19,), 2: (18, 19) if rotation == 1 else (19, 20),
                    3: (18, 19, 20)}[cleared]
            for y in rows:
                for x in range(10):
                    if (x, y) not in cells:
                        state.board.grid[y][x] = "J"
        if rotation == 0:
            corners = ((4,18),(4,20),(6,20)) if spin == "mini" else ((4,18),(6,18),(4,20))
        elif rotation == 1:
            corners = ((4,18),(6,18),(4,20))
            state.board.grid[21][5] = "J"
        else:
            corners = ((4,18),(4,20),(6,20))
        for x,y in corners:
            state.board.grid[y][x] = "J"
        state.last_rotation = True
        state.last_kick_index = 0
        return state

    def test_default_landing_time_and_reset(self):
        prefs = PlayerSettings()
        self.assertEqual(prefs.lock_delay_ms, 300)
        self.assertEqual(settings.LOCK_DELAY, .3)
        prefs.lock_delay_ms = 500
        prefs.reset_timings()
        self.assertEqual(prefs.lock_delay_ms, 300)
        self.assertEqual(text("ko", "lock_delay_ms"), "착지 후 고정 시간")

    def test_basic_clear_names_survive_perfect_clear(self):
        examples = (
            (Piece("I", 6, 20), "SINGLE"),
            (Piece("O", 8, 20), "DOUBLE"),
            (Piece("J", 0, 19, 1), "TRIPLE"),
            (Piece("I", 7, 18, 1), "TETRIS"),
        )
        for piece,label in examples:
            with self.subTest(label=label):
                state = GameState()
                occupied = set(piece.cells())
                for y in {y for _,y in occupied}:
                    for x in range(10):
                        if (x,y) not in occupied:
                            state.board.grid[y][x] = "J"
                state.active = piece
                state.hard_drop()
                state.tick(.2)
                self.assertEqual(state.last_clear_type, label)
                self.assertTrue(state.last_clear_perfect)
                self.assertEqual(state.last_clear, "PERFECT CLEAR")

    def test_mini_and_full_spin_labels_and_scores(self):
        for spin,lines,expected,label in (
            ("mini",0,100,"T-SPIN MINI"),
            ("mini",1,200,"T-SPIN MINI SINGLE"),
            ("mini",2,400,"T-SPIN MINI DOUBLE"),
            ("full",0,400,"T-SPIN"),
            ("full",1,800,"T-SPIN SINGLE"),
            ("full",2,1200,"T-SPIN DOUBLE"),
            ("full",3,1600,"T-SPIN TRIPLE"),
        ):
            with self.subTest(spin=spin,lines=lines):
                state = self.spin_setup(spin,lines)
                self.assertEqual(state._spin_type(), spin)
                self.assertTrue(state.board.can_place(state.active))
                self.assertTrue(state.is_grounded())
                state.hard_drop()
                if lines:
                    state.tick(.2)
                self.assertEqual(state.lines,lines)
                self.assertEqual(state.score,expected)
                self.assertEqual(state.last_clear_type,label)

    def test_fifth_kick_upgrades_mini_and_zero_drop_keeps_it(self):
        state = self.spin_setup()
        state.last_kick_index = 4
        self.assertEqual(state._spin_type(),"full")
        state.hard_drop()
        self.assertEqual((state.score,state.last_clear_type),(400,"T-SPIN"))
        rotating = GameState()
        rotating.active = Piece("T",4,10)
        with patch("tetris.state.kick_offsets", return_value=((99,0),)*4+((0,0),)):
            self.assertTrue(rotating.rotate())
        self.assertEqual(rotating.last_kick_index,4)

    def test_notice_survives_next_piece_and_expires(self):
        state = self.spin_setup("full",1)
        state.hard_drop()
        state.tick(.2)
        label = state.last_clear_type
        state.hard_drop()
        self.assertEqual(state.last_clear_type,label)
        state.paused = True
        state.tick(5)
        self.assertEqual(state.clear_notice_timer,2)
        state.paused = False
        state.tick(2.1)
        self.assertEqual(state.clear_notice_timer,0)

    def test_tutorial_pages_wrap_to_new_count(self):
        game = Game(PlayerSettings())
        game.open("tutorial","menu")
        for language in ("en","ko"):
            game.preferences.language = language
            self.assertEqual(len(TUTORIAL[language]),3)
            game.tutorial_page = 2
            game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RIGHT))
            self.assertEqual(game.tutorial_page,0)
            game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_LEFT))
            self.assertEqual(game.tutorial_page,2)

    def test_notice_and_tutorial_surfaces_both_languages(self):
        pygame.font.init()
        try:
            surface = pygame.Surface((settings.WINDOW_WIDTH,settings.WINDOW_HEIGHT))
            for language in ("en","ko"):
                renderer = Renderer(surface,PlayerSettings(language=language))
                state = self.spin_setup("mini",2)
                state.hard_drop()
                state.tick(.2)
                renderer.draw(state)
                rect = renderer.clear_notice_rect()
                self.assertLess(rect.right, renderer.board_rect.left)
                self.assertGreaterEqual(rect.top,160)
                self.assertLess(rect.bottom,285)
                self.assertNotEqual(text(language,state.last_clear_type),"")
                for page in range(len(TUTORIAL[language])):
                    self.assertLessEqual(renderer.tutorial_layout(page)[2],496)
                    renderer.draw_tutorial(page)
        finally:
            pygame.font.quit()
