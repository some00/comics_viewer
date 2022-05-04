from typing import Optional
from pathlib import Path
import os
from collections import namedtuple

from .gi_helpers import Gtk, Gdk
from .in_mem_cache import InMemCache


StatusBar = namedtuple("StatusBar", ["bar", "filename", "pagename",
                                     "progress", "progress_bar"])


class View:
    def __init__(self, area: Gtk.GLArea, status_bar: StatusBar,
                 max_cache: int = 64 * 1024 * 1024):
        self._area = area
        self.status_bar = status_bar

        self._comics: Optional[Path] = None
        self._page: Optional[int] = None
        self._in_mem = InMemCache(max_cache)

        """
        # TODO test
        self.status_bar.filename.set_label("ada")
        self.status_bar.pagename.set_label("asd")
        percent = 0.5
        self.status_bar.progress.set_label(f"1/2 ({percent * 100:.0f})%")
        self.status_bar.progress_bar.set_fraction(0.5)
        """

        self._area.set_double_buffered(
            int(os.environ.get("COMICS_VIEWER_DOUBLE_BUFFERED", 1)))
        self._area.connect("render", self._render)

    @property
    def comics(self) -> Optional[Path]:
        return self._comics

    @comics.setter
    def comics(self, comics):
        self._page = None
        self._comics = comics
        # TODO start/stop caching
        # TODO status

    @property
    def page(self) -> Optional[int]:
        # TODO status
        return self._page

    @page.setter
    def page(self, page):
        self._page = page

    def _render(self, area: Gtk.GLArea, context: Gdk.GLContext):
        pass
