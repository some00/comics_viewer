from comics_viewer.archive import Archive, list_archive
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).parent.parent / "data"


def parametrize_archive(func):
    return pytest.mark.parametrize("path", [BASE_DIR / "rar.cbr",
                                            BASE_DIR / "zip.cbz"])(func)


def parametrize_pages(func):
    return pytest.mark.parametrize("idx, size, page",
                                   map(lambda x: (x[0], x[1][0], x[1][1]),
                                       enumerate([
                                           (9049, "00.png"),
                                           (25541, "01.jpg"),
                                           (25541, "02.jpeg"),
                                           (2616, "03.gif"),
                                           (9049, "04.PNG"),
                                           (25541, "05.JPG"),
                                           (25541, "06.JPEG"),
                                           (2616, "07.GIF"),
                                       ])))(func)


@parametrize_archive
def test_path(path):
    assert Archive(path).path == path


@parametrize_archive
def test_len(path):
    assert len(Archive(path)) == 8


@parametrize_pages
@parametrize_archive
def test_read(path, page, size, idx):
    page  # silence unused parameter
    assert len(Archive(path).read(idx)) == size


@parametrize_archive
@parametrize_pages
def test_name(path, page, size, idx):
    size  # silence unused parameter
    assert Archive(path).name(idx) == page


@parametrize_archive
@parametrize_pages
def test_size(path, page, size, idx):
    page  # silence unused parameter
    assert Archive(path).size(idx) == size


@parametrize_archive
def test_list_archive(path):
    assert list_archive(path) == [
        "00.png",
        "01.jpg",
        "02.jpeg",
        "03.gif",
        "04.PNG",
        "05.JPG",
        "06.JPEG",
        "07.GIF",
    ]


@parametrize_archive
def test_read_invalid_index(path):
    with pytest.raises(IndexError):
        Archive(path).read(10)


@parametrize_archive
def test_name_invalid_index(path):
    with pytest.raises(IndexError):
        Archive(path).name(11)
