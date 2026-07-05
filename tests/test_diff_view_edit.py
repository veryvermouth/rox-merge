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


def _cursor(view, line, col, side="right"):
    """커서를 놓고 선택을 해제(앵커=커서)한다 — 실제 내비게이션과 동일 상태."""
    view._active_side = side
    view._cur_line, view._cur_col = line, col
    view._collapse_selection()


def test_insert_text(view):
    left, right = _load(view, ["hello"], ["world"])
    _cursor(view, 0, 0)
    view._insert("X")
    view._insert("Y")
    assert right.lines == ["XYworld"]
    assert view._cur_col == 2


def test_commit_emits_once_for_typing_run(view):
    left, right = _load(view, ["a"], ["b"])
    _cursor(view, 0, 1)
    captured = []
    view.edit_committed.connect(lambda s, o, n: captured.append((s, list(o), list(n))))
    view._insert("c")
    view._insert("d")
    view.commit_edit()
    assert captured == [("right", ["b"], ["bcd"])]


def test_newline_splits_line(view):
    left, right = _load(view, ["x"], ["abcd"])
    _cursor(view, 0, 2)
    view._newline()
    assert right.lines == ["ab", "cd"]
    assert (view._cur_line, view._cur_col) == (1, 0)


def test_backspace_merges_lines(view):
    left, right = _load(view, ["x"], ["ab", "cd"])
    _cursor(view, 1, 0)
    view._backspace()
    assert right.lines == ["abcd"]
    assert (view._cur_line, view._cur_col) == (0, 2)


def test_delete_forward_at_line_end_merges(view):
    left, right = _load(view, ["x"], ["ab", "cd"])
    _cursor(view, 0, 2)
    view._delete()
    assert right.lines == ["abcd"]


def test_typing_into_empty_buffer(view):
    left, right = _load(view, ["x"], [])
    _cursor(view, 0, 0)
    view._insert("hi")
    assert right.lines == ["hi"]


def test_edit_then_undo_via_stack(view):
    left, right = _load(view, ["a"], ["b"])
    stack = UndoStack()
    _cursor(view, 0, 1)
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


# ------------------------------------------------------------------ selection


def test_select_all_and_copy_text(view):
    left, right = _load(view, ["one", "two", "three"], ["x"])
    view._active_side = "left"
    view._select_all()
    assert view._selected_text() == "one\ntwo\nthree"


def test_delete_selection_via_backspace(view):
    left, right = _load(view, ["x"], ["hello world"])
    view._active_side = "right"
    view._sel_line, view._sel_col = 0, 0
    view._cur_line, view._cur_col = 0, 6  # "hello " 선택
    view._backspace()
    assert right.lines == ["world"]


def test_typing_replaces_selection(view):
    left, right = _load(view, ["x"], ["hello"])
    view._active_side = "right"
    view._sel_line, view._sel_col = 0, 0
    view._cur_line, view._cur_col = 0, 5  # 전체 선택
    view._insert("bye")
    assert right.lines == ["bye"]


def test_multiline_paste(view):
    left, right = _load(view, ["x"], ["ab"])
    _cursor(view, 0, 1)
    view._insert_text("1\n2")  # 개행 포함 삽입
    assert right.lines == ["a1", "2b"]


def test_ime_commit_inserts_text(view):
    """한글 등 IME 입력: inputMethodEvent의 commitString이 삽입돼야 한다."""
    from PySide6.QtGui import QInputMethodEvent

    left, right = _load(view, ["x"], ["abc"])
    _cursor(view, 0, 3)
    # 조합 중(preedit)엔 문서 변화 없음
    view.inputMethodEvent(QInputMethodEvent("ㅎ", []))
    assert right.lines == ["abc"]
    assert view._preedit == "ㅎ"
    # 커밋되면 삽입
    ev = QInputMethodEvent("", [])
    ev.setCommitString("한글")
    view.inputMethodEvent(ev)
    assert right.lines == ["abc한글"]


def test_ime_ignored_when_read_only(view):
    from PySide6.QtGui import QInputMethodEvent

    left, right = _load(view, ["x"], ["abc"])
    view.set_read_only(True)
    _cursor(view, 0, 3)
    ev = QInputMethodEvent("", [])
    ev.setCommitString("한글")
    view.inputMethodEvent(ev)
    assert right.lines == ["abc"]
