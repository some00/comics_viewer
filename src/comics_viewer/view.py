from typing import Optional, Tuple
import os
from collections import namedtuple
from pathlib import Path
from contextlib import ExitStack, contextmanager
import OpenGL.GL as OGL
from OpenGL.arrays import vbo
from OpenGL.GL import shaders
from ctypes import c_void_p
import numpy as np
import numpy.typing as npt
from transforms3d.affines import compose as affine_compose
from transforms3d.axangles import axangle2mat
from datetime import datetime
import humanize

from .library import Comics, Progress, Library
from .gi_helpers import Gtk, Gdk
from .in_mem_cache import InMemCache
from .archive import Archive
from .cover_cache import CoverCache
from .utils import imdecode, RESOURCE_BASE_DIR, wrap_add_action
from .thumb import Thumb
from .view_gestures import ViewGestures
from .tiles import Tiles
from .cursor import Cursor
from .view_timer import ViewTimer


Status = namedtuple("Status", [
    "container", "comics", "progress", "pagename", "progress_bar",
    "img_shape", "encoded_size",
])
Actions = namedtuple("Actions", [
    "next_page", "prev_page",
])

VERTEX_DATA = np.array([
    # positions        texture coords
    1.0,   1.0, 0.0,   1.0, 1.0,      # top right
    1.0,  -1.0, 0.0,   1.0, 0.0,      # bottom right
    -1.0, -1.0, 0.0,   0.0, 0.0,      # bottom left
    -1.0,  1.0, 0.0,   0.0, 1.0       # top left
], dtype="f")
INDICES_DATA = np.array([
    0, 1, 3,
    1, 2, 3,
], dtype=np.uint32)


def cat(x, *v):
    return np.concatenate([x, v])


@contextmanager
def _vertex_arrays(size):
    vao = OGL.glGenVertexArrays(size)
    OGL.glBindVertexArray(vao)
    yield vao
    OGL.glDeleteVertexArrays(vao, size)


@contextmanager
def _vbo(vertex_data):
    rv = vbo.VBO(vertex_data, usage=OGL.GL_STATIC_DRAW,
                 target=OGL.GL_ARRAY_BUFFER)
    yield rv
    rv.delete()


@contextmanager
def _compile_and_link_shaders(fragment_code, vertex_code):
    with ExitStack() as stack:
        fragment = shaders.compileShader(fragment_code, OGL.GL_FRAGMENT_SHADER)
        stack.callback(OGL.glDeleteShader, fragment)
        vertex = shaders.compileShader(vertex_code, OGL.GL_VERTEX_SHADER)
        stack.callback(OGL.glDeleteShader, vertex)
        rv = shaders.compileProgram(vertex, fragment, validate=True)
        stack.pop_all()
    yield rv
    OGL.glDeleteProgram(rv)


@contextmanager
def _load_texture(img: npt.NDArray):
    texture = OGL.glGenTextures(1)
    OGL.glBindTexture(OGL.GL_TEXTURE_2D, texture)
    OGL.glTexParameteri(
        OGL.GL_TEXTURE_2D, OGL.GL_TEXTURE_WRAP_S, OGL.GL_REPEAT)
    OGL.glTexParameteri(
        OGL.GL_TEXTURE_2D, OGL.GL_TEXTURE_WRAP_T, OGL.GL_REPEAT)
    OGL.glTexParameteri(OGL.GL_TEXTURE_2D, OGL.GL_TEXTURE_MIN_FILTER,
                        OGL.GL_LINEAR_MIPMAP_LINEAR)
    OGL.glTexParameteri(
        OGL.GL_TEXTURE_2D, OGL.GL_TEXTURE_MAG_FILTER, OGL.GL_LINEAR)
    h, w, image = img.shape[0], img.shape[1], img.tobytes()
    OGL.glTexImage2D(OGL.GL_TEXTURE_2D, 0, OGL.GL_RGBA, w, h, 0, OGL.GL_BGR,
                     OGL.GL_UNSIGNED_BYTE, image)
    OGL.glGenerateMipmap(OGL.GL_TEXTURE_2D)
    try:
        yield texture
    finally:
        OGL.glDeleteTextures(1, texture)


