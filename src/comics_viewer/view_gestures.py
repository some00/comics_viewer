from typing import Optional
import numpy as np
import numpy.typing as npt

from .gi_helpers import Gtk, Gdk


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
        self._drag.connect("cancel", self.drag_cancel)
        self._position_at_begin: Optional[npt.NDArray] = None

        self._swipe = Gtk.GestureSwipe.new(event_box)
        self._swipe.connect("swipe", self.swipe)

        event_box.connect("event", self.event)

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
        self._position_at_begin = self._view.position
        self._start_drag_widget = np.array([start_y, start_x])
        self._start_drag_img = self._view.widget_to_img(
            self._start_drag_widget)
        # self._start_img = self._view.widget_to_img(
        #     np.array([start_y, start_x]))

    def get_offset(self, gesture: Gtk.GestureDrag):
        ok, offset_x, offset_y = gesture.get_offset()
        assert(ok)
        offset = np.array([offset_y, offset_x])

        """
        ok, start_x, start_y = gesture.get_start_point()
        assert(ok)
        start = np.array([start_y, start_x])

        print("debug pos", start_img)
        return np.array([50, 0])
        # start_img = self._view.widget_to_img(start)
        end_img = self._view.widget_to_img(self._start_img + offset)
        rv = end_img - start_img
        rv = self._view.widget_to_img(offset)
        """
        return self._view.widget_to_img(self._start_drag_widget + offset
                                        ) - self._start_drag_img

    def drag_end(self, gesture: Gtk.GestureDrag,
                 offset_x: float, offset_y: float):
        gesture_msg("drag end", offset_x, offset_y)
        offset = self.get_offset(gesture)
        if np.isclose(np.linalg.norm(offset), 0):
            pass
        else:
            self._view.position = self._position_at_begin + offset
        self._position_at_begin = None
        self._start_img = None

    def drag_update(self, gesture: Gtk.GestureDrag,
                    offset_x: float, offset_y: float):
        gesture_msg("drag update")
        offset = self.get_offset(gesture)
        self._view.position = self._position_at_begin + offset

    def drag_cancel(self, gesture: Gtk.GestureDrag,
                    sequence: Optional[Gdk.EventSequence]):
        gesture_msg("drag cancel")

    def swipe(self, gesture: Gtk.GestureSwipe,
              velocity_x: float, velocity_y: float):
        gesture_msg("swipe")

    def event(self, event_box: Gtk.EventBox, event: Gdk.Event):
        return False
        source_device = event.get_source_device()
        if source_device is None:
            return False
        source: Gdk.InputSource = event.get_source_device().get_source()
        if source not in [Gdk.InputSource.PEN, Gdk.InputSource.ERASER]:
            return False
        # ERASER 1 and PEN 1 works on touching the display
        # PEN 2 need proximity only
        # MOTION_NOTIFY indicates proximity reached
        if event.type == Gdk.EventType.LEAVE_NOTIFY:
            # print(event.type)
            pass
        elif event.type == Gdk.EventType.MOTION_NOTIFY:
            # print(event.type)
            pass
        elif event.type == Gdk.EventType.BUTTON_PRESS:
            # print(event.button.button, source)
            pass
        elif event.type == Gdk.EventType.BUTTON_RELEASE:
            # print(event.button.button, source)
            pass
        return True
