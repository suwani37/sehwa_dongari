"""Uniform scaling and mouse mapping for a resizable native window."""
import pygame
from tetris import settings


def initial_window_size(desktop=None):
    if desktop is None:
        sizes = pygame.display.get_desktop_sizes()
        desktop = sizes[0] if sizes else (1280,1040)
    return (min(settings.DEFAULT_WINDOW_WIDTH,max(1,desktop[0]-80)),
            min(settings.DEFAULT_WINDOW_HEIGHT,max(1,desktop[1]-80)))


class Viewport:
    def __init__(self, window_size, canvas_size=None):
        self.canvas_size = canvas_size or (settings.WINDOW_WIDTH,settings.WINDOW_HEIGHT)
        self.scaled = None
        self.resize(window_size)

    def resize(self, window_size):
        width,height = (max(1,int(v)) for v in window_size)
        self.window_size = (width,height)
        cw,ch = self.canvas_size
        scale = min(width/cw,height/ch)
        size = (max(1,int(cw*scale)),max(1,int(ch*scale)))
        self.rect = pygame.Rect((width-size[0])//2,(height-size[1])//2,*size)
        if self.scaled is None or self.scaled.get_size()!=size:
            self.scaled = pygame.Surface(size)

    def to_canvas(self, position):
        if not self.rect.collidepoint(position):
            return None
        return (int((position[0]-self.rect.left)*self.canvas_size[0]/self.rect.width),
                int((position[1]-self.rect.top)*self.canvas_size[1]/self.rect.height))

    def present(self, canvas, window):
        if window.get_size() != getattr(self,"window_size",None):
            self.resize(window.get_size())
            self.window_size = window.get_size()
        window.fill(settings.BACKGROUND)
        if canvas.get_size()==self.rect.size:
            window.blit(canvas,self.rect.topleft)
        else:
            pygame.transform.smoothscale(canvas,self.rect.size,self.scaled)
            window.blit(self.scaled,self.rect.topleft)
