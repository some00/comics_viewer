from pathlib import Path
from unittest.mock import MagicMock
from pytest import fixture, raises
from zipfile import ZipFile
from comics_viewer.archive import list_archive, ARCHIVE_TYPES


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
