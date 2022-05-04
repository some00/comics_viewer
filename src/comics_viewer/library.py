from typing import Iterable, Optional, Tuple, Union, Dict
from pathlib import Path
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import create_engine
from sqlalchemy import Table
from sqlalchemy.orm import Session
from sqlalchemy.orm import relationship
from itertools import chain
from operator import itemgetter
from bisect import bisect
from enum import Enum
import numpy.typing as npt
import cv2

from .archive import ARCHIVE_TYPES, list_archive
from .cover_cache import CoverCache
from .gi_helpers import Gio, Gtk, GObject, GLib, GdkPixbuf


COLLECTION_PREFIX = "collection_"
RESOURCE_BASE_DIR = Path(__file__).parent
Base = declarative_base()


def np_to_pixbuf(arr: npt.NDArray) -> GdkPixbuf.Pixbuf:
    return GdkPixbuf.Pixbuf.new_from_data(
        data=cv2.cvtColor(arr, cv2.COLOR_BGR2RGB).tobytes(),
        colorspace=GdkPixbuf.Colorspace.RGB,
        has_alpha=False,
        bits_per_sample=8,
        width=arr.shape[1],
        height=arr.shape[0],
        rowstride=arr.shape[1] * 3)


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
    id = Column(Integer, primary_key=True)
    path = Column(String, nullable=False, unique=True)
    pages = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    issue = Column(Integer, nullable=True)
    cover_idx = Column(Integer, nullable=True)

    progress = relationship("Progress", back_populates="comics", uselist=False)
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

    comics_id = Column(Integer, ForeignKey("comics.id"))
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


def compare_comics_icon(a: ComicsIcon, b: ComicsIcon):
    a = Path(a.comics.path)
    b = Path(b.comics.path)
    if a < b:
        return -1
    elif a > b:
        return 1
    else:
        return 0


