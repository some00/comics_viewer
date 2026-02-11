from pathlib import Path
import numpy as np
from functools import partial
from contextlib import ExitStack
import signal
import argparse
import sys

from .library import Library
from .view import View
from .app import App, AddAction
from .cover_cache import CoverCache
from .gi_helpers import GLib, Gtk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=Path("./data/cache"), type=Path)
    parser.add_argument("--library", default=Path("~/tmp/foo").expanduser(),
                        type=Path)
    parser.add_argument("--database", type=Path,
                        default=Path("./data/db.sqlite").absolute())
    args = parser.parse_args()

    with ExitStack() as stack:
        TEMP = args.cache
        def create_library(builder: Gtk.Builder,
                           app: App,
                           add_action: AddAction) -> Library:
            return Library(
                builder=builder,
                app=app,
                add_action=add_action,
                library=args.library.expanduser().absolute(),
                db=args.database.absolute(),
                cover_cache=stack.enter_context(
                    CoverCache(TEMP / "cover", np.array([240, 240]))
                )
            )

        create_view = partial(View, thumb_cache=stack.enter_context(
            CoverCache(TEMP / "thumb", np.array([120, 120]))
        ))
        app = App(stack, create_library, create_view,
                  application_id="com.github.some00.comics_viewer",)
        for sig in [signal.SIGINT, signal.SIGTERM]:
            def handler(*_) -> bool:
                app.quit()
                return False
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, handler, None)
        app.run(sys.argv)


main()
