from typing import Callable, Set, Optional
from enum import IntEnum

from .library import Library, Collection, Comics, Lib
from .gi_helpers import Gtk, Gio
from .utils import wrap_add_action, refresh_gtk_model, get_object

STACK_NAME = "manage"
TVC = Gtk.TreeViewColumn


class ComicsColumn(IntEnum):
    path = 0
    title = 1
    issue = 2
    cover = 3
    id = 4


class CollectionColumn(IntEnum):
    collection = 0
    contained = 1
    id = 2


class Manage:
    def __init__(self, library: Library, builder: Gtk.Builder,
                 add_action: Callable[[Gio.Action], None]):
        self._library = library
        self._session = self._library.new_session
        self._clipboard_title: Optional[str] = None

        add_action_wrapped = wrap_add_action(add_action)
        self._save_action = add_action_wrapped("save-manage", self.save)
        self._discard_action = add_action_wrapped("discard-manage",
                                                  self.discard)
        self._autoincrement_action = add_action_wrapped("autoincrement-manage",
                                                        self.autoincrement)
        self._autoincrement_action.set_enabled(False)
        self._copy_title_action = add_action_wrapped("copy-title-manage",
                                                     self.copy_title)
        self._paste_title_action = add_action_wrapped("paste-title-manage",
                                                      self.paste_title)

        title_renderer = Gtk.CellRendererText(editable=True)
        title_renderer.connect("edited", self._title_edited)
        issue_renderer = Gtk.CellRendererText(editable=True)
        issue_renderer.connect("edited", self._issue_edited)
        cover_renderer = Gtk.CellRendererText(editable=True)
        cover_renderer.connect("edited", self._cover_edited)
        self._comics = builder.get_object("manage_comics")
        assert isinstance(self._comics, Gtk.TreeView)
        self._comics.append_column(TVC("Path",
                                       Gtk.CellRendererText(),
                                       text=ComicsColumn.path))
        self._comics.append_column(TVC("Title",
                                       title_renderer,
                                       text=ComicsColumn.title))
        self._comics.append_column(TVC("Issue",
                                       issue_renderer,
                                       text=ComicsColumn.issue))
        self._comics.append_column(TVC("Cover Page",
                                       cover_renderer,
                                       text=ComicsColumn.cover))
        self._comics.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self._comics.get_selection().connect("changed", self._comics_changed)

        self._contained_renderer = Gtk.CellRendererToggle()
        self._contained_renderer.connect("toggled", self._contained_changed)
        self._contained_renderer.set_sensitive(False)
        collections = builder.get_object("manage_collections")
        assert isinstance(collections, Gtk.TreeView)
        self._collections = collections
        self._collections.append_column(TVC("Collection",
                                            Gtk.CellRendererText(),
                                            text=CollectionColumn.collection))
        self._collections.append_column(TVC("Comics Contained",
                                            self._contained_renderer,
                                            active=CollectionColumn.contained))
        self._collections.get_selection().set_mode(Gtk.SelectionMode.NONE)

        self._stack = builder.get_object("stack")
        self._switcher = get_object(builder, Gtk.StackSwitcher, "switcher")

        self._set_session_action_states()
        self._set_clipboad_action_states()

    @property
    def dirty(self) -> bool:
        return any(map(bool, (
            self._session.dirty,
            self._session.new,
            self._session.deleted,
        )))

    def save(self):
        self._session.commit()
        self._set_session_action_states()

    def discard(self):
        self._session.rollback()
        self.refresh()
        self._set_session_action_states()

    def _set_session_action_states(self):
        self._switcher.set_sensitive(not self.dirty)
        self._save_action.set_enabled(self.dirty)
        self._discard_action.set_enabled(self.dirty)

    def _set_clipboad_action_states(self):
        copy = False
        paste = False
        if self._stack.get_visible_child_name() == STACK_NAME:
            model, paths = self._comics.get_selection().get_selected_rows()
            if len(paths) == 1:
                copy = bool(model[paths[0]][ComicsColumn.title])
            if paths and self._clipboard_title:
                paste = True
        self._copy_title_action.set_enabled(copy)
        self._paste_title_action.set_enabled(paste)

    def refresh(self):
        self._refresh_comics()
        self._refresh_collections()
        self._comics.get_selection().unselect_all()
        self._set_clipboad_action_states()

    def _refresh_comics(self):
        comics = self._session.query(
            Comics.path, Comics.title, Comics.issue, Comics.cover_idx,
            Comics.id,
        ).join(Lib).filter_by(path=str(self._library.path)
                              ).order_by(Comics.path).all()
        comics = [(
            path,
            "" if title is None else title,
            0 if issue is None else issue,
            1 if cover_idx is None else cover_idx + 1,
            id,
        ) for (path, title, issue, cover_idx, id) in comics]
        refresh_gtk_model(self._comics.get_model(), comics)

    def _refresh_collections(self):
        collections = [(row[0], False, row[1]) for row in self._session.query(
            Collection.name, Collection.id).join(Lib).filter_by(
                path=str(self._library.path)).order_by(Collection.name).all()]
        refresh_gtk_model(self._collections.get_model(), collections)

    def _comics_changed(self, selection: Gtk.TreeSelection):
        model, paths = selection.get_selected_rows()
        self._autoincrement_action.set_enabled(len(paths) > 1)
        selected: Optional[Set[int]] = None
        for id in map(lambda p: model[p][-1], paths):
            comics = self._comics_by_id(id)
            if selected is None:
                selected = {c.id for c in comics.collections}
            elif selected != {c.id for c in comics.collections}:
                selected = None
                break
        model = self._collections.get_model()
        self._contained_renderer.set_sensitive(selected is not None)
        for idx, id in enumerate([row[CollectionColumn.id] for row in model]):
            model.set_value(model.iter_nth_child(None, idx),
                            CollectionColumn.contained,
                            selected is not None and id in selected)
        self._set_clipboad_action_states()

    def autoincrement(self):
        model, paths = self._comics.get_selection().get_selected_rows()
        rows = [model[p] for p in paths]
        ids = [row[ComicsColumn.id] for row in rows]
        comics = self._session.query(Comics).filter(Comics.id.in_(ids)).all()
        first = None
        for idx, (it, c) in enumerate(zip([model.get_iter(p) for p in paths],
                                          comics)):
            if first is None:
                first = model.get_value(it, ComicsColumn.issue)
            issue = first + idx
            if issue == c.issue:
                continue
            model.set_value(it, ComicsColumn.issue, issue)
            c.issue = issue
            self._session.add(c)
        self._set_session_action_states()

    def _contained_changed(self, renderer, path):
        model, paths = self._comics.get_selection().get_selected_rows()
        ids = [model[p][ComicsColumn.id] for p in paths]
        comics = self._session.query(Comics).filter(Comics.id.in_(ids)).all()
        model = self._collections.get_model()
        it = model.get_iter(path)
        new = not model.get_value(it, CollectionColumn.contained)
        model.set_value(it, CollectionColumn.contained, new)
        id = model.get_value(it, CollectionColumn.id)
        collection = self._session.query(Collection).filter_by(id=id).one()
        if new:
            [c.collections.append(collection) for c in comics]
        else:
            [c.collections.remove(collection) for c in comics]
        [self._session.add(c) for c in comics]
        self._set_session_action_states()

    def _title_edited(self, renderer, path, new_text):
        model = self._comics.get_model()
        model.set_value(model.get_iter(path), ComicsColumn.title, new_text)
        new_text = new_text if new_text else None
        comics = self._comics_by_id(model[path][ComicsColumn.id])
        if comics.title == new_text:
            return
        comics.title = new_text
        self._session.add(comics)
        self._set_session_action_states()
        self._set_clipboad_action_states()

    def _issue_edited(self, renderer, path, new_text):
        try:
            issue = int(new_text)
        except ValueError:
            return
        model = self._comics.get_model()
        model.set_value(model.get_iter(path), ComicsColumn.issue, issue)
        comics = self._comics_by_id(model[path][ComicsColumn.id])
        if comics.issue == issue:
            return
        comics.issue = issue
        self._session.add(comics)
        self._set_session_action_states()

    def _cover_edited(self, renderer, path, new_text):
        try:
            cover_idx = int(new_text) - 1
        except ValueError:
            return
        model = self._comics.get_model()
        comics = self._comics_by_id(model[path][ComicsColumn.id])
        if 0 > cover_idx or cover_idx >= comics.pages:
            return
        model.set_value(model.get_iter(path),
                        ComicsColumn.cover, cover_idx + 1)
        if comics.cover_idx == cover_idx:
            return
        comics.cover_idx = cover_idx
        self._session.add(comics)
        self._set_session_action_states()

    def _comics_by_id(self, id: int) -> Comics:
        return self._session.query(Comics).filter_by(id=id).one()

    def copy_title(self):
        model, paths = self._comics.get_selection().get_selected_rows()
        if len(paths) != 1:
            return
        self._clipboard_title = model[paths[0]][ComicsColumn.title]
        if not self._clipboard_title:
            self._clipboard_title = None
        self._set_clipboad_action_states()

    def paste_title(self):
        if self._clipboard_title is None:
            return
        model, paths = self._comics.get_selection().get_selected_rows()
        [model.set_value(model.get_iter(p),
                         ComicsColumn.title,
                         self._clipboard_title) for p in paths]
        ids = set(model[p][ComicsColumn.id] for p in paths)
        for comics in self._session.query(Comics).filter(Comics.id.in_(ids)):
            if comics.title == self._clipboard_title:
                continue
            comics.title = self._clipboard_title
            self._session.add(comics)
        self._set_session_action_states()
