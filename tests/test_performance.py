"""Deterministic cache and frame-budget regressions, not flaky FPS assertions."""
from unittest.mock import patch
import unittest
import pygame
from tetris import settings
from tetris.ai import AIController
from tetris.battle import BattleMatch
from tetris.preferences import PlayerSettings
from tetris.presentation import Viewport, initial_window_size
from tetris.renderer import Renderer
from tetris.state import GameState


class PerformanceTests(unittest.TestCase):
    def test_ai_time_budget_bounds_expensive_nodes(self):
        state = GameState(mode="battle")
        controller = AIController("hard")
        controller.serial = state.spawn_serial
        controller.age = controller.interval
        controller.start = state.active
        processed=[]
        def work():
            while True:
                processed.append(1)
                yield None
        controller.search=work()
        ticks=iter((0,.0008,.0016,.0024))
        controller.clock=lambda: next(ticks)
        controller.update(1/60,state)
        self.assertEqual(len(processed),3)
        self.assertIsNotNone(controller.search)

    def test_font_and_notice_are_reused_instead_of_reloaded(self):
        pygame.font.init()
        try:
            screen=pygame.Surface((settings.WINDOW_WIDTH,settings.WINDOW_HEIGHT))
            renderer=Renderer(screen)
            state=GameState()
            state.last_clear_type="T-SPIN MINI DOUBLE"
            state.last_clear_perfect=True
            state.clear_notice_timer=2
            self.assertIs(renderer.font(20),renderer.font(20))
            renderer._draw_clear_notice(state)
            card=next(iter(renderer._notice_cache.values()))
            with patch.object(renderer,"wrap_lines",side_effect=AssertionError("Repeated layout")):
                for _ in range(60):
                    renderer._draw_clear_notice(state)
            self.assertIs(next(iter(renderer._notice_cache.values())),card)
            self.assertEqual(len(renderer._notice_cache),1)
            renderer.preferences.language="ko"
            renderer._draw_clear_notice(state)
            self.assertEqual(len(renderer._notice_cache),2)
        finally:
            pygame.font.quit()

    def test_text_cache_is_bounded_and_reuses_unchanged_text(self):
        pygame.font.init()
        try:
            renderer=Renderer(pygame.Surface((938,864)))
            font=renderer.small_font
            first=renderer._text("SCORE",font,settings.TEXT_COLOR)
            self.assertIs(first,renderer._text("SCORE",font,settings.TEXT_COLOR))
            for n in range(600):
                renderer._text(str(n),font,settings.TEXT_COLOR)
                renderer._measure(str(n),font)
            self.assertLessEqual(len(renderer._text_cache),256)
            self.assertLessEqual(len(renderer._measure_cache),512)
        finally:
            pygame.font.quit()

    def test_board_layer_invalidates_for_new_blocks_garbage_and_clears(self):
        pygame.font.init()
        try:
            renderer=Renderer(pygame.Surface((938,864)))
            state=GameState()
            size=renderer.battle_board_rect(0).size
            first=renderer._battle_layer(state.board,size)
            self.assertIs(first,renderer._battle_layer(state.board,size))
            state.board.grid[-1][0]="J"
            placed=renderer._battle_layer(state.board,size)
            self.assertIsNot(first,placed)
            state.board.add_garbage(1,5)
            garbage=renderer._battle_layer(state.board,size)
            self.assertIsNot(placed,garbage)
            state.board.grid[-1]=["J"]*10
            state.board.clear_rows((21,))
            self.assertIsNot(garbage,renderer._battle_layer(state.board,size))
            self.assertEqual(len(renderer._board_cache),1)
        finally:
            pygame.font.quit()

    def test_enlarged_battle_boards_fit_and_stay_square(self):
        for index in (0,1):
            rect=Renderer.battle_board_rect(index)
            self.assertEqual(rect.width,320)
            self.assertEqual(rect.height,640)
            self.assertEqual(rect.width/10,rect.height/20)
            self.assertTrue(pygame.Rect(0,0,938,864).contains(rect))
        self.assertEqual((settings.DEFAULT_WINDOW_WIDTH,settings.DEFAULT_WINDOW_HEIGHT),(1200,960))
        self.assertEqual(initial_window_size((1920,1080)),(1200,960))
        width,height=initial_window_size((1366,768))
        self.assertLessEqual(width,1366-80)
        self.assertLessEqual(height,768-80)

    def test_viewport_aspect_mapping_and_letterbox(self):
        for size in ((1200,960),(1600,900),(800,700),(1,1)):
            view=Viewport(size)
            self.assertTrue(pygame.Rect(0,0,*size).contains(view.rect))
            self.assertEqual(view.to_canvas(view.rect.topleft),(0,0))
            self.assertIsNone(view.to_canvas((-1,-1)))
            if size!=(1,1):
                self.assertLess(abs(view.rect.width*864-view.rect.height*938),1800)
                self.assertAlmostEqual(view.to_canvas(view.rect.center)[0],469,delta=2)
                self.assertAlmostEqual(view.to_canvas(view.rect.center)[1],432,delta=2)
                if view.rect.left:
                    self.assertIsNone(view.to_canvas((0,view.rect.centery)))
        view=Viewport((1200,960))
        button=Renderer.menu_button_rect(0)
        physical=(view.rect.left+int(button.centerx*view.rect.width/938),
                  view.rect.top+int(button.centery*view.rect.height/864))
        self.assertTrue(button.collidepoint(view.to_canvas(physical)))

    def test_scaled_present_uses_reusable_buffer(self):
        canvas=pygame.Surface((938,864))
        canvas.fill((11,22,33))
        window=pygame.Surface((1200,960))
        view=Viewport(window.get_size())
        buffer=view.scaled
        view.present(canvas,window)
        view.present(canvas,window)
        self.assertIs(view.scaled,buffer)
        self.assertEqual(window.get_at(view.rect.center)[:3],(11,22,33))
        self.assertEqual(window.get_at((0,0))[:3],settings.BACKGROUND)
        small=pygame.Surface((800,700))
        view.present(canvas,small)
        self.assertEqual(view.window_size,(800,700))
        self.assertIsNot(view.scaled,buffer)


if __name__=="__main__":
    unittest.main()
