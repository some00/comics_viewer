import numpy as np
import cv2
from difflib import SequenceMatcher
from enum import IntEnum


def scale_to_fit(dst, src):
    src_shape = np.array(src.shape[:2]).astype(float)
    scale = np.min(dst / src_shape)
    new_shape = (src_shape.astype(float) * scale).astype(int)
    return cv2.resize(src, np.flip(new_shape))


def imdecode(buf: bytes):
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
