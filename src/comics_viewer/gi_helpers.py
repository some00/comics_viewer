import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Rsvg

__all__ = [Gtk, Gdk, GLib, GObject, GdkPixbuf, Gio, Rsvg]
