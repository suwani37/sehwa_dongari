"""Window-resolution glyphs, layering, and resize cache regressions."""
import unittest
import pygame

from tetris import settings
from tetris.battle import BattleMatch
from tetris.presentation import Viewport
from tetris.preferences import PlayerSettings
from tetris.renderer import Renderer
from tetris.state import GameState


class NativeTextTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        self.canvas = pygame.Surface((938,864))
        self.renderer = Renderer(self.canvas)

    def tearDown(self):
        pygame.font.quit()

    def test_glyphs_equal_font_rasterized_at_final_pixel_size(self):
        for dimensions in ((1200,960),(800,700),(1600,1200)):
            window = pygame.Surface(dimensions)
            viewport = Viewport(dimensions)
            layer = self.renderer.native_text
            layer.begin_frame(viewport)
            self.canvas.fill((0,0,0))
            self.renderer._label("한국어 SCORE",100,100,self.renderer.text_font,(255,255,255))
            self.assertEqual(self.canvas.get_at((100,100))[:3],(0,0,0))
            viewport.present(self.canvas,window)
            layer.present(window)
            size = round(24*viewport.rect.height/864)
            font = pygame.font.Font(self.renderer.font_path,size)
            glyph = font.render("한국어 SCORE",True,(255,255,255))
            expected = pygame.Surface(glyph.get_size())
            expected.fill((0,0,0))
            expected.blit(glyph,(0,0))
            position = layer._point((100,100))
            actual = window.subsurface(pygame.Rect(position,glyph.get_size()))
            self.assertEqual(pygame.image.tobytes(actual,"RGB"),
                             pygame.image.tobytes(expected,"RGB"))

    def test_same_size_uses_original_text_and_resize_rebuilds_cache(self):
        layer = self.renderer.native_text
        layer.begin_frame(Viewport((938,864)))
        self.renderer.draw_menu()
        self.assertFalse(layer.commands)
        layer.begin_frame(Viewport((1200,960)))
        first = layer.image("SCORE",19,(255,255,255))
        self.assertIs(first,layer.image("SCORE",19,(255,255,255)))
        layer.begin_frame(Viewport((1200,960)))
        self.assertIs(first,layer.image("SCORE",19,(255,255,255)))
        layer.begin_frame(Viewport((800,700)))
        self.assertFalse(layer.images)
        self.assertIsNot(first,layer.image("SCORE",19,(255,255,255)))
        for number in range(300):
            layer.image(str(number),19,(255,255,255))
        self.assertLessEqual(len(layer.images),256)

    def test_button_background_covers_earlier_text(self):
        viewport = Viewport((200,100),(100,50))
        layer = self.renderer.native_text
        layer.begin_frame(viewport)
        layer.draw("OLD",10,(255,255,255),(5,5),"topleft",255)
        layer.cover(pygame.Rect(0,0,100,50))
        window = pygame.Surface((200,100))
        window.fill((80,0,0))
        before = pygame.image.tobytes(window,"RGB")
        layer.present(window)
        self.assertEqual(before,pygame.image.tobytes(window,"RGB"))

    def test_pause_dims_background_text_and_restores_clip(self):
        viewport = Viewport((1200,960))
        layer = self.renderer.native_text
        layer.begin_frame(viewport)
        self.renderer.draw_pause(GameState())
        commands = [cmd for cmd in layer.commands if cmd[0]=="text"]
        self.assertTrue(any(cmd[-1]==30 for cmd in commands))
        self.assertTrue(any(cmd[-1]==255 for cmd in commands))
        window = pygame.Surface((1200,960))
        clip = pygame.Rect(10,10,1150,900)
        window.set_clip(clip)
        layer.present(window)
        self.assertEqual(window.get_clip(),clip)

    def test_all_screens_and_effects_use_native_text_in_both_languages(self):
        for language in ("en","ko"):
            prefs = PlayerSettings(language=language)
            self.renderer.preferences = prefs
            battle = BattleMatch(prefs,seed=8)
            battle.player.last_clear_type = "TETRIS"
            battle.player.last_clear_perfect = True
            battle.player.clear_notice_timer = 2
            battle.player.perfect_clear_timer = 1
            battle.winner = "player"
            for draw in (self.renderer.draw_menu,self.renderer.draw_modes,
                         self.renderer.draw_difficulty,
                         lambda:self.renderer.draw_settings(prefs),
                         lambda:self.renderer.draw_settings(prefs,tab=1),
                         self.renderer.draw_tutorial,
                         lambda:self.renderer.draw(battle.player),
                         lambda:self.renderer.draw_battle(battle),
                         lambda:self.renderer.draw_result(battle.player,battle=battle)):
                viewport = Viewport((1200,960))
                window = pygame.Surface((1200,960))
                layer = self.renderer.native_text
                layer.begin_frame(viewport)
                draw()
                self.assertTrue(layer.commands)
                viewport.present(self.canvas,window)
                layer.present(window)
