"""Rasterize text at the final window resolution instead of stretching glyphs."""
from collections import OrderedDict
import sys

import pygame


def enable_dpi_awareness():
    """Call before creating the window; older Windows versions use the fallback."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


class NativeText:
    def __init__(self, font_path):
        self.font_path = font_path
        self.viewport = None
        self.scale = None
        self.commands = []
        self.fonts = {}
        self.images = OrderedDict()

    def begin_frame(self, viewport):
        self.commands.clear()
        self.viewport = viewport if viewport.rect.size != viewport.canvas_size else None
        scale = (viewport.rect.width / viewport.canvas_size[0],
                 viewport.rect.height / viewport.canvas_size[1])
        if scale != self.scale:
            self.scale = scale
            self.fonts.clear()
            self.images.clear()

    def draw(self, label, size, color, position, anchor, alpha):
        if self.viewport is None:
            return False
        self.commands.append(("text", label, size, color, position, anchor, alpha))
        return True

    def cover(self, rect):
        # Buttons painted after earlier text must still cover that text.
        if self.viewport is not None:
            self.commands.append(("cover", rect.copy()))

    def dim(self, opacity):
        if self.viewport is not None:
            self.commands = [(*cmd[:-1], round(cmd[-1] * (255 - opacity) / 255))
                             if cmd[0] == "text" else cmd for cmd in self.commands]

    def image(self, label, size, color):
        pixels = max(1, round(size * self.scale[1]))
        key = (pixels, label, tuple(color))
        result = self.images.get(key)
        if result is None:
            if pixels not in self.fonts:
                self.fonts[pixels] = pygame.font.Font(self.font_path, pixels)
            result = self.fonts[pixels].render(label, True, color)
            self.images[key] = result
            if len(self.images) > 256:
                self.images.popitem(last=False)
        else:
            self.images.move_to_end(key)
        return result

    def _point(self, point):
        return (self.viewport.rect.left + round(point[0] * self.scale[0]),
                self.viewport.rect.top + round(point[1] * self.scale[1]))

    def present(self, window):
        if self.viewport is None:
            return
        clip = window.get_clip()
        window.set_clip(self.viewport.rect.clip(clip))
        try:
            # Snapshot opaque button backgrounds before adding any native text.
            covers = {}
            for index, cmd in enumerate(self.commands):
                if cmd[0] == "cover":
                    rect = cmd[1]
                    left, top = self._point(rect.topleft)
                    right, bottom = self._point(rect.bottomright)
                    target = pygame.Rect(left, top, right-left, bottom-top).clip(window.get_rect())
                    covers[index] = (window.subsurface(target).copy(), target.topleft)
            for index, cmd in enumerate(self.commands):
                if cmd[0] == "cover":
                    window.blit(*covers[index])
                    continue
                _, label, size, color, position, anchor, alpha = cmd
                image = self.image(label, size, color)
                if alpha != 255:
                    image = image.copy()
                    image.set_alpha(alpha)
                rect = image.get_rect(**{anchor: self._point(position)})
                window.blit(image, rect)
        finally:
            window.set_clip(clip)
