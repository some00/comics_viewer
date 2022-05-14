from .gi_helpers import GLib
from .cursor import CursorIcon
from time import time


class ViewTimer:
    def __init__(self,
                 view,
                 tile_timeout: float = 5,
                 cursor_timeout: float = 3):
        self._view = view
        self._tile_timeout = tile_timeout
        self._cursor_timeout = cursor_timeout

        self._enabled = False
        self._tile = time()
        self._cursor = time()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        if not self._enabled and enabled:
            self._tile = time()
            self._cursor = time()
            GLib.timeout_add(1000, self.on_timeout)
        self._enabled = enabled

    def tile(self, icon: CursorIcon):
        self._view.cursor.set_cursor(icon)
        self._tile = time()

    def cursor(self):
        self._view.cursor.set_cursor(CursorIcon.DEFAULT)
        self._cursor = time()

    def on_timeout(self):
        if not self._enabled:
            return
        now = time()
        if abs(now - self._cursor) > self._cursor_timeout:
            self._view.cursor.set_cursor(CursorIcon.NONE)
        if abs(now - self._tile) > self._tile_timeout:
            self._view.tiles.hide_tiles()
        GLib.timeout_add(1000, self.on_timeout)
