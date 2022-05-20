from typing import Optional
from enum import Enum
from contextlib import ExitStack

from .gi_helpers import Gtk, Gio, GLib, Gdk
from .library import Library
from .view import View
from .manage import Manage
from .utils import RESOURCE_BASE_DIR
from .cursor import CursorIcon


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
        self.statusbar = builder.get_object("statusbar_scrolled")
        self.thumb_scrolled_window = builder.get_object(
            "thumb_scrolled_window")
        self.switcher = builder.get_object("switcher")
        builder.get_object("stack").connect("notify::visible-child-name",
                                            self.visible_child_changed)

        self._library = self._create_library(builder=builder,
                                             add_action=self.add_action,
                                             app=self)
        self._view = self._stack.enter_context(
            self._create_view(builder=builder,
                              app=self,
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
        if True:
            import cProfile
            self._pr_enabled = False
            self._pr = cProfile.Profile()
            profiler = Gio.SimpleAction.new("toggle-profiler", None)
            profiler.connect("activate", lambda *x: self.toggle_profiler())
            self.profiler = profiler
            self.add_action(profiler)
            self.set_accels_for_action("app.toggle-profiler", ["p"])

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
        self.set_accels_for_action("app.edit-with-mouse", ["m"])

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
                self.statusbar.hide()
                self.thumb_scrolled_window.hide()
                self.switcher.hide()
                self.window.fullscreen()
            else:
                self.statusbar.show()
                self.thumb_scrolled_window.show()
                self.switcher.show()
                self.window.unfullscreen()
        self.fs.set_state(GLib.Variant.new_boolean(self.fullscreen))

    def configure_event(self, widget, event):
        self.change_fullscreen(self.fullscreen)

    def change_fullscreen(self, fs: bool):
        self.fs.change_state(GLib.Variant.new_boolean(fs))

    def view_comics(self, *args, **kwargs):
        if self._view.load(*args, **kwargs):
            self.stack.set_visible_child_name("view")

    def visible_child_changed(self, stack, param):
        name = stack.get_visible_child_name()
        if name == StackName.manage.value:
            self.disable_view()
            self._manage.refresh()
        elif name == StackName.view.value:
            self.area.grab_focus()
            self.area.queue_render()
        elif name == StackName.library.value:
            self.disable_view()
            self._library.refresh_models()
        else:
            raise RuntimeError("unknown stack child")

    def disable_view(self):
        self._view.timer.enabled = False
        self._view.cursor.set_cursor(CursorIcon.DEFAULT)

    def toggle_profiler(self):
        import time
        self._pr_enabled = not self._pr_enabled
        if self._pr_enabled:
            print("profiler started")
            self._pr_start = time.time()
            self._pr.enable()
        else:
            self._pr.disable()
            import pstats
            ps = pstats.Stats(self._pr).sort_stats("tottime")
            ps.print_stats()
            print(time.time() - self._pr_start)
