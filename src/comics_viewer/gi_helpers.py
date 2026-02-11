import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import Gtk  # noqa: E402
from gi.repository import Gdk  # noqa: E402
from gi.repository import GLib  # noqa: E402
from gi.repository import GObject  # noqa: E402
from gi.repository import GdkPixbuf  # noqa: E402
from gi.repository import Gio  # noqa: E402
from gi.repository import GObject  # noqa: E402
from gi.repository import Rsvg  # noqa: E402

__all__ = [Gtk, Gdk, GLib, GObject, GdkPixbuf, Gio, Rsvg]
