from typing import Optional
import numpy as np
from collections import namedtuple
import numpy.typing as npt
from enum import Enum

from .utils import is_in
from .gi_helpers import Gtk, Gdk
from .cursor import Cursor, CursorIcon

# ERASER 1 and PEN 1 works on touching the display
# PEN 2 need proximity only
# MOTION_NOTIFY indicates proximity reached
# PEN 1 will still be generated if PEN 2 is pressed

DragData = namedtuple("DragData", [
    "start_pos",
    "affine",
    "start_widget",
    "start_img",
])


def event_source_type() -> Optional[Gdk.InputSource]:
    event = Gtk.get_current_event()
    source_device = event.get_source_device()
    if source_device is None:
        return None
    return source_device.get_source()


def dec_event_handler(func):
    def wrapper(self, *args, _func=func, **kwargs):
        source = event_source_type()
        if source is None or source not in [
            Gdk.InputSource.PEN, Gdk.InputSource.ERASER,
            Gdk.InputSource.TOUCHSCREEN,
        ]:
            self._view.timer.cursor()
        filter_in = [Gdk.InputSource.PEN, Gdk.InputSource.ERASER]
        if self.edit_with_mouse:
            filter_in.append(Gdk.InputSource.MOUSE)

        if source is None or source not in filter_in:
            return False
        return _func(self, *args, **kwargs)
    return wrapper


class Direction(Enum):
    up = -np.pi / 2
    down = np.pi / 2
    left = np.pi
    right = 0


def gesture_msg(*args, **kwargs):
    return
    print(*args, **kwargs)


