from comics_viewer.archive import Archive, list_archive, ARCHIVE_TYPES
from pathlib import Path
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from pytest import fixture, raises
from zipfile import ZipFile


BASE_DIR = Path(__file__).parent.parent / "data"


@fixture
def mock_archive_types():
    copy = ARCHIVE_TYPES.copy()
    try:
        mock = {k: MagicMock(spec=ZipFile) for k in ARCHIVE_TYPES.keys()}
        ARCHIVE_TYPES.update(**mock)
        yield mock
    finally:
        ARCHIVE_TYPES.update(**copy)


def test_list_archive_empty(mock_archive_types):
    file = mock_archive_types[".cbz"].return_value.__enter__.return_value
    file.namelist.return_value = []
    assert list_archive(Path("foo.cbz")) == []


def test_list_archive_not_comics():
    with raises(KeyError):
        list_archive(Path("a.zip"))


def test_list_archive_image_filter(mock_archive_types):
    file = mock_archive_types[".cbr"].return_value.__enter__.return_value
    images = ["b/b.png", "c/c.PNG", "d/d.jpg", "e/e.JPEG", "f/f.gif", "g.GIF"]
    file.namelist.return_value = ["a.txt"] + images
    assert images == list_archive(Path("a.cbr"))


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
