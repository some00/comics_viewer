from typing import List, Any
from pathlib import Path
import numpy as np
import cv2
from difflib import SequenceMatcher
from enum import IntEnum
import numpy.typing as npt

from .gi_helpers import Gio, Gtk


RESOURCE_BASE_DIR = Path(__file__).parent


def scale_to_fit(dst, src):
    src_shape = np.array(src.shape[:2]).astype(float)
    scale = np.min(dst / src_shape)
    new_shape = (src_shape.astype(float) * scale).astype(int)
    return cv2.resize(src, np.flip(new_shape))


def imdecode(buf: bytes) -> npt.NDArray:
    return cv2.imdecode(np.frombuffer(buf, dtype=np.uint8), cv2.IMREAD_COLOR)


class Opcode(IntEnum):
    replace = 0
    delete = 1
    insert = 2
    equal = 3


def diff_opcodes(a, b):
    offset_i = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b).get_opcodes():
        i1 += offset_i
        i2 += offset_i
        if tag == Opcode.replace.name:
            yield Opcode.replace, i1, i2, j1, j2
        elif tag == Opcode.delete.name:
            yield Opcode.delete, i1, i2, j1, j2
            offset_i -= i2 - i1
        elif tag == Opcode.insert.name:
            yield Opcode.insert, i1, i2, j1, j2
            offset_i += j2 - j1
        elif tag == Opcode.equal.name:
            yield Opcode.equal, i1, i2, j1, j2


def wrap_add_action(add_action):
    def add_action(name, handler, add_action=add_action):
        rv = Gio.SimpleAction.new(name, None)
        rv.connect("activate", lambda *x, handler=handler: handler())
        add_action(rv)
        return rv
    return add_action


def refresh_gtk_model(model: Gtk.ListStore, target: List[Any],
                      offset: int = 0):
    ms = list(model)[offset:]
    for code, i1, i2, j1, j2 in diff_opcodes(ms, target):
        i1 += offset
        i2 += offset
        if code == Opcode.insert:
            for i, j in zip(range(i1, i1 + j2 - j1), range(j1, j2)):
                model.insert(i, target[j])
        elif code == Opcode.delete:
            for i in range(i1, i2):
                it = model.iter_nth_child(None, i1)
                if it is not None:
                    model.remove(it)
        elif code == Opcode.replace:
            for i, j in zip(range(i1, i2 + 1), range(j1, j2 + 1)):
                if i < len(model) and j < len(target):
                    model.set_row(model.iter_nth_child(None, i), target[j])
                elif i >= len(model) and j < len(target):
                    model.insert(i, target[j])
                elif j >= len(target) and i < len(model):
                    model.remove(model.iter_nth_child(None, i))


def refresh_gio_model(model: Gio.ListModel, target: List[Any]):
    ms = list(model)
    for code, i1, i2, j1, j2 in diff_opcodes(ms, target):
        if code == Opcode.insert or code == Opcode.replace:
            model[i1:i2] = target[j1:j2]
        elif code == Opcode.delete:
            del model[i1:i2]
