"""파일 비교 세션 순수 로직 테스트 (게이팅 / 점프 clamp)."""

from rox_merge.app.compare_model import build_result, step_hunk
from rox_merge.core.diff import KIND_CHANGE, KIND_EQUAL
from rox_merge.core.document import Document


def _doc(lines):
    return Document(path="x", lines=list(lines))


# ----------------------------------------------------------- 게이팅 (PLAN §4.6)


def test_both_filled_runs_diff():
    result = build_result(_doc(["a"]), _doc(["b"]))
    assert result.rows[0].kind == KIND_CHANGE
    assert len(result.hunks) == 1


def test_left_empty_is_plain():
    # 한쪽이 비면 diff 없이 플레인(모두 equal, hunk 없음)
    result = build_result(Document(lines=[]), _doc(["a", "b"]))
    assert [r.kind for r in result.rows] == [KIND_EQUAL, KIND_EQUAL]
    assert result.hunks == []
    assert result.rows[0].left_index is None
    assert result.rows[0].right_index == 0


def test_right_empty_is_plain():
    result = build_result(_doc(["a", "b"]), Document(lines=[]))
    assert result.hunks == []
    assert all(r.kind == KIND_EQUAL for r in result.rows)
    assert result.rows[1].left_index == 1
    assert result.rows[1].right_index is None


def test_both_empty_no_rows():
    result = build_result(Document(lines=[]), Document(lines=[]))
    assert result.rows == []


# ----------------------------------------------------------- 점프 clamp (§6.2)


def test_step_hunk_no_hunks():
    assert step_hunk(-1, +1, 0) == -1


def test_step_hunk_first_jump():
    assert step_hunk(-1, +1, 3) == 0
    assert step_hunk(-1, -1, 3) == 0


def test_step_hunk_next_prev():
    assert step_hunk(0, +1, 3) == 1
    assert step_hunk(1, +1, 3) == 2
    assert step_hunk(2, -1, 3) == 1


def test_step_hunk_clamps_at_ends():
    # 마지막에서 다음 → 제자리, 처음에서 이전 → 제자리 (순환 안 함)
    assert step_hunk(2, +1, 3) == 2
    assert step_hunk(0, -1, 3) == 0
