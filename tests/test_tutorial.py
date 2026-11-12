"""Hands-on mission completion, real inputs, skipping, and isolated practice."""
import unittest
import pygame

from tetris.game import Game
from tetris.i18n import TUTORIAL
from tetris.piece import Piece
from tetris.preferences import ACTIONS, PlayerSettings
from tetris.presentation import Viewport
from tetris.renderer import Renderer
from tetris.tutorial import LESSONS, TutorialSession


def press(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def release(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYUP, key=key))


def click(game, rect):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


class TutorialRuleTests(unittest.TestCase):
    def test_all_eight_missions_require_real_actions(self):
        session = TutorialSession()
        for index, lesson in enumerate(LESSONS):
            self.assertEqual(session.index, index)
            self.assertFalse(session.advance())
            self.assertFalse(session.complete)
            if lesson.action == "clear":
                session.perform("hard_drop")
                self.assertFalse(session.complete)
                self.assertTrue(session.state.clearing_rows)
                session.tick(.199)
                self.assertFalse(session.complete)
                session.tick(.001)
                self.assertEqual(session.state.lines, 1)
                self.assertTrue(session.state.board.is_empty())
            else:
                for _ in range(lesson.target):
                    self.assertTrue(session.perform(lesson.action))
            self.assertTrue(session.complete)
            self.assertEqual(session.index, index)
            self.assertTrue(session.advance())
        self.assertTrue(session.finished)
        self.assertFalse(session.advance())

    def test_wall_and_wrong_inputs_do_not_count(self):
        session = TutorialSession()
        self.assertTrue(session.perform("right"))
        self.assertEqual(session.progress, 0)
        self.assertFalse(session.perform("hard_drop"))
        session.state.active = Piece("T", 0, 5)
        self.assertFalse(session.perform("left"))
        self.assertEqual(session.progress, 0)

    def test_practice_has_no_gravity_or_automatic_lock(self):
        session = TutorialSession(lesson_index=4)
        before = session.active
        session.tick(100)
        self.assertEqual(session.active, before)
        session.state.active = session.state.ghost
        session.tick(100)
        self.assertIsNotNone(session.active)
        self.assertTrue(session.state.board.is_empty())

    def test_soft_drop_respects_interval_and_release(self):
        session = TutorialSession(lesson_index=4)
        session.tick(.049, True)
        self.assertEqual(session.progress, 0)
        session.tick(.001, True)
        self.assertEqual(session.progress, 1)
        session.tick(.049, True)
        session.tick(100, False)
        session.tick(.001, True)
        self.assertEqual(session.progress, 1)
        session.tick(.1, True)
        self.assertTrue(session.complete)

    def test_drop_and_hold_change_real_board_and_piece(self):
        session = TutorialSession(lesson_index=5)
        target = session.state.ghost
        session.perform("hard_drop")
        self.assertIsNone(session.active)
        self.assertTrue(all(session.state.board.grid[y][x] == "T" for x,y in target.cells()))
        session = TutorialSession(lesson_index=6)
        session.perform("hold")
        self.assertEqual(session.state.hold_kind, "T")
        self.assertEqual(session.active.kind, "I")
        self.assertFalse(session.state.can_hold)

    def test_missed_line_clear_can_be_retried(self):
        session = TutorialSession(lesson_index=7)
        session.perform("right")
        session.perform("hard_drop")
        session.tick(1)
        self.assertFalse(session.complete)
        self.assertTrue(session.needs_retry)
        session.retry()
        self.assertFalse(session.needs_retry)
        session.perform("hard_drop")
        session.tick(.2)
        self.assertTrue(session.complete)


