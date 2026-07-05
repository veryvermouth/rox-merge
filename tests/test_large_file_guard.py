"""큰 파일 가드 테스트 (PLAN §7). 임계값을 낮춰 빠르게 검증."""

from rox_merge.app import compare_model as cm
from rox_merge.app.compare_model import build_result, guard_note
from rox_merge.core.diff import KIND_EQUAL
from rox_merge.core.document import Document
from tests.test_moves import MOVED_LEFT, MOVED_RIGHT


def _doc(lines):
    return Document(path="x", lines=list(lines))


def test_move_guard_disables_moves(monkeypatch):
    left, right = _doc(MOVED_LEFT), _doc(MOVED_RIGHT)
    # 임계값 아래: 이동 탐지됨
    monkeypatch.setattr(cm, "MOVE_GUARD_LINES", 10_000)
    assert build_result(left, right).moves != []
    # 임계값 위: 이동 탐지 자동 비활성
    monkeypatch.setattr(cm, "MOVE_GUARD_LINES", 3)
    result = build_result(left, right)
    assert result.moves == []
    # diff 자체는 여전히 동작(hunk 존재)
    assert result.hunks


def test_diff_guard_falls_back_to_plain(monkeypatch):
    monkeypatch.setattr(cm, "DIFF_GUARD_LINES", 2)
    result = build_result(_doc(["a", "b", "c"]), _doc(["x", "y", "z"]))
    assert result.hunks == []
    assert all(r.kind == KIND_EQUAL for r in result.rows)


def test_guard_note(monkeypatch):
    monkeypatch.setattr(cm, "MOVE_GUARD_LINES", 3)
    monkeypatch.setattr(cm, "DIFF_GUARD_LINES", 100)
    note = guard_note(_doc(["a"] * 3), _doc(["b"] * 3))  # total 6 > 3
    assert note and "이동" in note

    monkeypatch.setattr(cm, "DIFF_GUARD_LINES", 4)
    note2 = guard_note(_doc(["a"] * 3), _doc(["b"] * 3))  # total 6 > 4
    assert note2 and "diff" in note2


def test_no_note_for_small_files():
    assert guard_note(_doc(["a"]), _doc(["b"])) is None


def test_guard_skipped_when_one_side_empty(monkeypatch):
    monkeypatch.setattr(cm, "DIFF_GUARD_LINES", 1)
    # 한쪽이 비면 게이팅이 우선(플레인), 가드 note는 None
    assert guard_note(Document(lines=[]), _doc(["a", "b"])) is None