class View:
    def __init__(
        self,
        builder: Gtk.Builder,
        app,
        library: Library,
        add_action,
        thumb_cache: CoverCache,
        max_cache: int = 64 * 1024 * 1024
    ):
        self._thumb = Thumb(view=self, builder=builder,
                            thumb_cache=thumb_cache, library=library.path)
        self._app = app
        self._library = library
        self._area = builder.get_object("view")
        self._window = builder.get_object("window")
        self._status = Status(
            container=builder.get_object("statusbar"),
            comics=builder.get_object("comics"),
            progress=builder.get_object("progress"),
            pagename=builder.get_object("pagename"),
            progress_bar=builder.get_object("progress_bar"),
            img_shape=builder.get_object("img_shape"),
            encoded_size=builder.get_object("encoded_size"),
        )
        self._in_mem = InMemCache(max_cache)
        self._archive: Optional[Archive] = None
        self._comics: Optional[Comics] = None
        self._page_idx: Optional[int] = None
        self._img_shape: Optional[npt.NDArray] = None
        self._encoded_size: Optional[int] = None
        self._page_changed = False
        self._timer = ViewTimer(self)
        self._cursor = Cursor(builder, self)

        self._stack = ExitStack()
        self._tex_stack = ExitStack()
        self._texture = None
        self._vao = None
        self._vbo = None
        self._shader = None
        self._transform = None
        self._scale = 1.0
        self._position: npt.NDArray = np.zeros(2)
        self._viewport: Optional[npt.NDArray] = None

        self._area.set_double_buffered(
            int(os.environ.get("COMICS_VIEWER_DOUBLE_BUFFERED", 1)))
        self._area.connect("render", self._render)
        self._area.connect("realize", self._realize, True)
        self._area.connect("unrealize", self._unrealize, False)
        self._area.connect("key-press-event", self._key_press)
        self._area.connect(
            "notify::has-focus",
            lambda *x: self.set_actions(self._area.has_focus())
        )

        add_action = wrap_add_action(add_action)
        self._actions = Actions(
            next_page=add_action("next-page", self.next_page),
            prev_page=add_action("prev-page", self.prev_page),
        )
        self._gestures = ViewGestures(self, builder)
        self._tiles = Tiles(self, builder)
        self.set_actions(False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._stack.pop_all().close()
        self._tex_stack.pop_all().close()

    @property
    def app(self):
        return self._app

    @property
    def cursor(self) -> Cursor:
        return self._cursor

    @property
    def timer(self) -> ViewTimer:
        return self._timer

    @property
    def tiles(self) -> Tiles:
        return self._tiles

    @property
    def page_number(self) -> int:
        return self.page_idx + 1

    @property
    def fraction(self):
        return self.page_number / len(self.archive)

    @property
    def archive(self) -> Archive:
        return self._archive

    @archive.setter
    def archive(self, path: Path):
        if self._archive and self._archive.path == path:
            return
        self._archive = Archive(path)
        self._thumb.archive = self._archive
        if self._comics.title and self._comics.issue:
            comics = f"{self._comics.title} #{self._comics.issue}"
        else:
            comics = self.archive.path.name
        self._status.comics.set_label(comics)
        self._window.set_title(comics)

    @property
    def page_idx(self) -> int:
        return self._page_idx

    @property
    def viewport(self) -> Optional[npt.NDArray]:
        return self._viewport

    @viewport.setter
    def viewport(self, viewport: npt.NDArray):
        self._viewport = viewport

    @page_idx.setter
    def page_idx(self, page_idx):
        if page_idx >= len(self.archive) or page_idx < 0:
            return
        self._page_idx = page_idx
        self._status.progress.set_label(
            f"{self.page_number}/{len(self.archive)} "
            f"({self.fraction * 100:.0f}%)"
        )
        self._status.progress_bar.set_fraction(self.fraction)
        self._status.pagename.set_label(self.archive.name(page_idx))
        with self._library.new_session as session, session.begin():
            comics = session.query(Comics).filter_by(
                id=self._comics.id).one()
            comics.progress = Progress(
                page_idx=page_idx,
                last_read=datetime.now(),
            )
            session.add(comics)
        self._page_changed = True
        self._scale = 1.0
        self.position = np.zeros(2)
        self._area.queue_render()
        self._thumb.scroll_to(page_idx)
        self._tiles.reset()  # TODO save
        self.set_actions(True)

    @property
    def img_shape(self) -> Optional[npt.NDArray]:
        return self._img_shape

    @img_shape.setter
    def img_shape(self, img_shape: Tuple[int, int]):
        self._img_shape = np.array(img_shape)
        self._status.img_shape.set_label(
            "x".join(map(str, np.flip(self._img_shape))))

    @property
    def encoded_size(self) -> Optional[int]:
        return self._encoded_size

    @encoded_size.setter
    def encoded_size(self, encoded_size: int):
        self._encoded_size = encoded_size
        self._status.encoded_size.set_label(
            humanize.naturalsize(encoded_size, gnu=True))

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, scale: float):
        self._scale = np.clip(scale, 1.0, 4.0)
        self._area.queue_render()

    @property
    def position(self) -> npt.NDArray:
        return self._position

    @position.setter
    def position(self, position: npt.NDArray):
        if self.img_shape is not None and self.viewport is not None:
            affine = self.affine(np.zeros(2))
            vp = np.abs(
                self.widget_to_img(self.viewport, affine)
                -
                self.widget_to_img(np.zeros(2), affine)
            ) * np.flip(self.keep_aspect)
            shape = self.img_shape.astype(np.float64)
            position = np.clip(
                position,
                vp / 2 - shape / 2,
                shape - vp / 2 - shape / 2
            )

        self._position = position
        self._area.queue_render()

    @property
    def angle(self):
        viewport_aspect = np.divide(*self.viewport)
        aspects = {
            abs(np.divide(
                *self.img_shape) - viewport_aspect): 0,
            abs(np.divide(
                *np.flip(self.img_shape)) - viewport_aspect): np.pi / 2
        }
        return aspects[min(aspects.keys())]

    @property
    def m_rotation(self):
        angle = self.angle
        return axangle2mat([0, 0, 1.0], angle)

    @property
    def m_zoom(self):
        return self.keep_aspect * self.scale

    @property
    def m_translate(self):
        # temp var
        p = self.position.copy()
        # translate by the inverse of position
        p *= -1.0
        # scale by the user selected zoom level
        p *= self.scale
        # normalize
        p /= (self.img_shape / np.flip(self.keep_aspect))
        # scale to vertex coords [0, 1]
        p *= 2.0
        # invert y
        p *= [-1.0, 1.0]
        # rotate by current image rotation
        p = np.dot(cat(p, 0.0), self.m_rotation)[:2]
        # flip for (x, y)
        p = np.flip(p)
        return p

    @property
    def keep_aspect(self):
        if self.img_shape is None:
            return np.array([1.0, 1.0])
        vp = np.abs(np.dot(cat(self.viewport, 0), self.m_rotation))[:2]
        rv = vp / self.img_shape
        rv /= max(rv)
        return rv

    def widget_to_img(self, pos: npt.NDArray, affine=None):
        return self._transform_position(pos=pos, inverse=True, affine=affine)

    def img_to_widget(self, pos: npt.NDArray, affine=None):
        return self._transform_position(pos=pos, inverse=False, affine=affine)

    def _transform_position(self, pos: npt.NDArray,
                            inverse: bool, affine=None) -> npt.NDArray:
        if affine is None:
            affine = self.affine()
        if inverse:
            affine = np.linalg.inv(affine)
            src, dst = self.viewport, self.img_shape
        else:
            src, dst = self.img_shape, self.viewport
        ndc = np.dot(cat(np.flip((pos - src / 2.0) / src * 2.0 * [-1.0, 1.0]),
                         0.0, 1.0), affine)[:2]
        return np.flip(((ndc - [-1.0, 1.0]) /
                        2.0 * [1.0, -1.0] * np.flip(dst))[:2])

    def load(self, base: Path, comics: Comics, page_idx: int) -> bool:
        path = base / comics.path
        try:
            self._comics = comics
            self.archive = path
            self.page_idx = page_idx
        except IndexError:
            return False
        except OSError:
            return False
        return True

    def _ensure_page(self):
        if not self._page_changed:
            return
        self._page_changed = False
        if self.archive is None or self.page_idx is None:
            return
        key = (self.archive.path, self.page_idx)
        encoded = self._in_mem.get(key)
        if encoded is None:
            encoded = self.archive.read(self.page_idx)
            self._in_mem.store(key, encoded)
        self.encoded_size = len(encoded)
        decoded = imdecode(encoded)
        self._tex_stack.pop_all().close()
        self._area.make_current()
        self._texture = self._tex_stack.enter_context(_load_texture(decoded))
        self.img_shape = decoded.shape[:2]
        self._area.queue_render()

    def _render(self, area: Gtk.GLArea, context: Gdk.GLContext):
        self._ensure_page()
        OGL.glClearColor(0, 0, 0, 0)
        OGL.glClear(OGL.GL_COLOR_BUFFER_BIT)
        x, y, w, h = OGL.glGetIntegeri_v(OGL.GL_VIEWPORT, 0)
        self.viewport = np.array([h, w])
        if self._texture is not None:
            with self._shader:
                OGL.glUniformMatrix4fv(self._transform,
                                       1, OGL.GL_FALSE,
                                       self.affine())
                OGL.glBindTexture(OGL.GL_TEXTURE_2D, self._texture)
                OGL.glBindVertexArray(self._vao)
                OGL.glDrawElements(
                    OGL.GL_TRIANGLES, 6, OGL.GL_UNSIGNED_INT, INDICES_DATA)
        OGL.glFlush()
        return True

    def affine(self, translate: Optional[npt.NDArray] = None):
        if translate is None:
            translate = self.m_translate
        return affine_compose(Z=cat(self.m_zoom, 1),
                              T=cat(translate, 0),
                              R=self.m_rotation).T.astype(np.float64)

    def _realize(self, area: Gtk.GLArea, ctx: Gdk.GLContext):
        area.make_current()
        OGL.glPixelStorei(OGL.GL_UNPACK_ALIGNMENT, 1)
        self._vao = self._stack.enter_context(_vertex_arrays(1))
        self._vbo = self._stack.enter_context(_vbo(VERTEX_DATA))
        with self._vbo:
            OGL.glVertexAttribPointer(0, 3,
                                      OGL.GL_FLOAT,
                                      OGL.GL_FALSE,
                                      len(VERTEX_DATA),
                                      None)
            OGL.glEnableVertexAttribArray(0)
            OGL.glVertexAttribPointer(1, 2,
                                      OGL.GL_FLOAT,
                                      OGL.GL_FALSE,
                                      len(VERTEX_DATA),
                                      c_void_p(3 * 4))
            OGL.glEnableVertexAttribArray(1)
        with (RESOURCE_BASE_DIR / "view.fs").open() as f:
            fragment_code = f.read()
        with (RESOURCE_BASE_DIR / "view.vs").open() as f:
            vertex_code = f.read()
        self._shader = self._stack.enter_context(
            _compile_and_link_shaders(fragment_code, vertex_code))
        self._transform = OGL.glGetUniformLocation(self._shader, "transform")
        self._ensure_page()

    def _unrealize(self, area: Gtk.GLArea, ctx: Gdk.GLContext):
        area.make_current()
        self._tex_stack.pop_all().close()
        self._stack.pop_all().close()

    def next_page(self):
        self.page_idx += 1

    def prev_page(self):
        self.page_idx -= 1

    def set_actions(self, enable: bool):
        self._actions.next_page.set_enabled(
            enable and
            self.archive and
            self.page_idx + 1 < len(self.archive)
        )
        self._actions.prev_page.set_enabled(
            enable and
            self.archive and
            self.page_idx
        )

    def _key_press(self, widget: Gtk.GLArea, event: Gdk.EventKey):
        return event.keyval in (Gdk.KEY_Right, Gdk.KEY_Left)

    def rotate(self, p: npt.NDArray, angle: Optional[float] = None):
        if angle is None:
            m_rotation = self.m_rotation
        else:
            m_rotation = axangle2mat([0, 0, 1.0], angle)
        return np.dot(cat(p, 0), m_rotation)[:2]
