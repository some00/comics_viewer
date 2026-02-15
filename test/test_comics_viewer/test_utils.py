import pytest
from PIL.Image import Image
from pathlib import Path
import numpy as np
from comics_viewer.utils import (
    image_shape, imdecode, imencode, diff_opcodes, Opcode, wrap_add_action,
    refresh_gtk_model, refresh_gio_model, dfs_gen, image_to_pixbuf, is_in
)
from comics_viewer.gi_helpers import Gtk, Gio, GObject, GdkPixbuf


@pytest.fixture
def mock_image(mocker):
    return mocker.MagicMock(Image)


def test_image_shape(mock_image):
    img = mock_image()
    img.size = (2, 4)
    coords = image_shape(img)
    assert coords.x == 2
    assert coords.y == 4


def test_imdecode(mocker):
    mock_image = mocker.patch("comics_viewer.utils.image")
    rv = imdecode(b"\0")
    mock_image.open.assert_called_once()
    im = mock_image.open.return_value.__enter__.return_value
    assert rv == im.convert.return_value
    im.convert.assert_called_once_with("RGB")


def test_imencode(mock_image, mocker):
    img = mock_image()
    rv = imencode(img)
    assert rv == b""
    img.save.assert_called_once_with(mocker.ANY, format="PNG")


@pytest.mark.parametrize("a, b, expected", [
    ([0, 1, 2, 3], [0, 1, 2, 3], [(Opcode.equal, 0, 4, 0, 4)]),
    ([0, 1, 2, 3], [0, 1, 2], [(Opcode.equal, 0, 3, 0, 3),
                               (Opcode.delete, 3, 4, 3, 3)]),
    ([0, 1, 2, 3], [4, 5, 6, 7], [(Opcode.replace, 0, 4, 0, 4)]),
    ([0, 1, 2, 3], [-1, 0, 1, 2, 3], [(Opcode.insert, 0, 0, 0, 1),
                                      (Opcode.equal, 1, 5, 1, 5)]),
])
def test_diff_opcodes(a, b, expected):
    assert list(diff_opcodes(a, b)) == expected


def test_wrap_add_action(mocker):
    mock_gio = mocker.patch("comics_viewer.utils.Gio")
    mock_add_action = mocker.MagicMock()
    add_action = wrap_add_action(mock_add_action)
    mock_handler = mocker.MagicMock()
    rv = add_action("name", mock_handler)
    mock_gio.SimpleAction.new.assert_called_once_with("name", None)
    rv_mock = mock_gio.SimpleAction.new.return_value
    assert rv == rv_mock
    rv_mock.connect.assert_called_once_with("activate", mocker.ANY)


def decorate_model_data(func):
    return pytest.mark.parametrize("model_data, target", [
        ([0, 1, 2, 3], [0, 1, 2, 3]),
        ([0, 1, 3], [0, 1, 2, 3]),
        ([0, 1, 2, 3], [0, 2, 3]),
        ([0, 1, 2, 4], [0, 1, 2, 3]),
        ([], [0, 1, 2, 3]),
        ([0, 1, 2, 3], []),
    ])(func)


@decorate_model_data
def test_refresh_gtk_model(model_data, target):
    builder = Gtk.Builder.new_from_string(
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <interface>
            <requires lib="gtk+" version="3.24"/>
            <object class="GtkListStore" id="model">
                <columns>
                    <column type="gint"/>
                    <column type="gint"/>
                </columns>
            </object>
        </interface>
        """, -1)
    model = builder.get_object("model")
    assert isinstance(model, Gtk.ListStore)
    for x in model_data:
        model.append((x, 0))
    target = [(x, 0) for x in target]
    refresh_gtk_model(model, target)
    assert [(x[0], 0) for x in model] == target


@decorate_model_data
def test_refresh_gio_model(model_data, target):
    class Elem(GObject.GObject):
        def __init__(self, value):
            super().__init__()
            self.value = value
    model = Gio.ListStore()
    [model.append(Elem(x)) for x in model_data]
    refresh_gio_model(model, list(map(Elem, target)))
    model_content = []
    for x in model:
        assert isinstance(x, Elem)
        model_content.append(x.value)
    assert model_content == target


def test_dfs_gen_empty_folder(mocker):
    root = mocker.MagicMock(Path)
    root.iterdir.return_value = []
    assert [] == list(dfs_gen(root))


def test_dfs_gen_one_file(mocker):
    root = mocker.MagicMock(Path)
    file = mocker.MagicMock(Path)
    root.iterdir.return_value = [file]
    file.is_dir.return_value = False
    file.is_symlink.return_value = False

    assert [file.relative_to.return_value] == list(dfs_gen(root))
    file.relative_to.assert_called_once_with(root)


def test_dfs_gen_subfolder(mocker):
    root = mocker.MagicMock(Path)
    sub = mocker.MagicMock(Path)
    file = mocker.MagicMock(Path)
    root.iterdir.return_value = [sub]
    sub.iterdir.return_value = [file]
    sub.is_symlink.return_value = False
    file.is_symlink.return_value = False

    assert [file.relative_to.return_value,
            sub.relative_to.return_value] == list(dfs_gen(root))
    file.relative_to.assert_called_once_with(root)
    sub.relative_to.assert_called_once_with(root)


def test_image_to_pixbuf():
    from PIL import Image
    image = Image.new("RGB", (10, 20))
    pixbuf = image_to_pixbuf(image)
    assert image.tobytes() == pixbuf.get_pixels()
    assert GdkPixbuf.Colorspace.RGB == pixbuf.get_colorspace()
    assert not pixbuf.get_has_alpha()
    assert 8 == pixbuf.get_bits_per_sample()
    assert 20 == pixbuf.get_height()
    assert 10 == pixbuf.get_width()
    assert 30 == pixbuf.get_rowstride()


@pytest.mark.parametrize("x0, y0, x1, y1, expected", [
    (10, 10, 5, 5, np.array([5, 5], dtype=np.float64)),
    (10, 10, 5, 11, None),
    (10, 15, 5, 15, np.array([5, 15], dtype=np.float64)),
    (10, 15, 11, 15, None),
    (10, 15, -10, 15, None),
])
def test_is_in(x0, y0, x1, y1, mocker, expected):
    widget = mocker.MagicMock(Gtk.Widget)
    widget.get_allocation.return_value.width = x0
    widget.get_allocation.return_value.height = y0
    rv = is_in(widget, x1, y1)
    if expected is None:
        assert rv is None
    else:
        assert np.all(expected == rv)
