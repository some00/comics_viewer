from typing import Optional
import numpy as np
from collections import namedtuple

from .utils import is_in
from .gi_helpers import Gtk, Gdk


DragData = namedtuple("DragData", [
    "start_pos",
    "affine",
    "start_widget",
    "start_img",
])


def gesture_msg(*args, **kwargs):
    return
    print(*args, **kwargs)


class ViewGestures:
    def __init__(self, view, builder: Gtk.Builder):
        self._view = view
        event_box = builder.get_object("view_event_box")

        self._zoom = Gtk.GestureZoom.new(event_box)
        self._zoom.connect("begin", self.zoom_begin)
        self._zoom.connect("cancel", self.zoom_cancel)
        self._zoom.connect("end", self.zoom_end)
        self._zoom.connect("scale-changed", self.zoom_scale_changed)
        self._scale_at_begin: Optional[float] = None

        self._drag = Gtk.GestureDrag.new(event_box)
        self._drag.connect("drag-begin", self.drag_begin)
        self._drag.connect("drag-end", self.drag_end)
        self._drag.connect("drag-update", self.drag_update)
        self._drag_data: Optional[DragData] = None

        self._swipe = Gtk.GestureSwipe.new(event_box)
        self._swipe.connect("swipe", self.swipe)

        event_box.connect("motion-notify-event", self.motion_notify)
        event_box.connect("leave-notify-event", self.leave_notify)
        event_box.connect("button-press-event", self.button_press)
        event_box.connect("button-release-event", self.button_release)
        # ERASER 1 and PEN 1 works on touching the display
        # PEN 2 need proximity only
        # MOTION_NOTIFY indicates proximity reached

    def zoom_begin(self, gesture: Gtk.GestureZoom,
                   sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom begin")
        self._scale_at_begin = self._view.scale

    def zoom_cancel(self, gesture: Gtk.GestureZoom,
                    sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom cancel")
        if self._scale_at_begin is not None:
            self._view.scale = self._scale_at_begin

    def zoom_end(self, gesture: Gtk.GestureZoom,
                 sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom end")
        self._scale_at_begin = None

    def zoom_scale_changed(self, gesture: Gtk.GestureZoom,
                           sequence: Optional[Gdk.EventSequence]):
        gesture_msg("zoom scale changed")
        self._view.scale = self._scale_at_begin * gesture.get_scale_delta()

    def drag_begin(self, gesture: Gtk.GestureDrag,
                   start_x: float, start_y: float):
        gesture_msg("drag begin")
        start = np.array([start_y, start_x])
        self._drag_data = DragData(
            start_pos=self._view.position,
            affine=self._view.affine(),
            start_widget=start,
            start_img=self._view.widget_to_img(start, self._view.affine()),
        )

    def drag_update(self, gesture: Gtk.GestureDrag,
                    offset_x: float, offset_y: float):
        gesture_msg("drag update")
        offset = np.array([offset_y, offset_x])
        self._view.position = self._drag_data.start_pos - (
            self._view.widget_to_img(
                self._drag_data.start_widget + offset,
                self._drag_data.affine) - self._drag_data.start_img
        )

    def drag_end(self, gesture: Gtk.GestureDrag,
                 offset_x: float, offset_y: float):
        gesture_msg("drag end", offset_x, offset_y)
        self._drag_data = None

    def swipe(self, gesture: Gtk.GestureSwipe,
              velocity_x: float, velocity_y: float):
        gesture_msg("swipe")

    def pen_event(self):
        event = Gtk.get_current_event()
        source_device = event.get_source_device()
        if source_device is None:
            return False
        return source_device.get_source() in [
            Gdk.InputSource.PEN, Gdk.InputSource.ERASER,
        ]

    def motion_notify(self, event_box: Gtk.EventBox, event: Gdk.EventMotion):
        if not self.pen_event():
            return False
        pos = is_in(event_box, event.x, event.y)
        if pos is None:
            return False
        """
        self._view._status.comics.set_label(str(self._view.widget_to_img(
            pos).astype(int)))
        """
        return True

    def leave_notify(self, event_box, event):
        return self.pen_event()

    def button_press(self, event_box, event):
        return self.pen_event()

    def button_release(self, event_box, event):
        return self.pen_event()
