from pathlib import Path
import numpy as np
from functools import partial
from contextlib import ExitStack
import signal

from .library import Library
from .view import View
from .app import App
from .cover_cache import CoverCache
from .gi_helpers import GLib


def main():
    with ExitStack() as stack:
        TEMP = Path("./data/cache").absolute()
        create_library = partial(
            Library,
            library=Path("~/tmp/foo").expanduser().absolute(),
            db=Path("./data/db.sqlite").absolute(),
            cover_cache=stack.enter_context(
                CoverCache(TEMP / "cover", np.array([240, 240]))
            ),
        )
        create_view = partial(View, thumb_cache=stack.enter_context(
            CoverCache(TEMP / "thumb", np.array([120, 120]))
        ))
        app = App(stack, create_library, create_view,
                  application_id="com.gitlab.some00.comics_viewer",)
        for sig in [signal.SIGINT, signal.SIGTERM]:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig,
                                 lambda *x: app.quit(), None)
        app.run()


main()
