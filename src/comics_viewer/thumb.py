from typing import Optional
from pathlib import Path

from .gi_helpers import Gtk, Gio, GObject, GLib
from .cover_cache import CoverCache
from .utils import refresh_gio_model, image_to_pixbuf, RESOURCE_BASE_DIR
from .archive import Archive


class PageInfo(GObject.GObject):
    def __init__(self, path: Path, page_idx: int):
        super().__init__()
        self.path = path
        self.page_idx = page_idx

    def __hash__(self):
        return hash(self.to_tuple())

    def __eq__(self, other):
        return self.to_tuple() == other.to_tuple()

    def to_tuple(self):
        return (
            self.path,
            self.page_idx,
        )


class Thumb:
    def __init__(self, view, builder: Gtk.Builder,
                 thumb_cache: CoverCache, library: Path):
        self._view = view
        self._library = library
        thumb = builder.get_object("thumb")
        assert isinstance(thumb, Gtk.FlowBox)
        self._thumb = thumb
        self._store = Gio.ListStore()
        self._thumb.bind_model(self._store, self.create_thumb)
        scrolled_window = builder.get_object("thumb_scrolled_window")
        assert isinstance(scrolled_window, Gtk.ScrolledWindow)
        self._scrolled_window = scrolled_window
        self._cache = thumb_cache
        self._archive: Optional[Archive] = None
        self._to_load = []
        self._idle: Optional[GLib.Source] = None
        self._cache.start_idle(self._library, [])
        # set_size_request can change the width/height (orientation)
        self._thumb.connect("child-activated", self._page_activated)

    @property
    def archive(self) -> Optional[Archive]:
        return self._archive

    @archive.setter
    def archive(self, archive: Archive):
        self._archive = archive
        if self._idle is not None:
            self._idle.destroy()
            self._idle = None
        self._to_load = []
        self.refresh_model()

    def ensure_idle(self):
        if self._idle is not None:
            return
        self._idle = GLib.idle_source_new()
        self._idle.set_callback(self.idle)
        self._idle.attach(None)

    def refresh_model(self):
        pages = len(self.archive) if self.archive else 0
        refresh_gio_model(self._store, [
            PageInfo(path=self.archive.path, page_idx=i) for i in range(pages)
        ])

    def create_thumb(self, obj: PageInfo) -> Gtk.Box:
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR / "page_icon.glade"))
        self._to_load.append((obj.page_idx, builder.get_object("img")))
        label = builder.get_object("label")
        assert isinstance(label, Gtk.Label)
        label.set_label(f"{obj.page_idx + 1}")
        self.ensure_idle()
        rv = builder.get_object("box")
        assert isinstance(rv, Gtk.Box)
        rv.page_idx = obj.page_idx  # pyrefly: ignore[missing-attribute]
        return rv

    def idle(self, _) -> int:
        try:
            page_idx, widget = self._to_load.pop(0)
        except IndexError:
            return GLib.SOURCE_REMOVE
        img = self._cache.cover(
            self._library,
            self.archive.path.relative_to(self._library), page_idx)
        widget.set_from_pixbuf(image_to_pixbuf(img))
        self._idle = None
        return GLib.SOURCE_CONTINUE

    def _page_activated(self, _: Gtk.FlowBox, child: Gtk.Bin):
        c = child.get_child()
        assert c is not None
        self._view.page_idx = c.page_idx  # pyrefly: ignore[missing-attribute]

    def scroll_to(self, page_idx):
        child = self._thumb.get_child_at_index(page_idx)
        if child is None:
            return
        self._thumb.select_child(child)
        self._scrolled_window.get_vadjustment().set_value(
            child.get_allocation().y)
