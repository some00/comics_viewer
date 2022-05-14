from typing import List, Optional, NewType
import numpy as np
import numpy.typing as npt
import cairo
from dataclasses import dataclass, field
from time import time
from contextlib import contextmanager

from .gi_helpers import Gtk, GLib


WidgetPos = NewType("WidgetPos", npt.NDArray)
ImagePos = NewType("ImagePos", npt.NDArray)


def html(s: str):
    assert(len(s) in [1 + 6, 1 + 8])
    assert(s[0] == "#")
    s = s[1:]
    r = int(s[:2], base=16)
    g = int(s[2:4], base=16)
    b = int(s[4:6], base=16)
    a = int(s[6:8], base=16) if len(s) == 8 else 255
    return np.array([r, g, b, a]) / 255


@contextmanager
def save(cr: cairo.Context):
    cr.save()
    try:
        yield
    finally:
        cr.restore()


@dataclass
class Colors:
    erase = html("#ff0000")
    normal = html("#ff00ff")
    pending = html("#00ff00")
    tile: List[npt.NDArray] = field(default_factory=lambda: [
        html(c) for c in [
            "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
            "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1",
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
            "#000075", "#808080", "#ffffff", "#000000",
        ]
    ])


@dataclass(init=False)
class Tile:
    tl: ImagePos
    br: ImagePos

    def __init__(self, a, b):
        self.tl = np.array([min(a[0], b[0]), min(a[1], b[1])])
        self.br = np.array([max(a[0], b[0]), max(a[1], b[1])])

    def contains(self, pos: ImagePos):
        return np.all(self.tl <= pos) and np.all(pos <= self.br)

    @property
    def area(self):
        return np.abs((self.br - self.tl).prod())


class Tiles:
    def __init__(self, view, builder: Gtk.Builder):
        self._area: Gtk.DrawingArea = builder.get_object("view_drawing")
        self._view = view

        self._area.connect("draw", self._draw)

        self._show_tiles = False
        self._cursor: Optional[ImagePos] = None
        self._tiles: List[Tile] = []
        self._begin: Optional[ImagePos] = None
        self._erase = False
        self._last_activity: Optional[float] = None

        self._colors = Colors()

        self._inactivity_timer: Optional[GLib.Source] = None

    def w2i(self, pos: WidgetPos) -> ImagePos:
        return self._view.widget_to_img(pos)

    def i2w(self, pos: ImagePos) -> WidgetPos:
        return self._view.img_to_widget(pos)

    def _draw(self, area: Gtk.DrawingArea, cr: cairo.Context):
        if not self._show_tiles:
            return

        def t(p):
            return np.flip(self.i2w(p))

        cr.select_font_face("monospace", cairo.FontSlant.NORMAL,
                            cairo.FontWeight.BOLD)
        cr.set_font_size(30)
        erase_indices = self.to_be_erased()
        for idx, tile in enumerate(self._tiles):
            if idx in erase_indices:
                cr.set_source_rgba(*self._colors.erase)
                cr.set_line_width(4)
            else:
                cr.set_source_rgba(
                    *self._colors.tile[idx % len(self._colors.tile)])
                cr.set_line_width(2)
            tl, br = t(tile.tl), t(tile.br)
            cr.rectangle(*tl, *(br - tl))
            cr.stroke()

            cr.move_to(*(tl + (br - tl) / 2))
            with save(cr):
                cr.rotate(-self._view.angle)
                cr.show_text(f"{idx + 1}")

        if self._erase:
            cr.set_source_rgba(*self._colors.erase)
            cr.set_dash([3, 2])
            cr.set_line_width(1)
        else:
            cr.set_source_rgba(*self._colors.pending)
            cr.set_line_width(2)
        if self._begin is not None and self._cursor is not None:
            tl, br = t(self._begin), t(self._cursor)
            cr.rectangle(*tl, *(br - tl))
        cr.stroke()

    def to_be_erased(self) -> List[int]:
        rv = []
        if not self._erase or self._cursor is None or self._begin is None:
            return rv
        selection = Tile(self._begin, self._cursor)
        for idx, tile in enumerate(self._tiles):
            if selection.contains(tile.tl) and selection.contains(tile.br):
                rv.append(idx)
        if rv:
            return rv
        for idx, tile in enumerate(self._tiles):
            if (
                tile.contains(selection.tl) and tile.contains(selection.br) and
                (not rv or self._tiles[rv[0]].area > tile.area)
            ):
                rv = [idx]
        return rv

    def _start_timer(self, restart=False):
        if not restart:
            self._last_activity = time()
        if self._inactivity_timer is None or restart:
            return  # TODO disabled for now
            self._inactivity_timer = GLib.timeout_source_new_seconds(1)
            self._inactivity_timer.set_callback(self._on_inactivity_timeout)
            self._inactivity_timer.attach()

    def _on_inactivity_timeout(self, arg):
        if self._last_activity - time() > 8:
            self._show_tiles = False
            self._area.queue_draw()
        else:
            self._start_timer(restart=True)

    def queue_draw(self):
        self._show_tiles = True
        self._start_timer()
        self._area.queue_draw()

    def hide_tiles(self, *args):
        if self._inactivity_timer is not None:
            self._inactivity_timer.destroy()
            self._inactivity_timer = None
        if self._show_tiles:
            self._show_tiles = False
            self._area.queue_draw()

    def reset(self):
        if self._inactivity_timer is not None:
            self._inactivity_timer.destroy()
            self._inactivity_timer = None
        self._cursor = None
        self._tiles = []
        self._motion_timeout = None
        self._tile_timeout = None
        self._show_tiles = False
        self._last_activity = None
        self._erase = False
        self._area.queue_draw()

    def clip(self, pos: ImagePos):
        return np.clip(pos, [0, 0], self._view.img_shape)

    def pen_down(self, pos: WidgetPos):
        self._begin = self.clip(self.w2i(pos))
        self._cursor = self._begin
        self._erase = False
        self.queue_draw()

    def pen_up(self, pos: WidgetPos):
        self._erase = False
        if self._begin is None:
            return
        a = self._begin
        b = self.clip(self.w2i(pos))
        if not np.all(np.isclose(a, b)):
            self._tiles.append(Tile(a, b))
        self._cursor = None
        self._begin = None
        self.queue_draw()

    def eraser_down(self, pos: WidgetPos):
        self._begin = self.clip(self.w2i(pos))
        self._cursor = self._begin
        self._erase = True
        self.queue_draw()

    def eraser_up(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        erase_indices = self.to_be_erased()
        self._tiles = [t for idx, t in enumerate(self._tiles)
                       if idx not in erase_indices]
        self._erase = False
        self.queue_draw()

    def pen_motion(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        self._start_timer()
        self.queue_draw()

    def pen_left(self):
        self._begin = None
        self._cursor = None
        self.queue_draw()
