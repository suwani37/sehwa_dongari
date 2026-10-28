"""Attack strategy and result input regressions, without opening a window."""
import random
import unittest
import pygame

from tetris.ai import AIController, attack_search, placement_search, rebase_actions
from tetris.game import Game
from tetris.piece import Piece, spawn_piece
from tetris.preferences import ACTIONS, PlayerSettings
from tetris.renderer import Renderer
from tetris.state import GameState


def finish(search):
    while True:
        try:
            next(search)
        except StopIteration as result:
            return result.value


class AttackAITests(unittest.TestCase):
    def test_normal_and_hard_use_held_i_for_multi_line_attacks(self):
        for difficulty in ("normal", "hard"):
            for lines in (2, 3, 4):
                state = GameState(rng=random.Random(1), mode="battle", defer_spawn=True)
                state.active = spawn_piece("O", 10)
                state.hold_kind = "I"
                state.board.grid[-lines - 1][0] = "J"  # Supported block; not a perfect clear.
                for row in state.board.grid[-lines:]:
                    row[:9] = ["J"] * 9
                ai = AIController(difficulty)
                ai.clock = lambda: 0
                ai.node_budget = 100000
                ai.update(2, state)
                state.tick(.2)
                self.assertEqual(state.lock_events.popleft().lines, lines)
                self.assertEqual(state.hold_kind, "O")

    def test_hold_is_not_considered_until_available_again(self):
        state = GameState(rng=random.Random(1), mode="battle")
        state.can_hold = False
        plans = finish(attack_search(state, state.active, "hard"))
        self.assertTrue(plans)
        self.assertFalse(any(plan.use_hold for plan in plans))

    def test_gravity_during_search_preserves_a_legal_route(self):
        state = GameState(mode="battle")
        state.active = Piece("T", 3, 1)
        plans = finish(placement_search(state.board, state.active, "hard"))
        actual = state.active.moved(0, 2)
        valid = [(plan, rebase_actions(state.board, plan, actual)) for plan in plans]
        plan, route = next((p, r) for p, r in valid if r is not None)
        state.active = actual
        for action in route:
            if action in ("left", "right"):
                self.assertTrue(state.move(-1 if action == "left" else 1, 0))
            elif action == "down":
                self.assertTrue(state.step_down())
            else:
                self.assertTrue(state.rotate(1 if action == "cw" else -1))
        self.assertEqual(state.active, plan.piece)

    def test_seeded_play_builds_multi_line_attacks(self):
        for difficulty in ("normal", "hard"):
            state = GameState(rng=random.Random(11), mode="battle", defer_spawn=True)
            ai = AIController(difficulty)
            ai.clock = lambda: 0
            ai.node_budget = 100000
            clears = []
            for _ in range(60):
                ai.update(2, state)
                state.tick(.2)
                self.assertTrue(state.lock_events)
                clears.append(state.lock_events.popleft().lines)
                self.assertFalse(state.game_over)
                state._spawn_next()
            self.assertIn(4, clears)
            self.assertGreaterEqual(sum(lines >= 2 for lines in clears), 3)


class ResultMouseTests(unittest.TestCase):
    def test_all_result_buttons_require_mouse_in_every_mode(self):
        for mode in ("sprint40", "blitz", "marathon", "battle"):
            for button, destination in enumerate(("game", "settings", "tutorial", "menu")):
                game = Game(PlayerSettings())
                game.start(mode)
                previous = game.state
                game.open("result")
                for key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_r, pygame.K_ESCAPE,
                            pygame.K_UP, pygame.K_DOWN, pygame.K_q):
                    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
                    self.assertEqual(game.view, "result")
                    self.assertIs(game.state, previous)
                    self.assertTrue(game.running)
                game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                  pos=Renderer.pause_button_rect(button).center))
                self.assertEqual(game.view, destination)
                if button == 0:
                    self.assertIsNot(game.state, previous)
                elif button in (1, 2):
                    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    self.assertEqual(game.view, "result")

    def test_obsolete_restart_binding_is_not_exposed(self):
        self.assertNotIn("restart", ACTIONS)
        self.assertNotIn("restart", PlayerSettings().keys)
