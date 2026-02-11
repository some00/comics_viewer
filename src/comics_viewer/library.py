from typing import Generator, Optional, Union, Dict, Iterable, cast
from pathlib import Path
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import create_engine
from sqlalchemy import Table
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import null
from itertools import chain
from enum import Enum

from .archive import ARCHIVE_TYPES, list_archive
from .cover_cache import CoverCache
from .gi_helpers import Gio, Gtk, GObject, GLib
from .utils import (
    wrap_add_action, refresh_gtk_model, refresh_gio_model, RESOURCE_BASE_DIR,
    image_to_pixbuf, get_object
)


COLLECTION_PREFIX = "collection_"
Base = declarative_base()


class FixedViews(Enum):
    cont = "continue"
    new = "new"
    unsorted = "unsorted"


class Lib(Base):
    __tablename__ = "library"
    id = Column(Integer, primary_key=True)
    path = Column(String, nullable=False)
    comics = relationship("Comics",
                          back_populates="lib",
                          cascade="all, delete-orphan")
    collections = relationship("Collection",
                               back_populates="lib",
                               cascade="all, delete-orphan")


collection_association_table = Table(
    "collection_association", Base.metadata,
    Column('comics_id', ForeignKey("comics.id")),
    Column('collection_id', ForeignKey("collection.id"))
)


class Comics(Base):
    __tablename__ = "comics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    pages: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)
    issue: Mapped[int] = mapped_column(Integer, nullable=True)
    cover_idx: Mapped[int] = mapped_column(Integer, nullable=True)

    progress = relationship("Progress",
                            back_populates="comics",
                            uselist=False,
                            cascade="all, delete-orphan")
    lib_id = Column(Integer, ForeignKey("library.id"), nullable=False)
    lib = relationship("Lib", back_populates="comics")

    collections = relationship(
        "Collection", secondary=collection_association_table,
        back_populates="comics")


class Progress(Base):
    __tablename__ = "progress"
    id = Column(Integer, primary_key=True)
    page_idx = Column(Integer, nullable=False)
    last_read = Column(DateTime, nullable=False)

    comics_id = Column(Integer, ForeignKey("comics.id"), nullable=False)
    comics = relationship("Comics", back_populates="progress")


class Collection(Base):
    __tablename__ = "collection"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    lib_id = Column(Integer, ForeignKey("library.id"), nullable=False)
    lib = relationship("Lib", back_populates="collections")

    comics = relationship("Comics", secondary=collection_association_table,
                          back_populates="collections")


class ComicsIcon(GObject.GObject):
    def __init__(self, comics: Comics):
        super().__init__()
        self.comics = comics
        self.progress = 0.0
        if (
            comics.progress is not None and
            comics.progress.page_idx is not None
        ):
            self.progress = comics.progress.page_idx / comics.pages

    def __hash__(self):
        return hash(self.to_tuple())

    def __eq__(self, other):
        return self.to_tuple() == other.to_tuple()

    def to_tuple(self):
        return (
            self.progress,
            self.comics.path,
            self.comics.pages,
            self.comics.cover_idx,
            self.comics.issue,
            self.comics.title,
        )


