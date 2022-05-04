from typing import Tuple
from pathlib import Path
from zipfile import ZipFile
from rarfile import RarFile
from contextlib import contextmanager

ARCHIVE_TYPES = {
    ".cbz": ZipFile,
    ".cbr": RarFile,
}
IMAGE_TYPES = [
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
]


@contextmanager
def archive(path: Path):
    with ARCHIVE_TYPES[path.suffix.lower()](path) as a:
        yield a


def list_archive(path: Path):
    def helper():
        with archive(path) as a:
            for p in map(Path, a.namelist()):
                if p.suffix.lower() in IMAGE_TYPES:
                    yield str(p)
    return sorted(list(helper()))


class Archive:
    def __init__(self, path: Path):
        self._pages = list_archive(path)
        self._path = path

    def __len__(self):
        return len(self._pages)

    def read(self, idx: int) -> Tuple[str, bytes]:
        with archive(self._path) as a:
            return (
                Path(self._pages[idx]).name,
                a.read(self._pages[idx])
            )
