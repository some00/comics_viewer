from pathlib import Path
from .library import Library
from .app import App
from .cover_cache import CoverCache
import numpy as np
from functools import partial


def abs(p: str):
    return Path(p).absolute()


create_library = partial(
    Library,
    library=Path("~/tmp/foo").expanduser().absolute(),
    db=abs("./data/db.sqlite"),
    cover_cache=CoverCache(abs("./data/cache"), np.array([240, 240])),
)
App(create_library).run()
