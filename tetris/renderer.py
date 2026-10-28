"""Draw the visible playfield, ghost, and side panel."""

from collections import OrderedDict
from pathlib import Path
from weakref import WeakKeyDictionary

import pygame

from tetris import settings
from tetris.piece import COLORS, spawn_piece
from tetris.preferences import ACTIONS, FRAME_MS, OPTIONS, PlayerSettings
from tetris.i18n import TUTORIAL, text
from tetris.state import GameState
from tetris.native_text import NativeText


class Renderer:
    def __init__(self, screen: pygame.Surface, preferences=None) -> None:
        self.screen = screen
        self.preferences = preferences or PlayerSettings()
        font_path = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansKR.ttf"
        if not font_path.exists():
            font_path = Path("C:/Windows/Fonts/malgun.ttf")
        self.font_path = str(font_path) if font_path.exists() else None
        self._fonts = {}
        self._font_sizes = {}
        self.native_text = NativeText(self.font_path)
        self._text_cache = OrderedDict()
        self._measure_cache = OrderedDict()
        self._notice_cache = OrderedDict()
        self._ghost_cache = {}
        self._grid_cache = {}
        self._board_cache = WeakKeyDictionary()
        self._tutorial_cache = {}
        self.menu_font = self.font(62)
        self.title_font = self.font(32)
        self.text_font = self.font(24)
        self.small_font = self.font(19)
        notices = ("SINGLE","DOUBLE","TRIPLE","TETRIS","T-SPIN MINI DOUBLE",
                   "T-SPIN SINGLE","T-SPIN DOUBLE","T-SPIN TRIPLE","PERFECT CLEAR")
        glyphs = "".join(text(language,key) for language in ("en","ko") for key in notices)
        for size in (15,20):
            self.font(size).render(glyphs,True,settings.ACCENT_COLOR)
        self.board_rect = pygame.Rect(
            settings.BOARD_LEFT, settings.MARGIN,
            settings.BOARD_WIDTH, settings.BOARD_HEIGHT,
        )

    def draw(self, state: GameState) -> None:
        self.screen.fill(settings.BACKGROUND)
        pygame.draw.rect(self.screen, settings.BOARD_BACKGROUND, self.board_rect)
        for column in range(1, settings.BOARD_COLUMNS):
            x = self.board_rect.left + column * settings.CELL_SIZE
            pygame.draw.line(self.screen, settings.GRID_COLOR,
                             (x, self.board_rect.top), (x, self.board_rect.bottom - 1))
        for row in range(1, settings.VISIBLE_ROWS):
            y = self.board_rect.top + row * settings.CELL_SIZE
            pygame.draw.line(self.screen, settings.GRID_COLOR,
                             (self.board_rect.left, y), (self.board_rect.right - 1, y))
        pygame.draw.rect(self.screen, settings.BORDER_COLOR, self.board_rect, 2)

        for y in range(settings.HIDDEN_ROWS, settings.BOARD_ROWS):
            for x, kind in enumerate(state.board.grid[y]):
                if kind is not None:
                    self._draw_cell(x, y, kind)
        if state.active is not None:
            ghost = state.ghost
            if ghost is not None:
                active_cells = set(state.active.cells())
                for x, y in ghost.cells():
                    if y >= settings.HIDDEN_ROWS and (x, y) not in active_cells:
                        self._draw_ghost(x, y, state.active.kind)
            for x, y in state.active.cells():
                if y >= settings.HIDDEN_ROWS:
                    self._draw_cell(x, y, state.active.kind)

        if state.clearing_rows:
            self._draw_line_clear_effect(state)
        self._draw_panel(state)
        if state.perfect_clear_timer > 0:
            self._draw_perfect_clear_effect(state)

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(
            self.board_rect.left + x * settings.CELL_SIZE + 2,
            self.board_rect.top + (y - settings.HIDDEN_ROWS) * settings.CELL_SIZE + 2,
            settings.CELL_SIZE - 4,
            settings.CELL_SIZE - 4,
        )

    def _draw_cell(self, x: int, y: int, kind: str) -> None:
        rect = self._cell_rect(x, y)
        pygame.draw.rect(self.screen, COLORS[kind], rect, border_radius=4)
        pygame.draw.rect(self.screen, settings.TEXT_COLOR, rect, 1, border_radius=4)

    def _draw_ghost(self, x: int, y: int, kind: str) -> None:
        rect = self._cell_rect(x,y)
        self.screen.blit(self._ghost_image(kind,rect.size),rect.topleft)

    def _draw_line_clear_effect(self, state: GameState) -> None:
        phase = 1.0 - state.clear_timer / settings.LINE_CLEAR_DELAY
        alpha = 95 if int(phase * 12) % 2 else 185
        for row in state.clearing_rows:
            if row < settings.HIDDEN_ROWS:
                continue
            top = self.board_rect.top + (row - settings.HIDDEN_ROWS) * settings.CELL_SIZE
            flash = pygame.Surface((settings.BOARD_WIDTH, settings.CELL_SIZE),
                                   pygame.SRCALPHA)
            flash.fill((235, 250, 255, alpha))
            self.screen.blit(flash, (self.board_rect.left, top))
            pygame.draw.line(self.screen, settings.TEXT_COLOR,
                             (self.board_rect.left, top + settings.CELL_SIZE // 2),
                             (self.board_rect.right - 1, top + settings.CELL_SIZE // 2), 2)

    def _draw_perfect_clear_effect(self, state: GameState) -> None:
        life = state.perfect_clear_timer / settings.PERFECT_CLEAR_EFFECT_TIME
        intensity = min(1.0, (1.0 - life) * 6.0, life * 4.0)
        banner = pygame.Surface((settings.BOARD_WIDTH - 24, 94), pygame.SRCALPHA)
        banner.fill((100, 72, 10, int(175 * intensity)))
        pygame.draw.rect(banner, (255, 226, 108, int(230 * intensity)),
                         banner.get_rect(), 3, border_radius=8)
        self.screen.blit(banner,
                         (self.board_rect.left + 12, self.board_rect.centery - 47))
        self._blit_text(self.tr("perfect"), self.title_font, (255,235,125),
                        (self.board_rect.centerx, self.board_rect.centery),
                        "center", int(255 * intensity))

    def _draw_panel(self, state: GameState) -> None:
        left = settings.MARGIN
        right = self.board_rect.right + settings.MARGIN
        self._label(self.tr("hold_label"), left, 46, self.title_font, settings.ACCENT_COLOR)
        self._draw_preview(state.hold_kind, left, 112, settings.HOLD_PANEL_WIDTH)
        if state.clear_notice_timer > 0:
            self._draw_clear_notice(state)
        self._label(self.tr(state.mode), left, 285, self.text_font, settings.ACCENT_COLOR)
        self._label(self.tr("timer"), left, 345, self.small_font, settings.MUTED_COLOR)
        seconds = state.time_remaining if state.mode == "blitz" else state.elapsed_time
        self._label(self.format_time(seconds), left, 385, self.text_font, settings.TEXT_COLOR)
        if state.mode == "sprint40":
            self._label(self.tr("remaining"), left, 460, self.small_font, settings.MUTED_COLOR)
            self._label(str(max(0, 40 - state.lines)), left, 498, self.title_font, settings.TEXT_COLOR)
        self._label("TETRIS", right, 35, self.title_font, settings.ACCENT_COLOR)
        self._label(self.tr("next_label"), right, 105, self.text_font, settings.MUTED_COLOR)
        for index, kind in enumerate(state.next_queue):
            self._draw_preview(kind, right, 145 + index * 78, settings.PANEL_WIDTH)
        self._label(self.tr("score"), right, 563, self.text_font, settings.MUTED_COLOR)
        self._label(str(state.score), right, 605, self.title_font, settings.TEXT_COLOR)
        self._label(f"{self.tr('lines')}  {state.lines}", right, 675, self.text_font, settings.TEXT_COLOR)
        self._label(f"{self.tr('level')}  {state.level}", right, 720, self.text_font, settings.TEXT_COLOR)
    @staticmethod
    def clear_notice_rect():
        return pygame.Rect(settings.MARGIN, 176, settings.HOLD_PANEL_WIDTH, 88)

    def _draw_clear_notice(self, state, rect=None):
        rect = self.clear_notice_rect() if rect is None else rect
        key = (self.preferences.language, state.last_clear_type,
               state.last_clear_perfect, rect.width, rect.height)
        card = self._notice_cache.get(key)
        if card is None:
            card = pygame.Surface(rect.size)
            card.fill(settings.BOARD_BACKGROUND)
            pygame.draw.line(card,settings.ACCENT_COLOR,(0,0),(0,rect.height),3)
            label = self.tr(state.last_clear_type)
            for size in range(20,13,-1):
                font = self.font(size)
                lines = self.wrap_lines(label,font,rect.width-14)
                height = len(lines)*(font.get_linesize()+2)+(22 if state.last_clear_perfect else 0)
                if len(lines)<=2 and height<=rect.height-16:
                    break
            top = 8
            labels = []
            for line in lines:
                labels.append((line, font, settings.ACCENT_COLOR, (8, top)))
                top += font.get_linesize()+2
            if state.last_clear_perfect:
                labels.append((self.tr("perfect"), self.font(15), (255,235,125),
                               (8,rect.height-25)))
            card = (card, tuple(labels))
            self._notice_cache[key] = card
            if len(self._notice_cache)>32:
                self._notice_cache.popitem(last=False)
        else:
            self._notice_cache.move_to_end(key)
        background, labels = card
        self.screen.blit(background, rect.topleft)
        for label, font, color, (x, y) in labels:
            self._blit_text(label, font, color, (rect.left + x, rect.top + y))

    def _draw_preview(self, kind: str | None, left: int, top: int,
                      panel_width: int) -> None:
        if kind is None:
            return
        cells = list(spawn_piece(kind, 4).cells())
        min_x = min(x for x, _ in cells)
        min_y = min(y for _, y in cells)
        width = max(x for x, _ in cells) - min_x + 1
        size = 24
        offset_x = left + (panel_width - width * size) // 2
        for x, y in cells:
            rect = pygame.Rect(offset_x + (x - min_x) * size,
                               top + (y - min_y) * size, size - 2, size - 2)
            pygame.draw.rect(self.screen, COLORS[kind], rect, border_radius=2)

    def _label(self, text: str, x: int, y: int, font: pygame.font.Font,
               color: tuple[int, int, int]) -> None:
        self._blit_text(text, font, color, (x, y))

    def _blit_text(self, label, font, color, position, anchor="topleft", alpha=255):
        if self.native_text.draw(label, self._font_sizes[id(font)], color,
                                 position, anchor, alpha):
            return
        image = self._text(label, font, color)
        if alpha != 255:
            image = image.copy()
            image.set_alpha(alpha)
        self.screen.blit(image, image.get_rect(**{anchor: position}))

    def font(self, size):
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(self.font_path,size)
            self._font_sizes[id(self._fonts[size])] = size
        return self._fonts[size]

    def _text(self, label, font, color):
        key = (id(font),label,tuple(color))
        image = self._text_cache.get(key)
        if image is None:
            image = font.render(label,True,color)
            self._text_cache[key] = image
            if len(self._text_cache)>256:
                self._text_cache.popitem(last=False)
        else:
            self._text_cache.move_to_end(key)
        return image

    def _measure(self, label, font):
        key = (id(font),label)
        size = self._measure_cache.get(key)
        if size is None:
            size = font.size(label)
            self._measure_cache[key] = size
            if len(self._measure_cache)>512:
                self._measure_cache.popitem(last=False)
        else:
            self._measure_cache.move_to_end(key)
        return size

    def _ghost_image(self, kind, size, border=2, radius=4):
        key = (kind,size,border,radius)
        if key not in self._ghost_cache:
            image = pygame.Surface(size,pygame.SRCALPHA)
            pygame.draw.rect(image,(*COLORS[kind],65),image.get_rect(),border_radius=radius)
            pygame.draw.rect(image,(*COLORS[kind],210),image.get_rect(),border,border_radius=radius)
            self._ghost_cache[key] = image
        return self._ghost_cache[key]


    def tr(self, key):
        return text(self.preferences.language, key)

    @staticmethod
    def format_time(seconds):
        milliseconds = round(max(0.0, seconds) * 1000)
        minutes, remainder = divmod(milliseconds, 60000)
        return f"{minutes:02d}:{remainder // 1000:02d}.{remainder % 1000:03d}"

    @staticmethod
    def menu_button_rect(index):
        return pygame.Rect((settings.WINDOW_WIDTH - 300) // 2, 300 + index * 96, 300, 68)

    @staticmethod
    def mode_button_rect(index):
        if index == 4:
            return pygame.Rect((settings.WINDOW_WIDTH - 240) // 2, 746, 240, 58)
        return pygame.Rect((settings.WINDOW_WIDTH - 440) // 2, 210 + index * 120, 440, 60)

    @staticmethod
    def difficulty_button_rect(index):
        if index == 3:
            return Renderer.mode_button_rect(4)
        return pygame.Rect((settings.WINDOW_WIDTH - 340) // 2, 280 + index * 140, 340, 65)

    @staticmethod
    def pause_button_rect(index):
        return pygame.Rect((settings.WINDOW_WIDTH - 340) // 2, 315 + index * 95, 340, 64)

    @staticmethod
    def tab_rect(index):
        return pygame.Rect(205 + index * 270, 172, 258, 54)

    @staticmethod
    def setting_minus_rect(index):
        return pygame.Rect(540, 255 + index * 90, 48, 48)

    @staticmethod
    def setting_plus_rect(index):
        return pygame.Rect(785, 255 + index * 90, 48, 48)

    @staticmethod
    def language_rect():
        return pygame.Rect(540, 615, 293, 48)

    @staticmethod
    def key_slot_rect(index, slot):
        return pygame.Rect(465 + slot * 195, 245 + index * 43, 180, 36)

    @staticmethod
    def reset_rect():
        return pygame.Rect(settings.WINDOW_WIDTH // 2 - 270, 770, 250, 52)

    @staticmethod
    def settings_back_rect():
        return pygame.Rect(settings.WINDOW_WIDTH // 2 + 20, 770, 250, 52)

    @staticmethod
    def tutorial_rect(index):
        return pygame.Rect(100 + index * 270, 770, 200, 52)

    def _centered(self, label, y, font, color):
        self._blit_text(label, font, color, (settings.WINDOW_WIDTH // 2, y), "midtop")

    def _button(self, rect, label, selected=False):
        color = settings.ACCENT_COLOR if selected else settings.BORDER_COLOR
        pygame.draw.rect(self.screen, settings.BOARD_BACKGROUND, rect, border_radius=8)
        pygame.draw.rect(self.screen, color, rect, 3 if selected else 1, border_radius=8)
        self.native_text.cover(rect)
        font = self.text_font
        for size in range(24, 13, -1):
            if self._measure(label,font)[0] <= rect.width - 14:
                break
            font = self.font(size - 1)
        self._blit_text(label, font, settings.TEXT_COLOR, rect.center, "center")

    def draw_menu(self, selected=0):
        self.screen.fill(settings.BACKGROUND)
        self._centered("TETRIS", 115, self.menu_font, settings.ACCENT_COLOR)
        for index, key in enumerate(("play", "setting", "quit", "tutorial")):
            self._button(self.menu_button_rect(index), self.tr(key), selected == index)

    def draw_modes(self, selected=0):
        self.screen.fill(settings.BACKGROUND)
        self._centered(self.tr("modes"), 105, self.menu_font, settings.ACCENT_COLOR)
        for index, key in enumerate(("sprint40", "blitz", "marathon", "battle")):
            rect = self.mode_button_rect(index)
            self._button(rect, self.tr(key), selected == index)
            self._centered(self.tr(("sprint_desc", "blitz_desc", "marathon_desc", "battle_desc")[index]),
                           rect.bottom + 14, self.small_font, settings.MUTED_COLOR)
        self._button(self.mode_button_rect(4), self.tr("back"), selected == 4)

    def draw_difficulty(self, selected=0):
        self.screen.fill(settings.BACKGROUND)
        self._centered(self.tr("battle"), 90, self.menu_font, settings.ACCENT_COLOR)
        self._centered(self.tr("difficulty"), 190, self.text_font, settings.MUTED_COLOR)
        for index, key in enumerate(("easy", "normal", "hard", "back")):
            self._button(self.difficulty_button_rect(index), self.tr(key), selected == index)

    def key_label(self, key):
        if key is None:
            return self.tr("none")
        arrows = {pygame.K_LEFT: "←", pygame.K_RIGHT: "→", pygame.K_UP: "↑", pygame.K_DOWN: "↓"}
        return arrows.get(key) or pygame.key.name(key).upper()

    def draw_settings(self, preferences, selected=0, tab=0, slot=0, capturing=None, message=""):
        self.preferences = preferences
        self.screen.fill(settings.BACKGROUND)
        self._centered(self.tr("setting"), 70, self.menu_font, settings.ACCENT_COLOR)
        for index, key in enumerate(("timing", "keys")):
            self._button(self.tab_rect(index), self.tr(key), tab == index)
        if tab == 0:
            for index, (key, label, _, _, _) in enumerate(OPTIONS):
                y = 255 + index * 90
                label = label if index < 2 else self.tr(key)
                self._label(label, 100, y + 8, self.text_font, settings.TEXT_COLOR)
                self._label(self.tr(("das_help", "arr_help", "soft_help", "lock_help")[index]),
                            100, y + 54, self.small_font, settings.MUTED_COLOR)
                self._button(self.setting_minus_rect(index), "−", selected == index)
                value = getattr(preferences, key)
                label = f"{value / FRAME_MS:g} F  /  {value:.1f} ms" if index < 2 else f"{value:g} ms"
                value_font = self.small_font
                self._blit_text(label, value_font, settings.TEXT_COLOR, (686, y + 24), "center")
                self._button(self.setting_plus_rect(index), "+", selected == index)
            self._label(self.tr("language"), 100, 625, self.text_font, settings.TEXT_COLOR)
            self._button(self.language_rect(), "English / 한국어", selected == 4)
            # The active language is visible independently of the toggle label.
            self._centered("English" if preferences.language == "en" else "한국어",
                           686, self.text_font, settings.ACCENT_COLOR)
        else:
            for index, action in enumerate(ACTIONS):
                name = "pause_action" if action == "pause" else "quit_action" if action == "quit" else action
                self._label(self.tr(name), 100, 249 + index * 43,
                            self.small_font, settings.TEXT_COLOR)
                for key_slot in (0, 1):
                    label = self.key_label(preferences.keys[action][key_slot])
                    if capturing == (action, key_slot):
                        label = "…"
                    self._button(self.key_slot_rect(index, key_slot), label,
                                 selected == index and slot == key_slot)
            self._centered(self.tr("key_help"), 696, self.small_font, settings.MUTED_COLOR)
        if capturing:
            self._centered(self.tr("capture"), 731, self.small_font, settings.ACCENT_COLOR)
        elif message:
            self._centered(self.tr(message), 731, self.small_font, (255, 169, 110))
        reset_index = 5 if tab == 0 else len(ACTIONS)
        self._button(self.reset_rect(), self.tr("defaults"), selected == reset_index)
        self._button(self.settings_back_rect(), self.tr("back"), selected == reset_index + 1)

    def wrap_lines(self, label, font, width):
        lines, line = [], ""
        for word in label.split(" "):
            candidate = (line + " " + word).strip()
            if self._measure(candidate,font)[0] > width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        return lines

    def tutorial_layout(self, page):
        key = (self.preferences.language,page)
        if key in self._tutorial_cache:
            return self._tutorial_cache[key]
        _, paragraphs = TUTORIAL[self.preferences.language][page]
        for size in range(23, 16, -1):
            font = self.font(size)
            wrapped = [self.wrap_lines(p, font, settings.WINDOW_WIDTH - 180) for p in paragraphs]
            height = sum(len(lines) * (font.get_linesize() + 8) + 18 for lines in wrapped)
            if height <= 496:
                self._tutorial_cache[key] = (font,wrapped,height)
                return self._tutorial_cache[key]
        return font, wrapped, height

    def draw_tutorial(self, page=0):
        self.screen.fill(settings.BACKGROUND)
        pages = TUTORIAL[self.preferences.language]
        heading, _ = pages[page]
        self._centered(self.tr("tutorial"), 65, self.menu_font, settings.ACCENT_COLOR)
        self._centered(heading, 174, self.title_font, settings.TEXT_COLOR)
        font, paragraphs, _ = self.tutorial_layout(page)
        y = 242
        for lines in paragraphs:
            for line in lines:
                self._label(line, 90, y, font, settings.TEXT_COLOR)
                y += font.get_linesize() + 8
            y += 18
        for index, key in enumerate(("prev", "back", "next_page")):
            self._button(self.tutorial_rect(index), self.tr(key))
        self._centered(f"{page + 1} / {len(pages)}", 830, self.small_font, settings.MUTED_COLOR)

    def shade(self):
        shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        shade.fill((10, 14, 25, 225))
        self.screen.blit(shade, (0, 0))
        self.native_text.dim(225)

    @staticmethod
    def battle_board_rect(index):
        return pygame.Rect(160 + index * 446, 170, 320, 640)

    def _battle_layer(self, board, size):
        visible = tuple(tuple(row) for row in board.grid[settings.HIDDEN_ROWS:])
        key = (size,visible)
        cached = self._board_cache.get(board)
        if cached is not None and cached[0] == key:
            return cached[1]
        if size not in self._grid_cache:
            grid = pygame.Surface(size)
            grid.fill(settings.BOARD_BACKGROUND)
            cell = size[0]//settings.BOARD_COLUMNS
            for x in range(1,settings.BOARD_COLUMNS):
                pygame.draw.line(grid,settings.GRID_COLOR,(x*cell,0),(x*cell,size[1]-1))
            for y in range(1,settings.VISIBLE_ROWS):
                pygame.draw.line(grid,settings.GRID_COLOR,(0,y*cell),(size[0]-1,y*cell))
            self._grid_cache[size] = grid
        layer = self._grid_cache[size].copy()
        cell = size[0]//settings.BOARD_COLUMNS
        for y,row in enumerate(visible):
            for x,kind in enumerate(row):
                if kind is not None:
                    pygame.draw.rect(layer,COLORS[kind],
                                     (x*cell+1,y*cell+1,cell-2,cell-2),border_radius=2)
        self._board_cache[board] = (key,layer)
        return layer

    def _battle_field(self, state, rect):
        cell = rect.width//settings.BOARD_COLUMNS
        self.screen.blit(self._battle_layer(state.board,rect.size),rect.topleft)
        def block(x,y,kind,ghost=False):
            if not settings.HIDDEN_ROWS <= y < settings.BOARD_ROWS:
                return
            target = pygame.Rect(rect.left+x*cell+1,
                                 rect.top+(y-settings.HIDDEN_ROWS)*cell+1,cell-2,cell-2)
            if ghost:
                self.screen.blit(self._ghost_image(kind,target.size,1,0),target.topleft)
            else:
                pygame.draw.rect(self.screen,COLORS[kind],target,border_radius=2)
        if state.active is not None:
            ghost = state.ghost
            active_cells = set(state.active.cells())
            if ghost is not None:
                for x,y in ghost.cells():
                    if (x,y) not in active_cells:
                        block(x,y,state.active.kind,True)
            for x,y in state.active.cells():
                block(x,y,state.active.kind)
        for y in state.clearing_rows:
            if y >= settings.HIDDEN_ROWS:
                flash = pygame.Surface((rect.width,cell),pygame.SRCALPHA)
                alpha = 100 if int(state.clear_timer * 60) % 2 else 190
                flash.fill((235,250,255,alpha))
                self.screen.blit(flash,(rect.left,rect.top+(y-settings.HIDDEN_ROWS)*cell))
        pygame.draw.rect(self.screen,settings.BORDER_COLOR,rect,2)
        if state.perfect_clear_timer > 0:
            self._blit_text(self.tr("perfect"), self.text_font, (255,235,125), rect.center, "center")

    def draw_battle(self, battle):
        self.screen.fill(settings.BACKGROUND)
        for index,side in enumerate(battle.sides):
            rect = self.battle_board_rect(index)
            name = self.tr("you") if index == 0 else "AI / " + self.tr(battle.difficulty)
            self._label(name,rect.left,65,self.title_font,settings.ACCENT_COLOR)
            self._label(f"{self.tr('incoming')} {side.pending}",rect.left,125,
                        self.small_font,settings.TEXT_COLOR)
            self._battle_field(side.state,rect)
            colors = []
            for packet in side.incoming:
                color = (239,104,100) if packet.ready_at <= battle.time else (247,204,95)
                colors.extend([color] * min(packet.count,20-len(colors)))
                if len(colors) >= 20:
                    break
            bar_x = rect.left-12 if index == 0 else rect.right+4
            for segment,color in enumerate(colors):
                pygame.draw.rect(self.screen,color,
                                 (bar_x,rect.bottom-(segment+1)*32+2,8,29))
            self._label(f"{self.tr('score')} {side.state.score}  /  {self.tr('lines')} {side.state.lines}",
                        rect.left,817,self.font(16),settings.TEXT_COLOR)
            self._label(f"{self.tr('sent')} {side.sent}  /  {self.tr('received')} {side.received}",
                        rect.left,840,self.font(16),settings.MUTED_COLOR)
        self._centered(self.format_time(battle.time),110,self.text_font,settings.TEXT_COLOR)
        self._label(self.tr("hold_label"),20,175,self.text_font,settings.ACCENT_COLOR)
        self._draw_preview(battle.player.hold_kind,20,218,120)
        if battle.player.clear_notice_timer > 0:
            self._draw_clear_notice(battle.player,pygame.Rect(20,274,120,110))
        self._label(self.tr("next_label"),491,200,self.text_font,settings.MUTED_COLOR)
        for index,kind in enumerate(battle.player.next_queue):
            self._draw_preview(kind,491,255+index*70,104)
        self._label(self.tr("combo"),20,455,self.small_font,settings.ACCENT_COLOR)
        self._label(str(battle.sides[0].combo),20,488,self.title_font,settings.TEXT_COLOR)
        if battle.sides[0].sent_notice > 0:
            self._label(f"+{battle.sides[0].last_sent}",20,555,
                        self.title_font,(255,223,122))
        if battle.ai.clear_notice_timer > 0:
            self._label(self.tr(battle.ai.last_clear_type),606,35,
                        self.small_font,settings.MUTED_COLOR)

    def draw_pause(self, state, selected=0, battle=None):
        if battle is None:
            self.draw(state)
        else:
            self.draw_battle(battle)
        self.shade()
        self._centered(self.tr("pause"), 135, self.menu_font, settings.ACCENT_COLOR)
        for index, key in enumerate(("resume", "setting", "tutorial", "main_menu")):
            self._button(self.pause_button_rect(index), self.tr(key), selected == index)

    def draw_result(self, state, selected=0, battle=None):
        if battle is None:
            self.draw(state)
            title = "game_over" if state.game_over else state.finish_reason
            seconds = state.elapsed_time
        else:
            self.draw_battle(battle)
            title = {"player":"victory","ai":"defeat","draw":"draw"}[battle.winner]
            seconds = battle.time
        self.shade()
        self._centered(self.tr(title), 98, self.menu_font, settings.ACCENT_COLOR)
        self._centered(f"{self.tr('score')} {state.score}   |   {self.format_time(seconds)}",
                       223, self.text_font, settings.TEXT_COLOR)
        for index, key in enumerate(("retry", "setting", "tutorial", "main_menu")):
            self._button(self.pause_button_rect(index), self.tr(key), selected == index)
