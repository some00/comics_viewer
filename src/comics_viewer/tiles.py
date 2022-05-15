from typing import List, Optional, NewType, Union, Tuple, Callable
import numpy as np
import numpy.typing as npt
import cairo
from dataclasses import dataclass, field
from contextlib import contextmanager
from shapely.geometry import MultiPoint, box, Polygon, Point, MultiPolygon
from enum import Enum

from .gi_helpers import Gtk
from .cursor import CursorIcon


WidgetPos = NewType("WidgetPos", npt.NDArray)
ImagePos = NewType("ImagePos", Point)
EPSILON = 20


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


class State(Enum):
    RECTANGLE = CursorIcon.PEN_RECTANGLE
    POINT = CursorIcon.PEN_POINT
    ERASE = CursorIcon.PEN_ERASE


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


class Tiles:
    def __init__(self, view, builder: Gtk.Builder):
        # contants members
        self._area: Gtk.DrawingArea = builder.get_object("view_drawing")
        self._view = view
        self._colors = Colors()

        # model
        self._tiles: List[Polygon] = []
        self._dirty = False

        # display related
        self._show_tiles = False
        self._cursor: Optional[ImagePos] = None

        # state and related variables
        self._state = State.RECTANGLE
        self._restore: Optional[State] = None
        self._rect_begin: Optional[ImagePos] = None
        self._points: List[Point] = []

        # start operation
        self._area.connect("draw", self._draw)

    @property
    def tiles(self) -> MultiPolygon:
        return MultiPolygon(self._tiles)

    @tiles.setter
    def tiles(self, tiles: MultiPolygon):
        self.reset()
        self._tiles = list(tiles.geoms)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def w2i(self, pos: WidgetPos) -> ImagePos:
        return Point(np.flip(self._view.widget_to_img(pos)))

    def i2w(self, pos: ImagePos) -> WidgetPos:
        return self._view.img_to_widget(np.flip(
            np.array(pos.coords).reshape(2)))

    def _draw(self, area: Gtk.DrawingArea, cr: cairo.Context):
        if not self._show_tiles:  # no display
            return

        # translate from image to widget
        def t(p: Union[Tuple[float, float], ImagePos]) -> WidgetPos:
            if isinstance(p, tuple):
                p = Point(*p)
            return np.flip(self.i2w(p))

        cr.select_font_face("monospace", cairo.FontSlant.NORMAL,
                            cairo.FontWeight.BOLD)
        cr.set_font_size(30)
        with save(cr):
            self._draw_tiles(cr, t)
        cr.new_sub_path()
        with save(cr):
            self._draw_state(cr, t)

    def _draw_tiles(self, cr: cairo.Context, t: Callable):
        erase_indices = self.to_be_erased()
        # display tiles
        for idx, tile in enumerate(self._tiles):
            if idx in erase_indices:
                cr.set_source_rgba(*self._colors.erase)
                cr.set_line_width(4)
            else:
                cr.set_source_rgba(
                    *self._colors.tile[idx % len(self._colors.tile)])
                cr.set_line_width(2)
            # contour
            cr.move_to(*t(tile.exterior.coords[0]))
            for p in tile.exterior.coords[1:]:
                cr.line_to(*t(p))
            cr.line_to(*t(tile.exterior.coords[0]))
            cr.stroke()
            # label
            cr.move_to(*t(tile.representative_point()))
            with save(cr):
                cr.rotate(-self._view.angle)
                cr.show_text(f"{idx + 1}")

    def _draw_state(self, cr: cairo.Context, t: Callable):
        # set styling current operation
        if self._state == State.ERASE:
            cr.set_source_rgba(*self._colors.erase)
            cr.set_dash([5, 2])
            cr.set_line_width(1)
        elif self._state in [State.RECTANGLE, State.POINT]:
            cr.set_source_rgba(*self._colors.pending)
            cr.set_line_width(2)
        if (
            self._state in [State.ERASE, State.RECTANGLE] and
            self._rect_begin is not None and
            self._cursor is not None
        ):
            b, e = t(self._rect_begin), t(self._cursor)
            cr.rectangle(*b, *(e - b))
            cr.stroke()
        elif self._state == State.POINT:
            begin: Optional[WidgetPos] = None
            cursor_on_begin: bool = (
                self._cursor and self._points and
                self.snap(self._cursor) == self._points[0]
            )
            # pending points
            if self._points:
                begin = t(self._points[0])
                cr.arc(*begin, 8, 0, np.pi * 2)
                if cursor_on_begin:
                    cr.fill()
                else:
                    cr.stroke()
                cr.move_to(*begin)
            for point in map(t, self._points[1:]):
                cr.line_to(*point)
                cr.stroke()
                cr.arc(*point, 8, 0, np.pi * 2)
                cr.fill()
                cr.move_to(*point)
            # cursor
            if self._cursor:
                if cursor_on_begin and len(self._points) > 1:
                    cr.move_to(*t(self._points[-1]))
                    cr.line_to(*t(self._points[0]))
                    cr.stroke()
                if not cursor_on_begin:
                    cr.new_sub_path()
                    if self._points:
                        cr.move_to(*t(self._points[-1]))
                        cr.line_to(*t(self._cursor))
                        cr.stroke()
                    cr.arc(*t(self._cursor), 8, 0, np.pi * 2)
                    cr.stroke()

    def to_be_erased(self) -> List[int]:
        rv = []
        if (
            not self._state == State.ERASE or
            self._cursor is None or
            self._rect_begin is None
        ):
            return rv
        selection = box(*MultiPoint([self._rect_begin, self._cursor]).bounds)
        for idx, tile in enumerate(self._tiles):
            if selection.contains(tile):
                rv.append(idx)
        if rv:
            return rv
        for idx, tile in enumerate(self._tiles):
            if tile.contains(selection) and (
                not rv or self._tiles[rv[0]].area > tile.area
            ):
                rv = [idx]
        return rv

    def snap(self, pos: ImagePos):
        ref = self._rect_begin or (self._points and self._points[0])
        if ref and pos.distance(ref) < EPSILON / self._view.scale:
            return ref
        return pos

    def queue_draw(self):
        self._show_tiles = True
        self._view.timer.tile(self._state.value)
        self._area.queue_draw()

    def hide_tiles(self, *args):
        if self._show_tiles:
            self._show_tiles = False
            self._area.queue_draw()

    def reset(self):
        self._cursor = None
        self._tiles = []
        self._dirty = False
        self._motion_timeout = None
        self._tile_timeout = None
        self._show_tiles = False
        self._state = State.RECTANGLE
        self._points = []
        self._restore = None
        self._area.queue_draw()

    def clip(self, pos: ImagePos) -> ImagePos:
        return Point(np.clip(*(np.array(a, dtype=np.float64).reshape(2)
                               for a in (pos.coords,
                                         (0, 0),
                                         np.flip(self._view.img_shape)))))

    def _change_state(self, state: State):
        if state == State.ERASE:
            if self._state != State.ERASE:
                self._restore = self._state
        else:
            self._restore = None
        self._rect_begin = None
        self._points = []
        self._state = state

    def toggle_mode(self):
        def toggle(state):
            return State.RECTANGLE if state == State.POINT else State.POINT
        if self._state == State.ERASE:
            return
        self._change_state(toggle(self._state))

    def pen_down(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        if self._state == State.RECTANGLE:
            self._rect_begin = self.clip(self._cursor)
        elif self._state == State.POINT:
            pos = self.snap(self.clip(self.w2i(pos)))
            if self._points and pos == self._points[0]:
                if len(self._points) > 2:
                    self._tiles.append(Polygon(self._points))
                    self._dirty = True
                    self._points = []
            else:
                self._points.append(pos)
        self.queue_draw()

    def pen_up(self, pos: WidgetPos):
        pos = self.snap(self.clip(self.w2i(pos)))
        if self._state == State.RECTANGLE:
            if self._rect_begin is None:
                return
            if self._rect_begin != pos:
                self._tiles.append(box(*MultiPoint([self._rect_begin,
                                                    pos]).bounds))
                self._dirty = True
        self._cursor = None
        self._rect_begin = None
        self.queue_draw()

    def eraser_down(self, pos: WidgetPos):
        self._change_state(State.ERASE)
        self._cursor = self.w2i(pos)
        self._rect_begin = self._cursor
        self.queue_draw()

    def eraser_up(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        erase_indices = self.to_be_erased()
        self._dirty = self._dirty or bool(erase_indices)
        self._tiles = [t for idx, t in enumerate(self._tiles)
                       if idx not in erase_indices]
        self._change_state(self._restore)
        self.queue_draw()

    def pen_motion(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        self.queue_draw()

    def pen_left(self):
        self._rect_begin = None
        self._cursor = None
        self.queue_draw()
