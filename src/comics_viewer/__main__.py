from pathlib import Path
from .library import Library
from .app import App
from .cover_cache import CoverCache
import numpy as np


def abs(p: str):
    return Path(p).absolute()


App(Library(
    Path("~/tmp/foo").expanduser().absolute(),
    abs("./data/db.sqlite"),
    CoverCache(abs("./data/cache"), np.array([240, 240])),
)).run()
