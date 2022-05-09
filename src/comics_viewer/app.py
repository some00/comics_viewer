from typing import Optional
from enum import Enum
from contextlib import ExitStack

from .gi_helpers import Gtk, Gio, GLib, Gdk
from .library import Library
from .view import View
from .manage import Manage
from .utils import RESOURCE_BASE_DIR


class StackName(Enum):
    manage = "manage"
    library = "library"
    view = "view"


class App(Gtk.Application):
    def __init__(self, stack: ExitStack, create_library,
                 create_view, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_library = create_library
        self._create_view = create_view
        self._library: Optional[Library] = None
        self._view: Optional[View] = None
        self._manage: Optional[Manage] = None
        self._stack = stack
        self.window: Optional[Gtk.ApplicationWindow] = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR / "layout.glade"))
        self.area = builder.get_object("view")
        self.window = builder.get_object("window")
        self.add_window(self.window)
        self.stack = builder.get_object("stack")
        builder.get_object("stack").connect("notify::visible-child-name",
                                            self.visible_child_changed)

        self._library = self._create_library(builder=builder,
                                             add_action=self.add_action,
                                             app=self)
        self._view = self._stack.enter_context(
            self._create_view(builder=builder,
                              add_action=self.add_action,
                              library=self._library)
        )
        self._manage = Manage(self._library, builder, self.add_action)

        lw = self._library.last_viewed
        if lw is None:
            self.stack.set_visible_child_name("library")
        else:
            self.view_comics(self._library.path, lw, lw.progress.page_idx)

        quit = Gio.SimpleAction.new("quit", None)
        quit.connect("activate", lambda *x: self.quit())
        self.add_action(quit)

        self.fs = Gio.SimpleAction.new_stateful(
            "fullscreen", None, GLib.Variant.new_boolean(self.fullscreen))
        self.fs.connect("change-state", self.set_fullscreen)
        self.window.connect("configure-event", self.configure_event)
        self.add_action(self.fs)

        self.set_accels_for_action("app.quit", ["<Control>w"])
        self.set_accels_for_action("app.fullscreen", ["<Control>f"])
        self.set_accels_for_action("app.copy-title-manage", ["<Control>c"])
        self.set_accels_for_action("app.paste-title-manage", ["<Control>v"])
        self.set_accels_for_action("app.save-manage", ["<Control>s"])
        self.set_accels_for_action("app.prev-page", ["Left"])
        self.set_accels_for_action("app.next-page", ["Right", "space"])

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

    def view_comics(self, *args, **kwargs):
        if self._view.load(*args, **kwargs):
            self.stack.set_visible_child_name("view")

    def visible_child_changed(self, stack, param):
        name = stack.get_visible_child_name()
        if name == StackName.manage.value:
            self._manage.refresh()
        elif name == StackName.view.value:
            self.area.grab_focus()
            self.area.queue_render()
        elif name == StackName.library.value:
            self._library.refresh_models()
        else:
            raise RuntimeError("unknown stack child")
