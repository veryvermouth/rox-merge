"""DiffView 직접 편집 로직 헤드리스 테스트 (offscreen Qt)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from rox_merge.app.commands import SetLinesCommand, UndoStack  # noqa: E402
from rox_merge.core.diff import compute_diff  # noqa: E402
from rox_merge.core.document import Document  # noqa: E402
from rox_merge.ui.diff_view import DiffView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application


@pytest.fixture
def view(app):
    v = DiffView()
    v.resize(800, 400)
    return v


def _load(view, left_lines, right_lines):
    left = Document(path="L", lines=list(left_lines))
    right = Document(path="R", lines=list(right_lines))
    result = compute_diff(left.lines, right.lines)
    view.set_data(left, right, result)
    return left, right


def test_insert_text(view):
    left, right = _load(view, ["hello"], ["world"])
    view._active_side = "right"
    view._cur_line, view._cur_col = 0, 0
    view._insert("X")
    view._insert("Y")
    assert right.lines == ["XYworld"]
    assert view._cur_col == 2


def test_commit_emits_once_for_typing_run(view):
    left, right = _load(view, ["a"], ["b"])
    view._active_side = "right"
    view._cur_line, view._cur_col = 0, 1
    captured = []
    view.edit_committed.connect(lambda s, o, n: captured.append((s, list(o), list(n))))
    view._insert("c")
    view._insert("d")
    view.commit_edit()
    assert captured == [("right", ["b"], ["bcd"])]


def test_newline_splits_line(view):
    left, right = _load(view, ["x"], ["abcd"])
    view._active_side = "right"
    view._cur_line, view._cur_col = 0, 2
    view._newline()
    assert right.lines == ["ab", "cd"]
    assert (view._cur_line, view._cur_col) == (1, 0)


def test_backspace_merges_lines(view):
    left, right = _load(view, ["x"], ["ab", "cd"])
    view._active_side = "right"
    view._cur_line, view._cur_col = 1, 0
    view._backspace()
    assert right.lines == ["abcd"]
    assert (view._cur_line, view._cur_col) == (0, 2)


def test_delete_forward_at_line_end_merges(view):
    left, right = _load(view, ["x"], ["ab", "cd"])
    view._active_side = "right"
    view._cur_line, view._cur_col = 0, 2
    view._delete()
    assert right.lines == ["abcd"]


def test_typing_into_empty_buffer(view):
    left, right = _load(view, ["x"], [])
    view._active_side = "right"
    view._cur_line, view._cur_col = 0, 0
    view._insert("hi")
    assert right.lines == ["hi"]


def test_edit_then_undo_via_stack(view):
    left, right = _load(view, ["a"], ["b"])
    stack = UndoStack()
    view._active_side = "right"
    view._cur_line, view._cur_col = 0, 1
    view.edit_committed.connect(
        lambda s, o, n: stack.record(SetLinesCommand(right, o, n))
    )
    view._insert("X")
    view.commit_edit()
    assert right.lines == ["bX"]
    stack.undo()
    assert right.lines == ["b"]
    stack.redo()
    assert right.lines == ["bX"]
