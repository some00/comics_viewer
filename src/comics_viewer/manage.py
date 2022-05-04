from typing import Callable, Set, Optional
from enum import IntEnum

from .library import Library, Collection, Comics, Lib
from .gi_helpers import Gtk, Gio
from .utils import diff_opcodes, Opcode

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

        def add_action(name, handler, add_action=add_action):
            rv = Gio.SimpleAction.new(name, None)
            rv.connect("activate", lambda *x, handler=handler: handler())
            add_action(rv)
            return rv
        self._save_action = add_action("save-manage", self.save)
        self._discard_action = add_action("discard-manage", self.discard)
        self._autoincrement_action = add_action("autoincrement-manage",
                                                self.autoincrement)
        self._autoincrement_action.set_enabled(False)
        self._copy_title_action = add_action("copy-title-manage",
                                             self.copy_title)
        self._paste_title_action = add_action("paste-title-manage",
                                              self.paste_title)

        title_renderer = Gtk.CellRendererText(editable=True)
        title_renderer.connect("edited", self._title_edited)
        issue_renderer = Gtk.CellRendererText(editable=True)
        issue_renderer.connect("edited", self._issue_edited)
        cover_renderer = Gtk.CellRendererText(editable=True)
        cover_renderer.connect("edited", self._cover_edited)
        self._comics = builder.get_object("manage_comics")
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
        self._collections = builder.get_object("manage_collections")
        self._collections.append_column(TVC("Collection",
                                            Gtk.CellRendererText(),
                                            text=CollectionColumn.collection))
        self._collections.append_column(TVC("Comics Contained",
                                            self._contained_renderer,
                                            active=CollectionColumn.contained))
        self._collections.get_selection().set_mode(Gtk.SelectionMode.NONE)

        self._stack = builder.get_object("stack")
        self._stack.connect("notify::visible-child-name",
                            self.set_visible_child_name)
        self._switcher = builder.get_object("switcher")

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

    def set_visible_child_name(self, stack, param):
        if stack.get_visible_child_name() == STACK_NAME:
            self.refresh()
        self._set_clipboad_action_states()

    def refresh(self):
        self._refresh_comics()
        self._refresh_collections()
        self._comics.get_selection().unselect_all()

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
            0 if cover_idx is None else cover_idx,
            id,
        ) for (path, title, issue, cover_idx, id) in comics]
        self._refresh_model(self._comics.get_model(), comics)

    def _refresh_collections(self):
        collections = [(row[0], False, row[1]) for row in self._session.query(
            Collection.name, Collection.id).join(Lib).filter_by(
                path=str(self._library.path)).all()]
        self._refresh_model(self._collections.get_model(), collections)

    def _refresh_model(self, model, target):
        ms = list(model)
        for code, i1, i2, j1, j2 in diff_opcodes(ms, target):
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
                        model.set_row(model.iter_nth_child(None, i),
                                      target[j])
                    elif i >= len(model) and j < len(target):
                        model.insert(i, target[j])
                    elif j >= len(target) and i < len(model):
                        model.remove(model.iter_nth_child(None, i))

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
        self._session.add(comics)
        self._set_session_action_states()

    def _cover_edited(self, renderer, path, new_text):
        try:
            cover = int(new_text)
        except ValueError:
            return
        model = self._comics.get_model()
        comics = self._comics_by_id(model[path][ComicsColumn.id])
        if cover >= comics.pages:
            return
        model.set_value(model.get_iter(path), ComicsColumn.cover, cover)
        if comics.cover_idx == cover:
            return
        comics.cover_idx = cover
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
