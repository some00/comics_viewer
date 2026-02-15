from pathlib import Path
import pytest
from typing import Iterable
from pathlib import Path

from comics_viewer.thumb import PageInfo, Thumb
from comics_viewer.gi_helpers import GObject, Gtk, GLib
from comics_viewer.view import View
from comics_viewer.cover_cache import CoverCache


def test_page_info():
    tuples = [
        (Path("a.cbz"), 0),
        (Path("a.cbz"), 0),
        (Path("b.cbz"), 0),
        (Path("a.cbz"), 1),
    ]
    page_infos = [PageInfo(*t) for t in tuples]
    for idx, page_info in enumerate(page_infos):
        assert isinstance(page_info, GObject.GObject)
        hash(page_info)
        assert tuples[idx] == page_info.to_tuple()
    assert page_infos[0] == page_infos[1]
    assert page_infos[0] != page_infos[2]
    assert page_infos[0] != page_infos[3]


@pytest.fixture
def mock_view(mocker) -> View:
    return mocker.MagicMock(spec=View)


@pytest.fixture
def mock_cover_cache(mocker) -> CoverCache:
    return mocker.MagicMock(spec=CoverCache)


@pytest.fixture
def mock_builder(mocker) -> Gtk.Builder:
    return mocker.MagicMock(spec=Gtk.Builder)


@pytest.fixture
def mock_glib_idle_source(mocker) -> Iterable[GLib.Source]:
    with mocker.patch(
        "comics_viewer.thumb.GLib.idle_source_new",
        spec=GLib.Source,
    ) as source:
        yield source


@pytest.fixture
def mock_flowbox(mocker):
    return mocker.MagicMock(spec=Gtk.FlowBox)


@pytest.fixture
def mock_scrolled_window(mocker):
    return mocker.MagicMock(spec=Gtk.ScrolledWindow)


def test_thumb_init(mock_view, mock_builder, mock_cover_cache, mock_flowbox,
                    mock_scrolled_window, mocker):
    mock_builder.get_object.side_effect = [mock_flowbox, mock_scrolled_window]
    thumb = Thumb(view=mock_view,
                  builder=mock_builder,
                  thumb_cache=mock_cover_cache,
                  library=Path("library"))
    mock_flowbox.bind_model.assert_called_once_with(mocker.ANY,
                                                    thumb.create_thumb)
    mock_cover_cache.start_idle.assert_called_once_with(Path("library"),
                                                        mocker.ANY)
    mock_flowbox.connect.assert_called_once_with("child-activated", mocker.ANY)


@pytest.fixture
def thumb(mock_view, mock_builder, mock_cover_cache, mock_flowbox,
          mock_scrolled_window):
    mock_builder.get_object.side_effect = [mock_flowbox, mock_scrolled_window]
    thumb = Thumb(view=mock_view,
                  builder=mock_builder,
                  thumb_cache=mock_cover_cache,
                  library=Path("library"))
    return thumb


def test_archive(thumb):
    assert thumb.archive is None
