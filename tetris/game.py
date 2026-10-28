"""Application screens and input routing; gameplay rules live in GameState."""
import pygame

from tetris import settings
from tetris.i18n import TUTORIAL
from tetris.controls import HeldKeys, HorizontalRepeat
from tetris.preferences import ACTIONS, OPTIONS, PlayerSettings
from tetris.renderer import Renderer
from tetris.state import GameState
from tetris.battle import BattleMatch
from tetris.presentation import Viewport, initial_window_size
from tetris.native_text import enable_dpi_awareness


class Game:
    def __init__(self, preferences=None):
        self.preferences = preferences if preferences is not None else PlayerSettings.load()
        self.state = None
        self.battle = None
        self.difficulty = "normal"
        self.view = "menu"
        self.origin = "menu"
        self.selected = 0
        self.settings_tab = 0
        self.slot = 0
        self.capturing = None
        self.message = ""
        self.tutorial_page = 0
        self.held = HeldKeys()
        self.horizontal = HorizontalRepeat()
        self.running = True

    def open(self, view, origin=None):
        self.view = view
        self.selected = 0
        self.capturing = None
        self.message = ""
        self.held.clear()
        self.horizontal.reset()
        if origin is not None:
            self.origin = origin
        if view == "tutorial":
            self.tutorial_page = 0
        if view == "menu":
            self.state = None
            self.battle = None

    def start(self, mode):
        if mode == "battle":
            self.battle = BattleMatch(self.preferences, self.difficulty)
            self.state = self.battle.player
        else:
            self.battle = None
            self.state = GameState(timing=self.preferences, mode=mode)
        self.open("game")

    def resume(self):
        if self.battle is not None:
            self.battle.set_paused(False)
        else:
            self.state.paused = False
        self.open("game")

    def pause(self):
        if self.battle is not None:
            self.battle.set_paused(True)
        else:
            self.state.paused = True
        self.open("pause")

    def save(self):
        try:
            self.preferences.save()
        except OSError:
            self.message = "save_error"

    def change_timing(self, index, direction):
        self.preferences.adjust(OPTIONS[index][0], direction)
        self.message = ""
        self.save()

    def toggle_language(self):
        self.preferences.language = "ko" if self.preferences.language == "en" else "en"
        self.save()

    def reset_settings(self):
        if self.settings_tab == 0:
            self.preferences.reset_timings()
        else:
            self.preferences.reset_keys()
        self.save()

    def bind_key(self, key):
        action, slot = self.capturing
        if self.preferences.bind(action, slot, key):
            self.message = ""
            self.save()
        else:
            self.message = "pause_required" if key is None else "conflict"
        self.capturing = None

    def _settings_activate(self):
        reset_index = 5 if self.settings_tab == 0 else len(ACTIONS)
        if self.selected == reset_index:
            self.reset_settings()
        elif self.selected == reset_index + 1:
            self.open(self.origin)
        elif self.settings_tab == 0 and self.selected == 4:
            self.toggle_language()
        elif self.settings_tab == 1 and self.selected < len(ACTIONS):
            self.capturing = (ACTIONS[self.selected], self.slot)
            self.message = ""

    def _settings_event(self, event):
        count = 7 if self.settings_tab == 0 else len(ACTIONS) + 2
        if event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_ESCAPE:
                self.open(self.origin)
            elif key == pygame.K_TAB:
                self.settings_tab = 1 - self.settings_tab
                self.selected = 0
                self.message = ""
            elif key in (pygame.K_UP, pygame.K_DOWN):
                self.selected = (self.selected + (-1 if key == pygame.K_UP else 1)) % count
            elif key in (pygame.K_LEFT, pygame.K_RIGHT):
                direction = -1 if key == pygame.K_LEFT else 1
                if self.settings_tab == 0 and self.selected < len(OPTIONS):
                    self.change_timing(self.selected, direction)
                elif self.settings_tab == 0 and self.selected == 4:
                    self.toggle_language()
                elif self.settings_tab == 1:
                    self.slot = 1 - self.slot
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self._settings_activate()
            elif key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.settings_tab == 1 and self.selected < len(ACTIONS):
                self.capturing = (ACTIONS[self.selected], self.slot)
                self.bind_key(None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in (0, 1):
                if Renderer.tab_rect(index).collidepoint(event.pos):
                    self.settings_tab = index
                    self.selected = 0
                    self.message = ""
                    return
            if Renderer.settings_back_rect().collidepoint(event.pos):
                self.open(self.origin)
            elif Renderer.reset_rect().collidepoint(event.pos):
                self.reset_settings()
            elif self.settings_tab == 0:
                if Renderer.language_rect().collidepoint(event.pos):
                    self.selected = 4
                    self.toggle_language()
                for index in range(len(OPTIONS)):
                    for direction, rect in ((-1, Renderer.setting_minus_rect(index)),
                                            (1, Renderer.setting_plus_rect(index))):
                        if rect.collidepoint(event.pos):
                            self.selected = index
                            self.change_timing(index, direction)
            else:
                for index, action in enumerate(ACTIONS):
                    for slot in (0, 1):
                        if Renderer.key_slot_rect(index, slot).collidepoint(event.pos):
                            self.selected, self.slot = index, slot
                            self.capturing = (action, slot)
                            self.message = ""

    def _choose(self, choice):
        if self.view == "menu":
            if choice == 0:
                self.open("modes")
            elif choice == 1:
                self.settings_tab = 0
                self.open("settings", "menu")
            elif choice == 2:
                self.running = False
            elif choice == 3:
                self.open("tutorial", "menu")
        elif self.view == "modes":
            if choice == 4:
                self.open("menu")
            elif choice == 3:
                self.open("difficulty")
            else:
                self.start(("sprint40", "blitz", "marathon")[choice])
        elif self.view == "difficulty":
            if choice == 3:
                self.open("modes")
            else:
                self.difficulty = ("easy", "normal", "hard")[choice]
                self.start("battle")
        elif self.view in ("pause", "result"):
            origin = self.view
            if choice == 0:
                if origin == "pause":
                    self.resume()
                else:
                    self.start(self.state.mode)
            elif choice == 1:
                self.settings_tab = 0
                self.open("settings", origin)
            elif choice == 2:
                self.open("tutorial", origin)
            elif choice == 3:
                self.open("menu")

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYUP:
            self.held.release(event.key)
            return
        if event.type == pygame.WINDOWFOCUSLOST:
            if self.view == "game":
                self.pause()
            self.held.clear()
            return
        if self.view == "result" and event.type in (pygame.KEYDOWN, pygame.TEXTINPUT, pygame.TEXTEDITING):
            return
        if self.capturing:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.capturing = None
                else:
                    self.bind_key(None if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE) else event.key)
            return
        if self.view == "settings":
            self._settings_event(event)
            return
        if self.view == "tutorial":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.open(self.origin)
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    self.tutorial_page = (self.tutorial_page + (-1 if event.key == pygame.K_LEFT else 1)) % len(TUTORIAL[self.preferences.language])
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for index in range(3):
                    if Renderer.tutorial_rect(index).collidepoint(event.pos):
                        if index == 1:
                            self.open(self.origin)
                        else:
                            self.tutorial_page = (self.tutorial_page + (-1 if index == 0 else 1)) % len(TUTORIAL[self.preferences.language])
                        break
            return
        if self.view == "game":
            if event.type != pygame.KEYDOWN or not self.held.press(event.key):
                return
            action = next((name for name in ACTIONS if self.preferences.matches(name, event.key)), None)
            if action == "pause":
                self.pause()
            elif action == "quit":
                self.running = False
            elif action == "rotate_cw":
                self.state.rotate(1)
            elif action == "rotate_ccw":
                self.state.rotate(-1)
            elif action == "hard_drop":
                self.state.hard_drop()
                self.horizontal.after_hard_drop()
            elif action == "hold" and self.state.hold():
                self.horizontal.after_hard_drop()
            # Horizontal and soft-drop movement are driven once by tick, not KEYDOWN.
            return
        if event.type == pygame.KEYDOWN:
            key = event.key
            if self.view == "pause" and (key == pygame.K_ESCAPE or self.preferences.matches("pause", key)):
                self.resume()
                return
            if key == pygame.K_ESCAPE:
                self.open("modes" if self.view == "difficulty" else "menu")
            elif key in (pygame.K_UP, pygame.K_DOWN):
                count = 5 if self.view == "modes" else 4
                self.selected = (self.selected + (-1 if key == pygame.K_UP else 1)) % count
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self._choose(self.selected)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            rects = (Renderer.menu_button_rect if self.view == "menu" else
                     Renderer.mode_button_rect if self.view == "modes" else
                     Renderer.difficulty_button_rect if self.view == "difficulty" else Renderer.pause_button_rect)
            for index in range(5 if self.view == "modes" else 4):
                if rects(index).collidepoint(event.pos):
                    self._choose(index)
                    break

    def tick(self, elapsed):
        if self.view != "game" or self.state is None:
            return
        self.horizontal.update(elapsed, self.held.direction(self.preferences), self.state, self.preferences)
        if self.battle is not None:
            # Player input has already been applied; resolve both boards together.
            self.battle.tick(elapsed, self.held.active("soft_drop", self.preferences))
            ended = self.battle.finished
        else:
            self.state.tick(elapsed, self.held.active("soft_drop", self.preferences))
            ended = self.state.ended
        if ended:
            self.open("result")

    def draw(self, renderer):
        renderer.preferences = self.preferences
        if self.view == "menu":
            renderer.draw_menu(self.selected)
        elif self.view == "modes":
            renderer.draw_modes(self.selected)
        elif self.view == "difficulty":
            renderer.draw_difficulty(self.selected)
        elif self.view == "settings":
            renderer.draw_settings(self.preferences, self.selected, self.settings_tab,
                                   self.slot, self.capturing, self.message)
        elif self.view == "tutorial":
            renderer.draw_tutorial(self.tutorial_page)
        elif self.view == "pause":
            renderer.draw_pause(self.state, self.selected, battle=self.battle)
        elif self.view == "result":
            renderer.draw_result(self.state, self.selected, battle=self.battle)
        elif self.battle is not None:
            renderer.draw_battle(self.battle)
        else:
            renderer.draw(self.state)

    def run(self):
        enable_dpi_awareness()
        pygame.init()
        try:
            window = pygame.display.set_mode(initial_window_size(),pygame.RESIZABLE)
            screen = pygame.Surface((settings.WINDOW_WIDTH,settings.WINDOW_HEIGHT)).convert()
            viewport = Viewport(window.get_size())
            pygame.display.set_caption(settings.TITLE)
            clock = pygame.time.Clock()
            renderer = Renderer(screen, self.preferences)
            while self.running:
                elapsed = clock.tick(settings.FPS) / 1000.0
                for event in pygame.event.get():
                    if event.type in (pygame.VIDEORESIZE,pygame.WINDOWSIZECHANGED):
                        window = pygame.display.get_surface()
                        viewport.resize(window.get_size())
                    if event.type in (pygame.MOUSEBUTTONDOWN,pygame.MOUSEBUTTONUP,pygame.MOUSEMOTION):
                        position = viewport.to_canvas(event.pos)
                        if position is None:
                            continue
                        attributes = event.dict.copy()
                        attributes["pos"] = position
                        event = pygame.event.Event(event.type,attributes)
                    self.handle_event(event)
                if not self.running:
                    break
                self.tick(elapsed)
                renderer.native_text.begin_frame(viewport)
                self.draw(renderer)
                viewport.present(screen,window)
                renderer.native_text.present(window)
                pygame.display.flip()
        finally:
            pygame.quit()
