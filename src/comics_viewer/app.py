from typing import Optional
from pathlib import Path
from .gi_helpers import Gtk, Gio, GLib, Gdk
from .library import Library
from .view import View, StatusBar
from .manage import Manage

RESOURCE_BASE_DIR = Path(__file__).parent


class App(Gtk.Application):
    def __init__(self, library: Library, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._library = library
        self._view: Optional[View] = None
        self._manage: Optional[Manage] = None
        self.window: Optional[Gtk.ApplicationWindow] = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR / "layout.glade"))
        self._view = View(
            area=builder.get_object("view"),
            status_bar=StatusBar(
                filename=builder.get_object("filename"),
                progress=builder.get_object("progress"),
                pagename=builder.get_object("pagename"),
                bar=builder.get_object("statusbar"),
                progress_bar=builder.get_object("progress_bar"))
        )
        self.window = builder.get_object("window")
        self.stack = builder.get_object("stack")

        self._library.view = builder.get_object("library_view")
        self.library = builder.get_object("library")
        self.library.bind_model(self._library.list_store,
                                self._library.create_comics_box)
        self.add_window(self.window)
        self._manage = Manage(self._library, builder, self.add_action)

        lw = self._library.last_viewed
        if lw is None:
            self.stack.set_visible_child_name("library")
        else:
            self._view.comics, self._view.page = lw

        quit = Gio.SimpleAction.new("quit", None)
        quit.connect("activate", lambda *x: self.quit())
        self.add_action(quit)

        self.fs = Gio.SimpleAction.new_stateful(
            "fullscreen", None, GLib.Variant.new_boolean(self.fullscreen))
        self.fs.connect("change-state", self.set_fullscreen)
        self.window.connect("configure-event", self.configure_event)
        self.add_action(self.fs)

        add_collection = Gio.SimpleAction.new("add-collection", None)
        add_collection.connect("activate", self._library.add_collection_dialog)
        self.add_action(add_collection)

        self._library.remove_collection = Gio.SimpleAction.new(
            "remove-collection", None)
        self._library.remove_collection.set_enabled(False)
        self.add_action(self._library.remove_collection)

        self._library.refresh = Gio.SimpleAction.new("refresh-library", None)
        self.add_action(self._library.refresh)

        self.add_accelerator("<Control>w", "app.quit", None)
        self.add_accelerator("f", "app.fullscreen", None)
        self.add_accelerator("<Control>c", "app.copy-title-manage", None)
        self.add_accelerator("<Control>v", "app.paste-title-manage", None)
        self.add_accelerator("<Control>s", "app.save-manage", None)
        self._library.start_refresh()

    def do_activate(self):
        self.window.present()

    @property
    def fullscreen(self):
        return bool(
            self.window and
            self.window.get_window() and
            self.window.get_window().get_state() & Gdk.WindowState.FULLSCREEN
        )

    def set_fullscreen(self, action, value):
        if self.window:
            if value.get_boolean():
                self.window.fullscreen()
                # TODO doesn't run on set_state
                # self._view.status_bar.bar.hide()
                # TODO task switcher
            else:
                # TODO doesn't run on set_state
                # self._view.status_bar.bar.show()
                # TODO task switcher
                self.window.unfullscreen()
        self.fs.set_state(GLib.Variant.new_boolean(self.fullscreen))

    def configure_event(self, widget, event):
        self.fs.set_state(GLib.Variant.new_boolean(self.fullscreen))
