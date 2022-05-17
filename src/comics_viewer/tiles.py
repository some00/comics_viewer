from typing import List, Optional, NewType, Union, Tuple, Callable, Dict
import numpy as np
import numpy.typing as npt
import cairo
from dataclasses import dataclass, field
from contextlib import contextmanager
from enum import IntEnum
from shapely.geometry import MultiPoint, box, Polygon, Point, MultiPolygon
from shapely.strtree import STRtree
from shapely.ops import nearest_points

from .gi_helpers import Gtk
from .cursor import CursorIcon


WidgetPos = NewType("WidgetPos", npt.NDArray)
ImagePos = NewType("ImagePos", Point)
EPSILON = 20  # TODO everything is in image coordinates
RECTANGLE_CURSOR_SIZE = 20  # the first in widget coorditanes


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


class State(IntEnum):
    RECTANGLE = 0
    POINT = 1
    ERASE = 2


STATE_TO_ICON = {
    State.RECTANGLE: CursorIcon.NONE,
    State.POINT: CursorIcon.NONE,
    State.ERASE: CursorIcon.PEN_ERASE,
}


def isclose(a: Point, b: Point):
    return np.isclose(a.x, b.x, atol=3) and np.isclose(a.y, b.y, atol=3)


@dataclass
class Colors:
    erase = html("#ff0000")
    pending = html("#00ff00")
    tile: List[npt.NDArray] = field(default_factory=lambda: [
        html(c) for c in [
            "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
            "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1",
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
            "#000075", "#808080", "#ffffff", "#000000",
        ]
    ])


