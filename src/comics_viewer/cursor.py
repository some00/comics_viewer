from typing import Dict, Tuple, List, Optional
from pathlib import Path
from enum import Enum
import cairo
import numpy as np
from contextlib import contextmanager
from collections import defaultdict
from shapely.geometry import MultiPoint

from .gi_helpers import Gdk, Gtk, Rsvg, GdkPixbuf
from .utils import RESOURCE_BASE_DIR


class CursorIcon(Enum):
    PEN_RECTANGLE = RESOURCE_BASE_DIR / "pen-rect.svg"
    PEN_POINT = RESOURCE_BASE_DIR / "pen-point.svg"
    PEN_ERASE = RESOURCE_BASE_DIR / "pen-erase.svg"
    DEFAULT = "default"
    NONE = "none"


@contextmanager
def svg_handle(path: Path):
    handle = Rsvg.Handle.new_from_file(str(path))
    try:
        yield handle
    finally:
        handle.close()


class Cursor:
    def __init__(self, builder: Gtk.Builder, view):
        self._view = view
        self.gtk_window: Gtk.Window = builder.get_object("window")
        self._cursors: Dict[
            CursorIcon, List[Tuple[Gdk.Cursor, Optional[float]]]
        ] = defaultdict(list)

    @property
    def gdk_window(self) -> Gdk.Window:
        return self.gtk_window.get_window()

    @property
    def gdk_display(self) -> Gdk.Display:
        return self.gdk_window.get_display()

    def _get_cursor(self, icon: CursorIcon) -> Gdk.Cursor:
        for cursor, angle in self._cursors[icon]:
            if angle is None or np.isclose(self._view.angle, angle):
                return cursor
        assert(isinstance(icon.value, (Path, str)))
        if isinstance(icon.value, Path):
            cursor = self._create_cursor(icon.value)
            self._cursors[icon].append((cursor, self._view.angle))
            return cursor
        elif isinstance(icon.value, str):
            cursor = Gdk.Cursor.new_from_name(self.gdk_display, icon.value)
            self._cursors[icon].append((cursor, None))

    def set_cursor(self, icon: CursorIcon):
        self.gdk_window.set_cursor(self._get_cursor(icon))

    def _create_cursor(self, svg: Path):
        w, h = (self.gdk_display.get_default_cursor_size(),) * 2
        with svg_handle(svg) as handle:
            img = np.zeros((h, w, 4), dtype=np.uint8)
            fmt = cairo.Format.ARGB32
            stride = fmt.stride_for_width(w)
            assert(stride == w * 4)
            # NOTE: F endian and alignment
            with cairo.ImageSurface.create_for_data(
                memoryview(img), fmt, w, h, stride
            ) as s:
                cr = cairo.Context(s)
                rect = self._view.rotate(np.array([w, h]))
                cr.rotate(self._view.angle)
                vp = Rsvg.Rectangle()
                vp.y, vp.x = 0, 0
                vp.height, vp.width = rect[1], rect[0]
                handle.render_document(cr, vp)
            img = img[..., [2, 1, 0, 3]].copy()  # BGRA2RGBA
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                data=img.tobytes(),
                colorspace=GdkPixbuf.Colorspace.RGB,
                has_alpha=True,
                bits_per_sample=8,
                width=img.shape[1],
                height=img.shape[0],
                rowstride=img.shape[1] * 4)
            return Gdk.Cursor.new_from_pixbuf(
                self.gdk_display,
                pixbuf,
                *MultiPoint([np.zeros(2), rect]).bounds[2:]
            )
