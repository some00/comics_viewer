from typing import Optional
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

from .library import Comics
from .gi_helpers import Gtk, Gdk
from .in_mem_cache import InMemCache
from .archive import Archive
from .utils import imdecode, RESOURCE_BASE_DIR


Status = namedtuple("Status", [
    "container", "filename", "progress", "pagename", "progress_bar"
])

VERTEX_DATA = np.array([
    # positions        texture coords
    1.0,   1.0, 0.0,   1.0, 0.0,      # top right
    1.0,  -1.0, 0.0,   1.0, 1.0,      # bottom right
    -1.0, -1.0, 0.0,   0.0, 1.0,      # bottom left
    -1.0,  1.0, 0.0,   0.0, 0.0       # top left
], dtype="f")
INDICES_DATA = np.array([
    0, 1, 3,
    1, 2, 3,
], dtype=np.uint32)


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
    # TODO someday
    # img = cv2.flip(img, 0)
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
        self, area: Gtk.GLArea, builder: Gtk.Builder,
        max_cache: int = 64 * 1024 * 1024
    ):
        self._area = area
        self._status = Status(
            container=builder.get_object("statusbar"),
            filename=builder.get_object("filename"),
            progress=builder.get_object("progress"),
            pagename=builder.get_object("pagename"),
            progress_bar=builder.get_object("progress_bar"),
        )
        self._switcher = builder.get_object("switcher")
        self._in_mem = InMemCache(max_cache)
        self._archive: Optional[Archive] = None
        self._comics: Optional[Comics] = None
        self._page_idx: Optional[int] = None

        self._stack = ExitStack()
        self._tex_stack = ExitStack()
        self._texture = None
        self._vao = None
        self._vbo = None
        self._shader = None
        self._transform = None
        self._realized = False

        self._area.set_double_buffered(
            int(os.environ.get("COMICS_VIEWER_DOUBLE_BUFFERED", 1)))
        self._area.connect("render", self._render)
        self._area.connect("realize", self._realize, True)
        self._area.connect("unrealize", self._unrealize, False)
        # TODO reset cursor and zoom?
        # self._area.connect("size-allocate", self._size_allocate)
        builder.get_object("stack").connect("notify::visible-child-name",
                                            self.visible_child_changed)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._stack.pop_all().close()
        self._tex_stack.pop_all().close()

    @property
    def page_number(self) -> int:
        return self.page_idx + 1

    @property
    def page_idx(self) -> int:
        return self._page_idx

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
        self._status.filename.set_label(self.archive.path.name)

    @page_idx.setter
    def page_idx(self, page_idx):
        self._page_idx = page_idx
        self._status.progress.set_label(
            f"{self.page_number}/{len(self.archive)} "
            f"({self.fraction * 100:.0f}%)"
        )
        self._status.progress_bar.set_fraction(self.fraction)
        self._status.pagename.set_label(self.archive.name(page_idx))

    def load(self, base: Path, comics: Comics, page_idx: int) -> bool:
        path = base / comics.path
        try:
            self.archive = path
            self._comics = comics
            self.page_idx = page_idx
            self._set_img()
        except IndexError:
            return False
        except OSError:
            return False
        return True

    def _set_img(self):
        if self.archive is None or self.page_idx is None:
            return
        key = (self.archive.path, self.page_idx)
        encoded = self._in_mem.get(key)
        if encoded is None:
            encoded = self.archive.read(self.page_idx)
            self._in_mem.store(key, encoded)
        decoded = imdecode(encoded)
        if not self._realized:
            return
        self._tex_stack.pop_all().close()
        # TODO remove make current only call in _render
        self._area.make_current()
        self._texture = self._tex_stack.enter_context(_load_texture(decoded))
        self._area.queue_draw()

    def _render(self, area: Gtk.GLArea, context: Gdk.GLContext):
        self._clear_color = (1, 0, 1)  # TODO
        OGL.glClearColor(*self._clear_color, 1.0)
        OGL.glClear(OGL.GL_COLOR_BUFFER_BIT)
        if self._texture is not None:
            with self._shader:
                OGL.glUniformMatrix4fv(
                    self._transform, 1, OGL.GL_FALSE, self.affine)
                OGL.glBindTexture(OGL.GL_TEXTURE_2D, self._texture)
                OGL.glBindVertexArray(self._vao)
                OGL.glDrawElements(
                    OGL.GL_TRIANGLES, 6, OGL.GL_UNSIGNED_INT, INDICES_DATA)
        OGL.glFlush()
        return True

    @property
    def affine(self):
        self.zoom = 1.0  # TODO
        self.cursor = np.zeros(2)  # TODO
        self.scale = (1.0, 1.0)  # TODO

        Z = np.concatenate([self.scale, [1]])
        T = np.concatenate([self.cursor * self.zoom, [0]])
        A = affine_compose(T=T, R=np.eye(3), Z=Z)
        return np.transpose(A).astype(np.float32)

    def _realize(self, area: Gtk.GLArea, ctx: Gdk.GLContext):
        self._realized = True
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
        self._set_img()

    def _unrealize(self, area: Gtk.GLArea, ctx: Gdk.GLContext):
        area.make_current()
        self._tex_stack.pop_all().close()
        self._stack.pop_all().close()
        self._realized = False

    def visible_child_changed(self, stack, param):
        if stack.get_visible_child_name() == "view":
            self._area.queue_render()