class WidgetPosCache:
    def __init__(self, transform: Callable,
                 tiles, rect_begin, points):
        self._t = transform

        self._tiles_orig: List[Polygon] = tiles
        self._tiles: Optional[List[List[WidgetPos]]] = None
        self._representative_points: Optional[List[WidgetPos]] = None

        self._rect_begin_orig: ImagePos = rect_begin
        self._rect_begin: Optional[WidgetPos] = None

        self._points_orig: List[ImagePos] = points
        self._points: Optional[List[WidgetPos]] = None

    def invalidate(self):
        self._tiles = None
        self._representative_points = None
        self._rect_begin = None
        self._points = None

    @property
    def tiles(self) -> List[List[WidgetPos]]:
        if self._tiles is None:
            self._tiles = [[self._t(p) for p in t.exterior.coords]
                           for t in self._tiles_orig]
        return self._tiles

    @tiles.setter
    def tiles(self, tiles: List[Polygon]):
        self._tiles_orig = tiles
        self._tiles = None
        self._representative_points = None

    def representative_point(self, idx):
        if self._representative_points is None:
            self._representative_points = [
                self._t(t.representative_point()) for t in self._tiles_orig]
        return self._representative_points[idx]

    @property
    def rect_begin(self) -> WidgetPos:
        if self._rect_begin is None:
            self._rect_begin = self._t(self._rect_begin_orig)
        return self._rect_begin

    @rect_begin.setter
    def rect_begin(self, rect_begin: ImagePos):
        self._rect_begin_orig = rect_begin
        self._rect_begin = None

    @property
    def points(self) -> List[WidgetPos]:
        if self._points is None:
            self._points = [self._t(p) for p in self._points_orig]
        return self._points

    @points.setter
    def points(self, points: List[ImagePos]):
        self._points_orig = points
        self._points = None


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
        self._pen_down = False
        self._snap = True

        # state and related variables
        self._state = State.RECTANGLE
        self._restore: Optional[State] = None
        self._rect_begin: Optional[ImagePos] = None
        self._points: List[Polygon] = []
        self._tree: STRtree = STRtree([])
        self._line_tree: STRtree = STRtree([])
        self._tree_indices: Dict[int, int] = {}
        self._cache = WidgetPosCache(self.transform,
                                     self._tiles,
                                     self._rect_begin,
                                     self._points)
        # start operation
        self._area.connect("draw", self._draw)

    @property
    def tiles(self) -> MultiPolygon:
        return MultiPolygon(self._tiles)

    @tiles.setter
    def tiles(self, tiles: MultiPolygon):
        self.reset()
        self._tiles = list(tiles.geoms)
        self._tiles_changed()
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    def w2i(self, pos: WidgetPos) -> ImagePos:
        return Point(np.flip(self._view.widget_to_img(pos)))

    def i2w(self, pos: ImagePos) -> WidgetPos:
        return self._view.img_to_widget(np.flip(
            np.array(pos.coords).reshape(2)))

    # translate from image to widget
    def transform(self, p: Union[Tuple[float, float], ImagePos]) -> WidgetPos:
        if isinstance(p, tuple):
            p = Point(*p)
        return np.flip(self.i2w(p))

    def _draw(self, area: Gtk.DrawingArea, cr: cairo.Context):
        if not self._show_tiles:  # no display
            return

        cr.select_font_face("monospace", cairo.FontSlant.NORMAL,
                            cairo.FontWeight.BOLD)
        cr.set_font_size(30)
        with save(cr):
            self._draw_tiles(cr)
        cr.new_sub_path()
        with save(cr):
            self._draw_state(cr, self.transform)

    def _draw_tiles(self, cr: cairo.Context):
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
            cr.move_to(*self._cache.tiles[idx][0])
            for p in self._cache.tiles[idx][1:]:
                cr.line_to(*p)
            cr.line_to(*self._cache.tiles[idx][0])
            cr.stroke()
            # label
            cr.move_to(*self._cache.representative_point(idx))
            with save(cr):
                cr.rotate(-self._view.angle)
                cr.show_text(f"{idx + 1}")

    def _draw_state(self, cr: cairo.Context, t: Callable):
        c_orig = self._cursor
        c_snapped = self.snap(self._cursor) if self._cursor else None
        c_widget = t(c_snapped if self._state != State.ERASE else c_orig
                     ) if self._cursor else None

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
            c_orig is not None
        ):
            b, e = self._cache.rect_begin, c_widget
            cr.rectangle(*b, *(e - b))
            cr.stroke()
        elif self._state == State.POINT:
            self._draw_state_point(cr, c_orig, c_snapped, c_widget)

        if self._state == State.RECTANGLE and c_orig:
            if self._snap:
                cr.set_dash([5, 2])
            cr.rectangle(
                *(c_widget - [np.sqrt(RECTANGLE_CURSOR_SIZE * 4)] * 2),
                RECTANGLE_CURSOR_SIZE, RECTANGLE_CURSOR_SIZE)
            cr.stroke()

    def _draw_state_point(self,
                          cr: cairo.Context,
                          c_orig: ImagePos,
                          c_snapped: ImagePos,
                          c_widget: WidgetPos):
        cursor_on_begin: bool = (
            c_orig and self._points and
            isclose(c_snapped, self._points[0])
        )
        begin: Optional[WidgetPos] = None
        # pending points
        if self._points:
            begin = self._cache.points[0]
            end = self._cache._points[-1]
            cr.arc(*begin, 8, 0, np.pi * 2)
            if cursor_on_begin:
                cr.fill()
            else:
                cr.stroke()
            cr.move_to(*begin)
        for point in self._cache.points[1:]:
            cr.line_to(*point)
            cr.stroke()
            cr.arc(*point, 8, 0, np.pi * 2)
            cr.fill()
            cr.move_to(*point)
        # cursor
        if c_orig:
            if cursor_on_begin and len(self._points) > 1:
                cr.move_to(*end)
                cr.line_to(*begin)
                cr.stroke()
            if not cursor_on_begin:
                cr.new_sub_path()
                if self._points:
                    cr.move_to(*end)
                    cr.line_to(*c_widget)
                    cr.stroke()
                if self._snap:
                    cr.set_dash([5, 2])
                cr.arc(*c_widget, 8, 0, np.pi * 2)
                cr.stroke()

    def to_be_erased(self) -> List[int]:
        if (
            not self._state == State.ERASE or
            self._cursor is None or
            self._rect_begin is None
        ):
            return []
        selection = box(*MultiPoint([self._rect_begin, self._cursor]).bounds)
        inside = []
        outside = None
        for tile in self._tree.query(selection):
            if selection.contains(tile):
                inside.append(self._tree_indices[id(tile)])
                continue
            if (
                not inside and
                tile.contains(selection) and
                (outside is None or self._tiles[outside].area > tile.area)
            ):
                outside = self._tree_indices[id(tile)]
        if inside:
            return inside
        if outside is not None:
            return [outside]
        return []

    def snap(self, pos: ImagePos):
        if not self._snap:
            return pos
        cands = []
        distances = []

        def append_point(p: Point):
            cands.append(p)
            distances.append(p.distance(pos))
        if self._rect_begin:
            append_point(self._rect_begin)
        if self._points:
            append_point(self._points[0])
        if self._view.img_shape is not None:
            img = box(*MultiPoint([
                Point(0, 0), np.flip(self._view.img_shape)]
            ).bounds).exterior
            append_point(nearest_points(img, pos)[0])
        if self._tiles:
            tile = self._line_tree.nearest(pos)
            tile_point = nearest_points(tile, pos)[0]
            append_point(tile_point)
        if cands:
            min_idx = np.argmin(distances)
            distance = distances[min_idx]
            if distance < EPSILON / self._view.scale:
                return cands[min_idx]
        return pos

    def queue_draw(self):
        self._show_tiles = True
        self._view.timer.tile(STATE_TO_ICON[self._state])
        self._area.queue_draw()

    def hide_tiles(self, *args):
        if self._show_tiles:
            self._show_tiles = False
            self._area.queue_draw()

    def reset(self):
        self._cursor = None
        self._tiles = []
        self._tree = STRtree([])
        self._line_tree = STRtree([])
        self._tree_indices = {}
        self._dirty = False
        self._motion_timeout = None
        self._tile_timeout = None
        self._show_tiles = False
        if self._state == State.ERASE:
            self._state = State.RECTANGLE
        self._points = []
        self._cache.points = self._points
        self._restore = None
        self._area.queue_draw()

    def clip(self, pos: ImagePos) -> ImagePos:
        return Point(np.clip(*(np.array(a, dtype=np.float64).reshape(2)
                               for a in (pos.coords,
                                         (0, 0),
                                         np.flip(self._view.img_shape)))))

    def _tiles_changed(self):
        self._dirty = True
        self._tree_indices = {id(p): idx for idx, p in enumerate(self._tiles)}
        self._tree = STRtree(self._tiles)
        self._line_tree = STRtree([tile.exterior for tile in self._tiles])
        self._cache.tiles = self._tiles

    def _change_state(self, state: State):
        if state == State.ERASE:
            if self._state != State.ERASE:
                self._restore = self._state
        else:
            self._restore = None
        self._rect_begin = None
        self._cache.rect_begin = None
        self._points = []
        self._cache.points = self._points
        self._state = state

    def toggle_mode(self):
        def toggle(state):
            return State.RECTANGLE if state == State.POINT else State.POINT
        if self._state == State.ERASE:
            pass
        elif self._pen_down:
            self._snap = not self._snap
            self.queue_draw()
        else:
            self._change_state(toggle(self._state))

    def pen_down(self, pos: WidgetPos):
        self._pen_down = True
        self._cursor = self.w2i(pos)
        if self._state == State.RECTANGLE:
            self._rect_begin = self.clip(self._cursor)
            self._cache.rect_begin = self._rect_begin
        elif self._state == State.POINT:
            pos = self.snap(self.clip(self.w2i(pos)))
            if self._points and isclose(pos, self._points[0]):
                if len(self._points) > 2:
                    self._tiles.append(Polygon(self._points))
                    self._tiles_changed()
                    self._points = []
                    self._cache.points = self._points
            else:
                self._points.append(pos)
                self._cache.points = self._points
        self.queue_draw()

    def pen_up(self, pos: WidgetPos):
        self._pen_down = False
        pos = self.snap(self.clip(self.w2i(pos)))
        if self._state == State.RECTANGLE:
            if self._rect_begin is None:
                return
            if not isclose(self._rect_begin, pos):
                self._tiles.append(box(*MultiPoint([self._rect_begin,
                                                    pos]).bounds))
                self._tiles_changed()
        self._cursor = None
        self._rect_begin = None
        self._cache.rect_begin = None
        self.queue_draw()

    def eraser_down(self, pos: WidgetPos):
        self._change_state(State.ERASE)
        self._cursor = self.w2i(pos)
        self._rect_begin = self._cursor
        self._cache.rect_begin = self._rect_begin
        self.queue_draw()

    def eraser_up(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        erase_indices = self.to_be_erased()
        self._tiles = [t for idx, t in enumerate(self._tiles)
                       if idx not in erase_indices]
        if erase_indices:
            self._tiles_changed()
        self._change_state(self._restore)
        self.queue_draw()

    def pen_motion(self, pos: WidgetPos):
        self._cursor = self.w2i(pos)
        self.queue_draw()

    def pen_left(self):
        self._rect_begin = None
        self._cache.rect_begin = None
        self._cursor = None
        self.queue_draw()

    def transformation_changed(self):
        self._cache.invalidate()