class Library:
    def __init__(self, library: Path, db: Path, cover_cache: CoverCache,
                 builder: Gtk.Builder, add_action, app):
        self._app = app
        self._library = library
        self._db = db
        self._cover_cache = cover_cache
        self._engine = create_engine(f"sqlite:///{db.absolute()}")
        self.list_store = Gio.ListStore()

        self.view = get_object(builder, Gtk.ComboBoxText, "library_view")
        self.view.connect("changed", lambda view: self.refresh_models())

        flowbox = get_object(builder, Gtk.FlowBox, "library")
        flowbox.bind_model(self.list_store, self.create_comics_box)
        flowbox.connect("child-activated", self.comics_activated)

        self._to_process: Generator[Union[Path, Comics]] = \
            (Path() for _ in range(0))
        self._idle_id: Optional[int] = None
        self._comics: Dict[Path, Comics] = {}
        Base.metadata.create_all(self._engine)

        with self.new_session as session, session.begin():
            lib = session.query(Lib).filter(
                Lib.path == str(library)).one_or_none()
            if lib is None:
                lib = Lib(path=str(library))
                session.add(lib)

        add_action = wrap_add_action(add_action)
        self.remove_collection = add_action("remove-collection",
                                            self.remove_collection_dialog)
        self.add_collection = add_action("add-collection",
                                         self.add_collection_dialog)
        self.refresh = add_action("refresh-library", self.start_refresh)
        self.refresh.set_enabled(self._idle_id is None)

    def start_refresh(self):
        session = self.new_session
        lib = session.query(Lib).filter(
            Lib.path == str(self._library)).one()
        self._to_process = (x for x in chain(
            self.iterate_library(),
            iter(session.query(Comics).filter(Comics.lib == lib)),
        ))
        self._idle_id = GLib.idle_add(self._iter_refresh, session, lib)
        self.set_action_states()

    def _iter_refresh(self, session: Session, lib: Lib):
        try:
            v = next(self._to_process)
        except StopIteration:
            session.commit()
            self._idle_id = None
            self.set_action_states()
            self.refresh_models()
            self._cover_cache.start_idle(
                self._library,
                [(Path(p), 0 if idx is None else idx) for p, idx in
                 self.new_session.query(
                     Comics.path, Comics.cover_idx).join(Lib).filter(
                         Lib.path == str(self._library)).all()])
            return GLib.SOURCE_REMOVE
        assert isinstance(v, (Path, Comics))
        if isinstance(v, Path):
            comics = session.query(Comics).filter(
                Comics.path == str(v)).filter(
                    Comics.lib == lib).one_or_none()
            pages = len(list_archive(self._library / v))
            if comics is None:
                session.add(Comics(
                    path=str(v),
                    pages=pages,
                    lib=lib,
                ))
            else:
                comics.pages = pages
                session.add(comics)
        elif isinstance(v, Comics):
            try:
                # pyrefly: ignore[bad-assignment]
                v.pages = len(list_archive(self._library / v.path))
                session.add(v)
            except IOError:
                session.delete(v)
        return GLib.SOURCE_CONTINUE

    def iterate_library(self) -> Iterable[Path]:
        for comics in sorted(map(
            lambda c: c.relative_to(self._library),
            chain.from_iterable(
                map(lambda e: self._library.rglob(f"*{e}"),
                    chain(ARCHIVE_TYPES.keys(),
                          map(lambda a: a.upper(), ARCHIVE_TYPES.keys()))))
        )):
            yield comics

    @property
    def path(self) -> Path:
        return self._library

    @property
    def last_viewed(self) -> Optional[Comics]:
        return self.new_session.query(Comics).join(Progress).filter(
            Comics.pages - 1 != Progress.page_idx
        ).order_by(Progress.last_read.desc()).limit(1).one_or_none()

    def create_comics_box(self, obj: ComicsIcon) -> Gtk.Widget:
        title, path, pages, cover_idx, progress, issue = (
            obj.comics.title,
            obj.comics.path,
            obj.comics.pages,
            obj.comics.cover_idx,
            obj.progress,
            obj.comics.issue,
        )
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR / "comics_icon.glade"))
        label = Path(cast(str, path)).name
        if title is not None:
            if issue is not None:
                label = f"{title} #{issue}"
            else:
                label = title
        label_widget = get_object(builder, Gtk.Label, "label")
        label_widget.set_label(cast(str, label))
        if pages:
            image_widget = get_object(builder, Gtk.Image, "image")
            image_widget.set_from_pixbuf(
                image_to_pixbuf(self._cover_cache.cover(
                    self._library, Path(cast(str, path)),
                    0 if cover_idx is None else cast(int, cover_idx)
                )))
        progress_widget = get_object(builder, Gtk.ProgressBar, "progress")
        progress_widget.set_fraction(progress)
        rv = get_object(builder, Gtk.Box, "icon")
        rv.comics = obj.comics  # pyrefly: ignore[missing-attribute]
        return rv

    def comics_activated(self, _, child):
        comics = child.get_child().comics
        page_idx = comics.progress.page_idx if (
            comics.progress is not None and
            comics.progress.page_idx is not None and
            comics.pages - 1 != comics.progress.page_idx
        ) else 0
        self._app.view_comics(self.path, comics, page_idx)

    def add_collection_dialog(self):
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR /
                                  "add_collection_dialog.glade"))
        dialog = get_object(builder, Gtk.Dialog, "dialog")
        ok = dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        ok.set_sensitive(False)
        name = get_object(builder, Gtk.Entry, "name")

        def changed(name):
            ok.set_sensitive(self.check_colleciton_name(name.get_text()))

        def activate(name):
            if self.check_colleciton_name(name.get_text()):
                assert isinstance(ok, Gtk.Button)
                ok.clicked()

        name.connect("changed", changed)
        name.connect("activate", activate)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        if dialog.run() == Gtk.ResponseType.OK:
            self.do_add_collection(name.get_text())
        dialog.destroy()

    @property
    def new_session(self):
        return Session(self._engine)

    def check_colleciton_name(self, name: str, session=None) -> bool:
        if session is None:
            session = self.new_session
        return bool(name) and 0 == session.query(Collection).filter_by(
            name=name).join(Lib).filter_by(path=str(self.path)).count()

    def do_add_collection(self, name: str) -> bool:
        with self.new_session as session, session.begin():
            if not self.check_colleciton_name(name, session):
                return False
            session.add(Collection(
                lib=session.query(Lib).filter(
                    Lib.path == str(self._library)).one(),
                name=name,
            ))
        self._refresh_view_model()
        return True

    def remove_collection_dialog(self):
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR /
                                  "remove_collection_dialog.glade"))
        label = get_object(builder, Gtk.Label, "label")
        label.set_text(label.get_text().format(
            collection=self.view.get_active_text()))
        dialog = get_object(builder, Gtk.Dialog, "dialog")
        dialog.add_buttons(Gtk.STOCK_YES, Gtk.ResponseType.OK,
                           Gtk.STOCK_NO, Gtk.ResponseType.CANCEL)
        if dialog.run() == Gtk.ResponseType.OK:
            text = self.view.get_active_text()
            assert isinstance(text, str)
            self.do_remove_collection(text)
        dialog.destroy()

    def do_remove_collection(self, name: str) -> bool:
        with self.new_session as session, session.begin():
            collection = session.query(Collection).filter(
                Collection.name == name).join(Lib).filter(
                    Lib.path == str(self._library)).one_or_none()
            if collection is not None:
                session.delete(collection)
        self._refresh_view_model()
        return False

    def set_action_states(self):
        idle = self._idle_id is None
        self.view.set_sensitive(idle)
        self.add_collection.set_enabled(idle)
        id = self.view.get_active_id()
        assert isinstance(id, str)
        self.remove_collection.set_enabled(
            idle and id.startswith(COLLECTION_PREFIX)
        )
        self.refresh.set_enabled(idle)

    def refresh_models(self):
        self._refresh_view_model()
        self._refresh_flowbox()
        self.set_action_states()

    def _refresh_flowbox(self):
        id = self.view.get_active_id()
        comics: Optional[Iterable[Comics]] = None
        if id == FixedViews.cont.value:
            comics = self.new_session.query(Comics).join(
                Progress).filter(Comics.pages - 1 != Progress.page_idx
                                 ).order_by(Progress.last_read.desc())
        elif id == FixedViews.new.value:
            comics = self.new_session.query(Comics).filter(
                Comics.title == null(),
                Comics.issue == null()
            )
        elif id == FixedViews.unsorted.value:
            comics = self.new_session.query(Comics).outerjoin(
                collection_association_table
            ).filter_by(comics_id=None).distinct().order_by(Comics.path)
        elif id is None:
            self.view.set_active_id(FixedViews.cont.value)
        elif id.startswith(COLLECTION_PREFIX):
            collection_name = id[len(COLLECTION_PREFIX):]
            comics = self.new_session.query(Comics).join(Collection.comics) \
                .filter(Collection.name == collection_name) \
                .order_by(Comics.title, Comics.issue, Comics.path)

        if comics is not None:
            refresh_gio_model(self.list_store, list(map(ComicsIcon, comics)))

    def _refresh_view_model(self):
        new = [(x, f"{COLLECTION_PREFIX}{x}") for x in chain.from_iterable(
            self.new_session.query(Collection.name).join(Lib).filter_by(
                path=str(self.path)).order_by(Collection.name).all()
        )]
        offset = len(FixedViews.__members__)
        model = self.view.get_model()
        assert isinstance(model, Gtk.ListStore)
        refresh_gtk_model(model, new, offset)
