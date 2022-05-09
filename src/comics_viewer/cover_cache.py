from typing import Tuple, List, Optional, Dict, NewType, Union, Iterable
from hashlib import md5
from pathlib import Path
from binascii import hexlify
import numpy.typing as npt
import pickle
from time import time
from collections import namedtuple
from itertools import chain
from operator import itemgetter

from .utils import scale_to_fit, imdecode, dfs_gen, imencode
from .archive import Archive
from .in_mem_cache import InMemCache
from .gi_helpers import GLib


LRU_INFO = "lru.pickle"
Stamp = NewType("Stamp", int)
ToCache = namedtuple("ToCache", ["library", "comics", "page_idx"])


def cache_msg(*args, **kwargs):
    return
    print(*args, **kwargs)


# TODO rename thumbnail cache
class CoverCache:
    def __init__(self, path: Path, max_shape: npt.NDArray[int],
                 max_in_mem: int = 12 * 1024 * 1024,
                 max_size: int = 100 * 1024 * 1024):
        self._base = path.absolute()
        self._base.mkdir(exist_ok=True, parents=True)
        self._max_size = max_size
        self._max_shape = max_shape
        self._in_mem = InMemCache(max_in_mem)

        self._idle_source: Optional[GLib.Source] = None
        self._lru: Dict[Path, Stamp] = {}
        self._size: Optional[int] = None
        self._to_process: Iterable[Union[ToCache, Path]] = []

        lru = self._base / LRU_INFO
        if lru.exists():
            with lru.open("rb") as f:
                self._lru = pickle.load(f)
                cache_msg("loaded info")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.save()

    def cover(self, library: Path, comics: Path, idx: int) -> npt.NDArray:
        k, p = self.key(library, comics, idx)
        self._lru[p.relative_to(self._base)] = time()
        in_mem = self._in_mem.get(k)
        if in_mem is not None:
            cache_msg("in mem hit", k)
            return imdecode(in_mem)
        if p.exists():
            with p.open("rb") as f:
                in_mem = f.read()
                self._in_mem.store(k, in_mem)
                cache_msg("file hit", p)
                return imdecode(in_mem)
        else:
            page = Archive(library / comics).read(idx)
            thumb = scale_to_fit(self._max_shape, imdecode(page))
            p.parent.mkdir(exist_ok=True, parents=True)
            with p.open("wb") as f:
                in_mem = imencode(thumb)
                self._in_mem.store(k, in_mem)
                f.write(in_mem)
            self._size += len(in_mem)
            cache_msg("new entry", k)
            self.cleanup()
            return thumb

    def start_idle(self, library: Path, data: List[Tuple[Path, int]]):
        cache_msg("start idle")
        if self._idle_source is not None:
            self._idle_source.destroy()
        gen = (ToCache(library=library, comics=c, page_idx=i) for c, i in data)
        if self._size is None:
            self._size = 0
            self._to_process = chain(dfs_gen(self._base), gen)
            cache_msg("calc size")
        else:
            self._to_process = gen
        self._idle_source = GLib.idle_source_new()
        self._idle_source.set_callback(self.idle)
        self._idle_source.attach(None)

    def idle(self, arg):
        try:
            v = next(self._to_process)
        except StopIteration:
            self.cleanup()
            return GLib.SOURCE_REMOVE
        cache_msg("idle", v)
        if isinstance(v, Path):
            abs_p, rel_p = self._base / v, v
            if rel_p == LRU_INFO:
                pass
            elif abs_p.is_dir():
                if len(list(abs_p.iterdir())) == 0:
                    cache_msg("remove empty dir")
                    abs_p.rmdir()
            elif rel_p in self._lru:
                self._size += abs_p.stat().st_size
                cache_msg("entry size", self._size)
            else:
                cache_msg("rm orphan")
                abs_p.unlink()
        elif isinstance(v, ToCache):
            k, p = self.key(v.library, v.comics, v.page_idx)
            if not p.exists():
                page = Archive(v.library / v.comics).read(v.page_idx)
                thumb = scale_to_fit(self._max_shape, imdecode(page))
                p.parent.mkdir(exist_ok=True, parents=True)
                with p.open("wb") as f:
                    f.write(imencode(thumb))
                    cache_msg("new file entry", p)
        return GLib.SOURCE_CONTINUE

    def cleanup(self):
        cache_msg("cleanup")
        cleanorder = sorted(list(self._lru.items()), key=itemgetter(1))
        while self._size is not None and self._size > self._max_size:
            try:
                p, s = cleanorder.pop(0)
                p = self._base / p
                self._size -= p.stat().st_size
                p.unlink()
                cache_msg("drop file", p)
            except IndexError:
                break
        cache_msg("size after cleanup", self._size)

    def key(self, library: Path, comics: Path, idx: int) -> Union[str, Path]:
        assert(not comics.is_absolute())
        h = md5()
        h.update(str(library).encode())
        h.update(str(comics).encode())
        h.update(f"${idx}".encode())
        h.update("f_{self._max_shape[0]}x{self._max_size[1]}".encode())
        k = hexlify(h.digest()).decode()
        return k, self._base / k[:2] / k[2:]

    def save(self):
        cache_msg("save")
        with (self._base / LRU_INFO).open("wb") as f:
            pickle.dump(self._lru, f)
