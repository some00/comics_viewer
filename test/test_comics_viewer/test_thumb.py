import pytest
from typing import Iterable
from pathlib import Path
from PIL import Image as image

from comics_viewer.thumb import PageInfo, Thumb
from comics_viewer.gi_helpers import GObject, Gtk, GLib
from comics_viewer.view import View
from comics_viewer.cover_cache import CoverCache
from comics_viewer.archive import Archive


BASE_DIR = Path(__file__).parent.parent / "data"


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
    return mocker.patch("comics_viewer.thumb.GLib.idle_source_new",
                        spec=GLib.Source)


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
                  library=BASE_DIR)
    return thumb


def test_archive_none(thumb):
    assert thumb.archive is None


@pytest.fixture
def mock_builder_in_source(mocker) -> Gtk.Builder:
    return mocker.patch("comics_viewer.thumb.Gtk.Builder",
                        spec=Gtk.Builder)


@pytest.fixture
def mock_box(mocker):
    return mocker.MagicMock(spec=Gtk.Box)


@pytest.fixture
def mock_img(mocker):
    return mocker.MagicMock(spec=Gtk.Image)


@pytest.fixture
def mock_label(mocker):
    return mocker.MagicMock(spec=Gtk.Label)


def test_create_thumb(
    thumb, mock_builder_in_source, mock_glib_idle_source, mock_box, mock_img,
    mock_label,
):
    builder = mock_builder_in_source.return_value
    builder.get_object.side_effect = [mock_img, mock_label, mock_box]
    box = thumb.create_thumb(PageInfo(path=Path("a.cbz"), page_idx=5))
    assert box == mock_box
    assert box.page_idx == 5
    builder.add_from_file.assert_called()
    mock_label.set_label.assert_called_once_with("6")
    mock_glib_idle_source.assert_called_once()


@pytest.fixture
def thumb_create_thumb_called(
    thumb, mock_builder_in_source, mock_glib_idle_source, mock_box, mock_img,
    mock_label,
):
    mock_glib_idle_source  # silence unused
    thumb.archive = Archive(BASE_DIR / "zip.cbz")
    builder = mock_builder_in_source.return_value
    builder.get_object.side_effect = [mock_img, mock_label, mock_box]
    thumb.create_thumb(PageInfo(path=Path("zip.cbz"), page_idx=0))
    return thumb


def test_idle(
    thumb_create_thumb_called, mock_glib_idle_source, mocker, mock_cover_cache,
):
    thumb_create_thumb_called  # silence unused
    mock_glib_idle_source  # silence unused
    idle = mock_glib_idle_source.return_value
    idle.set_callback.assert_called_once()
    callback = idle.set_callback.call_args_list[0][0][0]

    mock_cover_cache.cover.return_value = image.new('RGB', (64, 64))
    rv = callback(mocker.ANY)
    mock_cover_cache.cover.assert_called_once_with(
        BASE_DIR, Path("zip.cbz"), 0
    )
    assert rv == GLib.SOURCE_CONTINUE

    rv = callback(mocker.ANY)
    assert rv == GLib.SOURCE_REMOVE


def test_archive_set_twice(thumb_create_thumb_called, mock_glib_idle_source):
    thumb = thumb_create_thumb_called
    thumb.archive = Archive(BASE_DIR / "rar.cbr")
    mock_glib_idle_source.return_value.destroy.assert_called_once()


def test_ensure_idle_twice(
    thumb_create_thumb_called, mock_glib_idle_source, mock_box, mock_label,
    mock_img, mock_builder_in_source,
):
    thumb = thumb_create_thumb_called
    builder = mock_builder_in_source.return_value
    builder.get_object.side_effect = [mock_img, mock_label, mock_box]
    thumb.create_thumb(PageInfo(Path("rar.cbr"), page_idx=1))
    mock_glib_idle_source.assert_called_once()


def test_page_activated(thumb, mock_flowbox, mocker, mock_view):
    thumb  # silence unused
    callback = mock_flowbox.connect.call_args_list[0][0][1]
    child = mocker.MagicMock(spec=Gtk.Bin)
    child.get_child.return_value.page_idx = 2
    callback(mocker.ANY, child)
    assert mock_view.page_idx == 2


def test_scroll_to(thumb, mock_flowbox, mock_scrolled_window):
    thumb.scroll_to(5)
    child = mock_flowbox.get_child_at_index.return_value
    mock_flowbox.select_child.assert_called_once_with(child)
    mock_scrolled_window.get_vadjustment.return_value \
        .set_value.assert_called_once_with(child.get_allocation.return_value.y)


def test_scroll_to_no_such_page(thumb, mock_flowbox):
    mock_flowbox.get_child_at_index.return_value = None
    thumb.scroll_to(5)
    mock_flowbox.select_child.assert_not_called()
