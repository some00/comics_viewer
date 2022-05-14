import gi
import importlib
__all__ = []

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
for name in ["Gtk", "GLib", "Gdk", "GObject", "GdkPixbuf", "Gio", "GObject",
             "Rsvg"]:
    module = importlib.import_module(f"gi.repository.{name}")
    globals()[name] = module
    __all__.append(name)
