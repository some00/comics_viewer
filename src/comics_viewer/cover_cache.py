from typing import Tuple, List
from hashlib import md5
from pathlib import Path
from binascii import hexlify
import numpy.typing as npt
import cv2

from .utils import scale_to_fit, imdecode
from .archive import Archive
from .in_mem_cache import InMemCache
from .gi_helpers import GLib


class CoverCache:
    def __init__(self, path: Path, max_shape: npt.NDArray[int],
                 max_lru: int = 12 * 1024 * 1024):
        self._directory = path
        self._max_shape = max_shape
        self._in_mem = InMemCache(max_lru)

    def cover(self, library: Path, comics: Path, idx: int) -> npt.NDArray:
        k = self.key(comics, idx)
        in_mem = self._in_mem.get(k)
        if in_mem is not None:
            return imdecode(in_mem)
        p = self._directory / k[:2] / k[2:]
        if p.exists():
            with p.open("rb") as f:
                in_mem = f.read()
                self._in_mem.store(k, in_mem)
                return imdecode(in_mem)
        else:
            page = Archive(library / comics).read(idx)
            thumb = scale_to_fit(self._max_shape, imdecode(page))
            p.parent.mkdir(exist_ok=True, parents=True)
            with p.open("wb") as f:
                _, in_mem = cv2.imencode(".png", thumb)
                self._in_mem.store(k, in_mem)
                f.write(in_mem)
            return thumb

    def start_idle(self, library: Path, data: List[Tuple[Path, int]]):
        GLib.idle_add(self.idle, library, data)

    def idle(self, library: Path, data: List[Tuple[Path, int]]):
        try:
            comics, idx = data.pop(0)
        except IndexError:
            return GLib.SOURCE_REMOVE
        k = self.key(comics, idx)
        p = self._directory / k[:2] / k[2:]
        if not p.exists():
            page = Archive(library / comics).read(idx)
            thumb = scale_to_fit(self._max_shape, imdecode(page))
            p.parent.mkdir(exist_ok=True, parents=True)
            with p.open("wb") as f:
                f.write(cv2.imencode(".png", thumb)[-1])
        return GLib.SOURCE_CONTINUE if data else GLib.SOURCE_REMOVE

    def key(self, comics: Path, idx: int) -> Path:
        assert(not comics.is_absolute())
        h = md5()
        h.update(str(comics).encode())
        h.update(f"${idx}".encode())
        return hexlify(h.digest()).decode()