class TutorialFlowTests(unittest.TestCase):
    def test_mouse_can_complete_every_mission_even_with_unbound_keys(self):
        prefs = PlayerSettings()
        prefs.keys = {action:[None,None] for action in ACTIONS}
        game = Game(prefs)
        game.open("tutorial", "menu")
        for index, lesson in enumerate(LESSONS):
            self.assertEqual(game.tutorial.index, index)
            action = "hard_drop" if lesson.action == "clear" else lesson.action
            control = lesson.controls.index(action)
            for _ in range(lesson.target):
                click(game, Renderer.tutorial_control_rect(control))
            game.tick(.2)
            self.assertTrue(game.tutorial.complete)
            click(game, Renderer.tutorial_rect(2))
        self.assertTrue(game.tutorial.finished)
        click(game, Renderer.tutorial_rect(2))
        self.assertEqual(game.view, "menu")

    def test_custom_keys_use_real_das_and_release_before_next_mission(self):
        prefs = PlayerSettings()
        prefs.keys["left"] = [pygame.K_a, None]
        game = Game(prefs)
        game.open("tutorial", "menu")
        press(game, pygame.K_a)
        game.tick(1/60)
        self.assertEqual(game.tutorial.progress, 1)
        for _ in range(14):
            game.tick(1/60)
        self.assertTrue(game.tutorial.complete)
        press(game, pygame.K_RETURN)
        self.assertEqual(game.tutorial.index, 1)
        self.assertFalse(game.held.order)
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, repeat=True))
        self.assertEqual(game.tutorial.index, 1)

    def test_skip_from_every_step_preserves_paused_battle_or_result(self):
        for origin in ("menu", "pause", "result"):
            for index in range(len(LESSONS)):
                for mouse in (False, True):
                    game = Game(PlayerSettings())
                    if origin != "menu":
                        game.start("battle")
                        game.pause()
                    match, state = game.battle, game.state
                    before = None if state is None else (state.active, [row[:] for row in state.board.grid])
                    game.open("tutorial", origin)
                    game.tutorial = TutorialSession(game.preferences, index)
                    game.tutorial.perform(LESSONS[index].controls[0])
                    game.tick(3)
                    if mouse:
                        click(game, Renderer.tutorial_rect(0))
                    else:
                        press(game, pygame.K_ESCAPE)
                    self.assertEqual(game.view, origin)
                    self.assertIs(game.state, state)
                    self.assertIs(game.battle, match)
                    if state is not None:
                        self.assertEqual((state.active,state.board.grid), before)
                        self.assertEqual(match.time, 0)
                        self.assertTrue(match.paused)

    def test_retry_and_focus_loss_clear_held_input(self):
        game = Game(PlayerSettings())
        game.open("tutorial", "menu")
        press(game, pygame.K_LEFT)
        game.tick(1/60)
        click(game, Renderer.tutorial_rect(1))
        self.assertEqual(game.tutorial.progress, 0)
        self.assertFalse(game.held.order)
        press(game, pygame.K_LEFT)
        game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        game.tick(1)
        self.assertEqual(game.tutorial.progress, 0)

    def test_all_practice_screens_fit_both_languages_and_native_scaling(self):
        pygame.font.init()
        try:
            for language in ("ko", "en"):
                prefs = PlayerSettings(language=language)
                canvas = pygame.Surface((938,864))
                renderer = Renderer(canvas, prefs)
                for index in range(len(LESSONS)):
                    session = TutorialSession(prefs,index)
                    self.assertEqual(len(TUTORIAL[language]),len(LESSONS))
                    font, paragraphs, height = renderer.tutorial_layout(index)
                    self.assertLessEqual(height,100)
                    self.assertTrue(all(renderer._measure(line,font)[0] <= 455
                                        for lines in paragraphs for line in lines))
                    for size in ((1200,960),(800,700)):
                        viewport = Viewport(size)
                        window = pygame.Surface(size)
                        renderer.native_text.begin_frame(viewport)
                        renderer.draw_tutorial(session)
                        viewport.present(canvas,window)
                        renderer.native_text.present(window)
                    session.progress = session.lesson.target
                    renderer.draw_tutorial(session)
                session.finished = True
                renderer.draw_tutorial(session)
        finally:
            pygame.font.quit()
