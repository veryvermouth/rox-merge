"""병합/Undo 커맨드 단위 테스트."""

from rox_merge.app.commands import ReplaceLinesCommand, UndoStack, make_apply_hunk
from rox_merge.core.diff import compute_diff
from rox_merge.core.document import Document


def _doc(lines):
    return Document(path="x", lines=list(lines))


def _apply_hunk(left, right, direction):
    """첫 hunk를 한 방향 적용하고 (left.lines, right.lines) 반환."""
    result = compute_diff(left.lines, right.lines)
    cmd = make_apply_hunk(left, right, result.hunks[0], direction)
    cmd.apply()
    return cmd


# --------------------------------------------------------- ReplaceLinesCommand


def test_replace_lines_apply_undo():
    doc = _doc(["a", "b", "c"])
    cmd = ReplaceLinesCommand(doc, start=1, old_len=1, new_lines=["X", "Y"])
    cmd.apply()
    assert doc.lines == ["a", "X", "Y", "c"]
    assert doc.dirty is True
    cmd.undo()
    assert doc.lines == ["a", "b", "c"]


def test_replace_lines_redo_after_undo():
    doc = _doc(["a", "b"])
    cmd = ReplaceLinesCommand(doc, start=0, old_len=1, new_lines=["Z"])
    cmd.apply()
    cmd.undo()
    cmd.apply()  # redo
    assert doc.lines == ["Z", "b"]


# ------------------------------------------------------------ make_apply_hunk


def test_merge_change_l2r():
    left, right = _doc(["a", "b", "c"]), _doc(["a", "X", "c"])
    _apply_hunk(left, right, "l2r")
    assert right.lines == ["a", "b", "c"]   # 왼쪽 내용으로 교체
    assert left.lines == ["a", "b", "c"]    # 원본 유지


def test_merge_change_r2l():
    left, right = _doc(["a", "b", "c"]), _doc(["a", "X", "c"])
    _apply_hunk(left, right, "r2l")
    assert left.lines == ["a", "X", "c"]


def test_merge_insert_l2r_removes():
    # 오른쪽에만 있는 줄 → 왼쪽(없음)을 적용 = 오른쪽에서 제거
    left, right = _doc(["a", "c"]), _doc(["a", "b", "c"])
    _apply_hunk(left, right, "l2r")
    assert right.lines == ["a", "c"]


def test_merge_insert_r2l_adds():
    left, right = _doc(["a", "c"]), _doc(["a", "b", "c"])
    _apply_hunk(left, right, "r2l")
    assert left.lines == ["a", "b", "c"]


def test_merge_delete_l2r_adds_to_right():
    left, right = _doc(["a", "b", "c"]), _doc(["a", "c"])
    _apply_hunk(left, right, "l2r")
    assert right.lines == ["a", "b", "c"]


def test_merge_delete_r2l_removes_from_left():
    left, right = _doc(["a", "b", "c"]), _doc(["a", "c"])
    _apply_hunk(left, right, "r2l")
    assert left.lines == ["a", "c"]


def test_merge_then_no_diff():
    # 병합 후 다시 비교하면 그 차이는 사라져야 한다.
    left, right = _doc(["a", "b", "c"]), _doc(["a", "X", "c"])
    _apply_hunk(left, right, "l2r")
    assert compute_diff(left.lines, right.lines).hunks == []


# ------------------------------------------------------------------ UndoStack


def test_undo_stack_merge_undo_redo():
    left, right = _doc(["a", "b", "c"]), _doc(["a", "X", "c"])
    stack = UndoStack()
    result = compute_diff(left.lines, right.lines)
    stack.push(make_apply_hunk(left, right, result.hunks[0], "l2r"))
    assert right.lines == ["a", "b", "c"]
    assert stack.can_undo() and not stack.can_redo()

    stack.undo()
    assert right.lines == ["a", "X", "c"]
    assert stack.can_redo()

    stack.redo()
    assert right.lines == ["a", "b", "c"]


def test_undo_stack_push_clears_redo():
    doc = _doc(["a"])
    stack = UndoStack()
    stack.push(ReplaceLinesCommand(doc, 0, 1, ["b"]))
    stack.undo()
    assert stack.can_redo()
    stack.push(ReplaceLinesCommand(doc, 0, 1, ["c"]))
    assert not stack.can_redo()  # 새 명령이 redo 이력을 비움


def test_undo_empty_is_noop():
    stack = UndoStack()
    stack.undo()  # 예외 없이 무시
    stack.redo()
    assert not stack.can_undo()
