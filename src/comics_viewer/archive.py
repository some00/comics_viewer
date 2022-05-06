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
        def helper():
            with archive(path) as a:
                for info in a.infolist():
                    if Path(info.filename).suffix.lower() in IMAGE_TYPES:
                        yield info.filename, info.file_size
        self._path = path
        self._pages = sorted(list(helper()))

    @property
    def path(self) -> Path:
        return self._path

    def __len__(self):
        return len(self._pages)

    def read(self, idx: int) -> bytes:
        with archive(self._path) as a:
            return a.read(self._pages[idx][0])

    def name(self, idx: int) -> str:
        return Path(self._pages[idx][0]).name

    def size(self, idx: int) -> int:
        return self._pages[idx][1]
