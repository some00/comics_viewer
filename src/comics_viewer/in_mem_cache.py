from typing import Hashable, Optional, Dict
from operator import itemgetter
from time import time


class InMemCache:
    def __init__(self, max_size: int):
        self._max_size = max_size
        self._cache: Dict[Hashable, bytes] = {}
        self._lru: Dict[Hashable, int] = {}

    def get(self, key: Hashable) -> Optional[bytes]:
        if key in self._cache:
            self._lru[key] = time()
            return self._cache[key]
        return None

    def size(self):
        return sum(map(len, self._cache.values()))

    @property
    def max_size(self):
        return self._max_size

    @max_size.setter
    def max_size(self, max_size: int):
        self._max_size = max_size
        self._drop()

    def store(self, key: Hashable, value: bytes):
        self._cache[key] = value
        self._lru[key] = time()
        self._drop()

    def _drop(self):
        size = self.size()
        usage = sorted([(v, k) for k, v in self._lru.items()],
                       key=itemgetter(0))
        while size > self._max_size:
            k = usage.pop(0)[1]
            size -= len(self._cache[k])
            del self._lru[k]
            del self._cache[k]