class Library:
    def __init__(self, library: Path, db: Path, cover_cache: CoverCache):
        self._library = library
        self._db = db
        self._cover_cache = cover_cache
        self._engine = create_engine(f"sqlite:///{db.absolute()}")
        self.list_store = Gio.ListStore()
        self._view: Optional[Gtk.ComboBoxText] = None
        self._remove_collection: Optional[Gio.SimpleAction] = None
        self._refresh: Optional[Gio.SimpleAction] = None
        self._to_process: Iterable[Union[Path, Comics, Collection]] = []
        self._idle_id: Optional[int] = None
        self._comics: Dict[Path, Comics] = {}
        Base.metadata.create_all(self._engine)

        with self.new_session as session, session.begin():
            lib = session.query(Lib).filter(
                Lib.path == str(library)).one_or_none()
            if lib is None:
                lib = Lib(path=str(library))
                session.add(lib)

    def start_refresh(self):
        if self.refresh:
            self.refresh.set_enabled(False)
        session = self.new_session
        lib = session.query(Lib).filter(
            Lib.path == str(self._library)).one()
        self.remove_collections_from_view()
        self._to_process = chain(
            self.iterate_library(),
            iter(session.query(Comics).filter(Comics.lib == lib)),
            iter(session.query(Collection).filter(
                Collection.lib == lib).order_by(Collection.name)),
        )
        self._idle_id = GLib.idle_add(self._iter_refresh, session, lib)

    def _iter_refresh(self, session: Session, lib: Lib):
        try:
            v = next(self._to_process)
        except StopIteration:
            session.commit()
            if self.refresh:
                self.refresh.set_enabled(True)
            self._idle_id = None
            if self.view:
                self.view_changed(self.view)
            self._cover_cache.start_idle(
                self._library,
                [(Path(p), 0 if idx is None else idx) for p, idx in
                 self.new_session.query(
                     Comics.path, Comics.cover_idx).join(Lib).filter(
                         Lib.path == str(self._library)).all()])
            return GLib.SOURCE_REMOVE
        assert(isinstance(v, (Path, Comics, Collection)))
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
                v.pages = pages = len(list_archive(self._library / v.path))
                session.add(v)
            except IOError:
                session.delete(v)
        elif self.view:
            self.view.get_model().append(
                (v.name, f"{COLLECTION_PREFIX}{v.name}"))
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
    def last_viewed(self) -> Optional[Tuple[Path, int]]:
        return None

    @property
    def view(self) -> Optional[Gtk.ComboBoxText]:
        return self._view

    @property
    def remove_collection(self) -> Optional[Gio.SimpleAction]:
        return self._remove_collection

    @property
    def refresh(self) -> Optional[Gio.SimpleAction]:
        return self._refresh

    @refresh.setter
    def refresh(self, refresh: Gio.SimpleAction):
        refresh.set_enabled(self._idle_id is None)
        refresh.connect("activate", lambda *x: self.start_refresh())
        self._refresh = refresh

    @remove_collection.setter
    def remove_collection(self, remove_collection):
        remove_collection.set_enabled(bool(
            self.view and
            self.view.get_active_id().startswith(COLLECTION_PREFIX)
        ))
        remove_collection.connect("activate", self.remove_collection_dialog)
        self._remove_collection = remove_collection

    @view.setter
    def view(self, view):
        self._view = view
        self._view.connect("changed", self.view_changed)
        self.view_changed(self._view)

    def view_changed(self, view):
        id = view.get_active_id()
        remove_enabled = False
        self.list_store.remove_all()
        if id == FixedViews.cont.value:
            pass
        elif id == FixedViews.new.value:
            self.show_new()
        elif id == FixedViews.unsorted.value:
            self.show_unsorted()
        elif id is None:
            view.set_active_id(FixedViews.cont.value)
        elif id.startswith(COLLECTION_PREFIX):
            remove_enabled = True

        if self.remove_collection:
            self.remove_collection.set_enabled(remove_enabled)

    def create_comics_box(self, obj: ComicsIcon):
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR / "comics_icon.glade"))
        builder.get_object("label").set_label(
            obj.comics.title
            if obj.comics.title else Path(obj.comics.path).name)
        if obj.comics.pages:
            # TODO no pages
            builder.get_object("image").set_from_pixbuf(
                np_to_pixbuf(self._cover_cache.cover(
                    self._library, Path(obj.comics.path),
                    0 if obj.comics.cover_idx is None else obj.comics.cover_idx
                )))
        return builder.get_object("icon")

    def add_collection_dialog(self, action, target):
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR /
                                  "add_collection_dialog.glade"))
        dialog = builder.get_object("dialog")
        ok = dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        ok.set_sensitive(False)
        name = builder.get_object("name")

        def changed(name):
            sensitive = False
            text = name.get_text()
            if text:
                sensitive = self.check_colleciton_name(text)
            ok.set_sensitive(sensitive)

        name.connect("changed", changed)
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
        return 0 == session.query(Lib).filter(
            Lib.path == str(self._library)).join(Collection).filter(
                Collection.name == name).count()

    def do_add_collection(self, name: str) -> bool:
        with self.new_session as session, session.begin():
            if not self.check_colleciton_name(name, session):
                return False
            session.add(Collection(
                lib=session.query(Lib).filter(
                    Lib.path == str(self._library)).one(),
                name=name,
            ))
            if self.view:
                names = list(map(itemgetter(0), self.view.get_model()))
                idx = bisect(names, name, lo=len(FixedViews.__members__))
                self.view.get_model().insert(
                    idx, (name, f"{COLLECTION_PREFIX}{name}"))
        return True

    def remove_collection_dialog(self, action, target):
        builder = Gtk.Builder()
        builder.add_from_file(str(RESOURCE_BASE_DIR /
                                  "remove_collection_dialog.glade"))
        label = builder.get_object("label")
        label.set_text(label.get_text().format(
            collection=self.view.get_active_text()))
        dialog = builder.get_object("dialog")
        dialog.add_buttons(Gtk.STOCK_YES, Gtk.ResponseType.OK,
                           Gtk.STOCK_NO, Gtk.ResponseType.CANCEL)
        if dialog.run() == Gtk.ResponseType.OK:
            self.do_remove_collection(self.view.get_active_text())
        dialog.destroy()

    def do_remove_collection(self, name: str) -> bool:
        with self.new_session as session, session.begin():
            collection = session.query(Collection).filter(
                Collection.name == name).join(Lib).filter(
                    Lib.path == str(self._library)).one_or_none()
            if collection is not None:
                session.delete(collection)
                for idx, (n, _) in enumerate(self.view.get_model()
                                             if self.view else []):
                    if n == name:
                        del self.view.get_model()[idx]
                        break
                return True
        return False

    def remove_collections_from_view(self):
        if self.view is None:
            return
        model = self.view.get_model()
        to_remove = []
        for row in model:
            if row[1].startswith(COLLECTION_PREFIX):
                to_remove.append(model.get_iter(row.path))
                continue
        [model.remove(i) for i in to_remove]

    def show_unsorted(self):
        pass

    def show_new(self):
        for comics in self.new_session.query(Comics
                                             ).filter_by(title=None,
                                                         issue=None):
            self.list_store.insert_sorted(ComicsIcon(comics),
                                          compare_comics_icon)
