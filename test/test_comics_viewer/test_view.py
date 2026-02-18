import pytest
from typing import Callable, Optional
from comics_viewer.view import View
from comics_viewer.gi_helpers import Gtk, Gio
from comics_viewer.library import Library
from comics_viewer.app import App
from comics_viewer.cover_cache import CoverCache
from dataclasses import dataclass, fields, field
from OpenGL.arrays.vbo import VBO
from unittest.mock import MagicMock


@dataclass(frozen=True)
class MockOGL:
    glGenVertexArrays: Callable
    glBindVertexArray: Callable
    glDeleteVertexArrays: Callable
    glDeleteShader: Callable
    glDeleteProgram: Callable
    glGenTextures: Callable
    glBindTexture: Callable
    glTexParameteri: Callable
    glTexImage2D: Callable
    glGenerateMipmap: Callable
    glDeleteTextures: Callable
    glClearColor: Callable
    glClear: Callable
    glGetIntegeri_v: Callable
    glUniformMatrix4fv: Callable
    glDrawElements: Callable
    glFlush: Callable
    glPixelStorei: Callable
    glVertexAttribPointer: Callable
    glEnableVertexAttribArray: Callable
    glGetUniformLocation: Callable


@pytest.fixture
def ogl(mocker) -> MockOGL:
    kwargs = {}
    for field in fields(MockOGL):
        kwargs[field.name] = mocker.patch(
                f"comics_viewer.view.OGL.{field.name}")
    return MockOGL(**kwargs)


@pytest.fixture
def vbo(mocker) -> VBO:
    return mocker.patch("comics_viewer.view.vbo.VBO", spec=VBO)


@dataclass(frozen=True)
class MockShaders:
    compileShader: Callable
    compileProgram: Callable


@pytest.fixture
def shaders(mocker) -> MockShaders:
    return MockShaders(
        compileProgram=mocker.patch(
            "comics_viewer.view.shaders.compileProgram"),
        compileShader=mocker.patch(
            "comics_viewer.view.shaders.compileShader"),
    )


def mm(spec):
    return field(default_factory=lambda: MagicMock(spec=spec))


@dataclass(frozen=True)
class MockObjects:
    view: MagicMock = mm(Gtk.GLArea)
    window: MagicMock = mm(Gtk.ApplicationWindow)
    statusbar: MagicMock = mm(Gtk.Box)
    comics: MagicMock = mm(Gtk.Label)
    progress: MagicMock = mm(Gtk.Label)
    pagename: MagicMock = mm(Gtk.Label)
    progress_bar: MagicMock = mm(Gtk.ProgressBar)
    img_shape: MagicMock = mm(Gtk.Label)
    encoded_size: MagicMock = mm(Gtk.Label)


@pytest.fixture
def builder(mocker) -> Gtk.Builder:
    return mocker.MagicMock(spec=Gtk.Builder)


@pytest.fixture
def objects(builder: Gtk.Builder) -> MockObjects:
    rv = MockObjects()

    def side_effect(name) -> Gtk.Widget:
        return getattr(rv, name)
    builder.get_object.side_effect = side_effect
    return rv


@pytest.fixture
def app(mocker) -> MagicMock:
    return mocker.MagicMock(spec=App)


@pytest.fixture
def library(mocker) -> MagicMock:
    return mocker.MagicMock(spec=Library)


@pytest.fixture
def add_action(mocker) -> MagicMock:
    return mocker.MagicMock()


@dataclass
class Callbacks:
    next_page: Optional[tuple[Callable, Gio.SimpleAction]] = None
    prev_page: Optional[tuple[Callable, Gio.SimpleAction]] = None
    edit_with_mouse: Optional[tuple[Callable, Gio.SimpleAction]] = None

    render: Optional[tuple[Callable, Gio.SimpleAction]] = None
    realize: Optional[tuple[Callable, Gio.SimpleAction]] = None
    unrealize: Optional[tuple[Callable, Gio.SimpleAction]] = None
    key_press_event: Optional[tuple[Callable, Gio.SimpleAction]] = None
    notify_has_focus: Optional[tuple[Callable, Gio.SimpleAction]] = None


@pytest.fixture
def callbacks(add_action, objects) -> Callbacks:
    rv = Callbacks()

    def collect(name: str, callback: Callable, *_) -> MagicMock:
        action = MagicMock(spec=Gio.SimpleAction)
        setattr(rv,
                name.replace("-", "_").replace("::", "_"),
                (callback, action))
        return action

    add_action.side_effect = collect
    objects.view.connect.side_effect = collect
    return rv


@pytest.fixture
def thumb_cache(mocker) -> MagicMock:
    return mocker.MagicMock(spec=CoverCache)


@pytest.fixture
def thumb(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.Thumb")


@pytest.fixture
def in_mem_cache(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.InMemCache")


@pytest.fixture
def view_timer(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.ViewTimer")


@pytest.fixture
def cursor(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.Cursor")


@pytest.fixture
def wrap_add_action(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.wrap_add_action",
                        lambda x: x)


@pytest.fixture
def view_gestures(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.ViewGestures")


@pytest.fixture
def tiles(mocker) -> MagicMock:
    return mocker.patch("comics_viewer.view.Tiles")


@dataclass(frozen=True)
class Fixture:
    view: View
    objects: MockObjects
    builder: Gtk.Builder
    app: App
    library: Library
    add_action: MagicMock
    thumb_cache: MagicMock
    callbacks: Callbacks
    thumb: MagicMock
    in_mem_cache: MagicMock
    view_timer: MagicMock
    cursor: MagicMock
    wrap_add_action: MagicMock
    view_gestures: MagicMock
    tiles: MagicMock
    ogl: MockOGL


@pytest.fixture
def f(
    objects: MockObjects, builder: Gtk.Builder, app: App, library: Library,
    add_action, thumb_cache: MagicMock, callbacks: Callbacks, thumb: MagicMock,
    in_mem_cache: MagicMock, view_timer: MagicMock, cursor: MagicMock,
    wrap_add_action: Callbacks, view_gestures: MagicMock, tiles: MagicMock,
    ogl: MockOGL,
):
    view = View(builder=builder,
                app=app,
                library=library,
                add_action=add_action,
                thumb_cache=thumb_cache)
    return Fixture(
        view=view,
        objects=objects,
        builder=builder,
        app=app,
        library=library,
        add_action=add_action,
        thumb_cache=thumb_cache,
        callbacks=callbacks,
        thumb=thumb,
        in_mem_cache=in_mem_cache,
        view_timer=view_timer,
        cursor=cursor,
        wrap_add_action=wrap_add_action,
        view_gestures=view_gestures,
        tiles=tiles,
        ogl=ogl,
    )


def test_set_double_buffered_called(f):
    f.objects.view.set_double_buffered.assert_called_once_with(True)