class ViewGestures:
    def __init__(self, view, builder: Gtk.Builder):
        self._view = view
        event_box = builder.get_object("view_event_box")
        self.window = builder.get_object("window")

        self._zoom = Gtk.GestureZoom.new(event_box)
        self._zoom.connect("begin", self.zoom_begin)
        self._zoom.connect("end", self.zoom_end)
        self._zoom.connect("scale-changed", self.zoom_scale_changed)
        self._scale_at_begin: Optional[float] = None
        self._position_at_begin: Optional[npt.NDArray] = None

        self._drag = Gtk.GestureDrag.new(event_box)
        self._drag.connect("drag-begin", self.drag_begin)
        self._drag.connect("drag-end", self.drag_end)
        self._drag.connect("drag-update", self.drag_update)
        self._drag_data: Optional[DragData] = None

        self._swipe = Gtk.GestureSwipe.new(event_box)
        self._swipe.connect("swipe", self.swipe)

        event_box.connect("motion-notify-event", self.motion_notify)
        event_box.connect("button-press-event", self.button_press)
        event_box.connect("button-release-event", self.button_release)
        event_box.connect("leave-notify-event", self.leave_notify_event)

        self._edit_with_mouse = False

        def disable_timer(*x):
            self._view.timer.enabled = False
            self._view.cursor.set_cursor(CursorIcon.DEFAULT)
        event_box.connect(
            "leave-notify-event",
            lambda *x: self._view.cursor.set_cursor(CursorIcon.DEFAULT)
        )

        def enable_timer(*x):
            self._view.timer.enabled = True
        event_box.connect("enter-notify-event", enable_timer)

    @property
    def edit_with_mouse(self) -> bool:
        return self._edit_with_mouse

    @edit_with_mouse.setter
    def edit_with_mouse(self, edit_with_mouse):
        self._edit_with_mouse = edit_with_mouse

    def zoom_begin(self, gesture: Gtk.GestureZoom,
                   sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom begin")
        self._scale_at_begin = self._view.scale
        self._position_at_begin = self._view.position

    def zoom_end(self, gesture: Gtk.GestureZoom,
                 sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom end")
        self._scale_at_begin = None
        self._position_at_begin = None

    def zoom_scale_changed(self, gesture: Gtk.GestureZoom,
                           sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom scale changed")
        self._view.scale = self._scale_at_begin * gesture.get_scale_delta()
        self._view.position = self._position_at_begin

    def drag_begin(self, gesture: Gtk.GestureDrag,
                   start_x: float, start_y: float):
        gesture_msg("drag begin")
        start = np.array([start_x, start_y])
        self._drag_data = DragData(
            start_pos=self._view.position,
            affine=self._view.affine(),
            start_widget=start,
            start_img=self._view.widget_to_img(start, self._view.affine()),
        )

    def drag_update(self, gesture: Gtk.GestureDrag,
                    offset_x: float, offset_y: float):
        gesture_msg("drag update")
        offset = np.array([offset_x, offset_y])
        self._view.position = self._drag_data.start_pos - (
            self._view.widget_to_img(
                self._drag_data.start_widget + offset,
                self._drag_data.affine) - self._drag_data.start_img
        )

    def drag_end(self, gesture: Gtk.GestureDrag,
                 offset_x: float, offset_y: float):
        gesture_msg("drag end", offset_x, offset_y)
        self._drag_data = None
        if not np.isclose(np.linalg.norm(np.array([offset_x, offset_y])), 0):
            return
        _, start_x, start_y = gesture.get_start_point()
        x = abs(self._view.rotate(np.array([start_x, start_y]))[1])
        w = self._view.rotate(self._view.viewport)[1]
        threshold = abs(w / 8)
        if x < threshold:
            self._view.page_idx -= int(np.sign(w))
        elif x > abs(w) - threshold:
            self._view.page_idx += int(np.sign(w))

    def swipe(self, gesture: Gtk.GestureSwipe,
              velocity_x: float, velocity_y: float):
        gesture_msg("swipe")
        if not np.isclose(self._view.scale, 1):
            return
        velocity = self._view.rotate(np.array([velocity_y, velocity_x]))
        if np.linalg.norm(velocity) < 100:
            return
        angle = np.arctan2(*velocity)
        directions = list(Direction.__members__.items())
        diffs = [np.abs(angle - ref.value) for _, ref in directions]
        cand = np.argmin(diffs)
        if abs(diffs[cand]) > 35 * np.pi / 180:
            return
        direction = directions[cand][1]
        if direction == Direction.up:
            self._view.app.change_fullscreen(True)
        elif direction == Direction.down:
            self._view.app.change_fullscreen(False)
        elif direction == Direction.left:
            self._view.page_idx += 1
        elif direction == Direction.right:
            self._view.page_idx -= 1

    @property
    def tiles(self):
        return self._view.tiles

    @property
    def cursor(self) -> Cursor:
        return self._view.cursor

    @dec_event_handler
    def motion_notify(self, event_box: Gtk.EventBox,
                      event: Gdk.EventMotion) -> bool:
        pos = is_in(event_box, event.x, event.y)
        if pos is None:
            return False
        self.tiles.pen_motion(pos)
        return True

    @dec_event_handler
    def leave_notify_event(self, event_box: Gtk.EventBox,
                           event: Gdk.EventCrossing):
        self.tiles.pen_left()
        return False

    @dec_event_handler
    def button_press(self, event_box: Gtk.EventBox,
                     event: Gdk.EventButton) -> bool:
        pos = is_in(event_box, event.x, event.y)
        if pos is None:
            return False
        source = event_source_type()
        if source == Gdk.InputSource.PEN:
            if event.button == 1:
                self.tiles.pen_down(pos)
        elif source == Gdk.InputSource.ERASER:
            self.tiles.eraser_down(pos)
        elif source == Gdk.InputSource.MOUSE:
            if event.button == 1:
                self.tiles.pen_down(pos)
            elif event.button == 3:
                self.tiles.eraser_down(pos)
        return True

    @dec_event_handler
    def button_release(self, event_box: Gtk.EventBox,
                       event: Gdk.EventButton) -> bool:
        pos = is_in(event_box, event.x, event.y)
        if pos is None:
            return False
        source = event_source_type()
        if source == Gdk.InputSource.PEN:
            if event.button == 1:
                self.tiles.pen_up(pos)
            elif event.button == 2:
                self.tiles.toggle_mode()
        elif source == Gdk.InputSource.ERASER:
            self.tiles.eraser_up(pos)
        elif source == Gdk.InputSource.MOUSE:
            if event.button == 1:
                self.tiles.pen_up(pos)
            elif event.button == 2:
                self.tiles.toggle_mode()
            elif event.button == 3:
                self.tiles.eraser_up(pos)
        return True
