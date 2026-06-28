"""Diff 엔진(정렬/intraline/whitespace/hunk) 단위 테스트 — 골든셋."""

from rox_merge.core.diff import (
    KIND_CHANGE,
    KIND_DELETE,
    KIND_EQUAL,
    KIND_INSERT,
    KIND_WHITESPACE,
    DiffOptions,
    compute_diff,
)
from rox_merge.core.diff.engine import normalize_whitespace


def _kinds(result):
    return [r.kind for r in result.rows]


def _pairs(result):
    return [(r.left_index, r.right_index, r.kind) for r in result.rows]


# ---------------------------------------------------------------------------
# 정렬(Alignment) 기본
# ---------------------------------------------------------------------------


def test_identical_all_equal():
    result = compute_diff(["a", "b"], ["a", "b"])
    assert _pairs(result) == [(0, 0, KIND_EQUAL), (1, 1, KIND_EQUAL)]
    assert result.hunks == []


def test_both_empty():
    result = compute_diff([], [])
    assert result.rows == []
    assert result.hunks == []


def test_insert_creates_gap_on_left():
    # 왼쪽엔 없고 오른쪽에만 있는 라인 → insert, 왼쪽은 gap(None)
    result = compute_diff(["a", "c"], ["a", "b", "c"])
    assert _pairs(result) == [
        (0, 0, KIND_EQUAL),
        (None, 1, KIND_INSERT),
        (1, 2, KIND_EQUAL),
    ]


def test_delete_creates_gap_on_right():
    result = compute_diff(["a", "b", "c"], ["a", "c"])
    # 오른쪽 "c"는 인덱스 1이므로 마지막 equal은 (2, 1)
    assert _pairs(result) == [
        (0, 0, KIND_EQUAL),
        (1, None, KIND_DELETE),
        (2, 1, KIND_EQUAL),
    ]


def test_change_pairs_lines():
    result = compute_diff(["a", "xxx", "c"], ["a", "yyy", "c"])
    assert _pairs(result) == [
        (0, 0, KIND_EQUAL),
        (1, 1, KIND_CHANGE),
        (2, 2, KIND_EQUAL),
    ]


def test_replace_uneven_pairs_then_gaps():
    # 왼쪽 2줄 vs 오른쪽 3줄이 바뀜 → 2줄 change 짝 + 1줄 insert
    result = compute_diff(["x1", "x2"], ["y1", "y2", "y3"])
    kinds = _kinds(result)
    assert kinds == [KIND_CHANGE, KIND_CHANGE, KIND_INSERT]
    assert result.rows[-1].left_index is None
    assert result.rows[-1].right_index == 2


# ---------------------------------------------------------------------------
# whitespace 분류 (PLAN §4.4)
# ---------------------------------------------------------------------------


def test_whitespace_only_difference():
    # 모든 라인 앞에 탭 추가 → change 아닌 whitespace
    left = ["def f():", "    return 1"]
    right = ["\tdef f():", "\t    return 1"]
    result = compute_diff(left, right)
    assert _kinds(result) == [KIND_WHITESPACE, KIND_WHITESPACE]


def test_whitespace_vs_real_change():
    # 들여쓰기만 바뀐 줄 = whitespace, 내용 바뀐 줄 = change
    left = ["a = 1", "b = 2"]
    right = ["  a = 1", "b = 3"]
    result = compute_diff(left, right)
    assert _kinds(result) == [KIND_WHITESPACE, KIND_CHANGE]


def test_ignore_whitespace_option_promotes_to_equal():
    left = ["    return 1"]
    right = ["\treturn 1"]
    result = compute_diff(left, right, DiffOptions(ignore_whitespace=True))
    assert _kinds(result) == [KIND_EQUAL]


def test_ignore_case_option():
    result = compute_diff(["Hello"], ["hello"], DiffOptions(ignore_case=True))
    assert _kinds(result) == [KIND_EQUAL]


def test_normalize_whitespace_helper():
    assert normalize_whitespace("  a   b  ") == "a b"
    assert normalize_whitespace("\t\ta\tb") == "a b"


# ---------------------------------------------------------------------------
# intraline 단어 단위 하이라이트 (PLAN §4.2)
# ---------------------------------------------------------------------------


def test_intraline_marks_changed_word_only():
    # "foo bar baz" vs "foo qux baz" → 가운데 단어만 강조
    result = compute_diff(["foo bar baz"], ["foo qux baz"])
    row = result.rows[0]
    assert row.kind == KIND_CHANGE
    assert len(row.left_spans) == 1
    assert len(row.right_spans) == 1
    left = result and "foo bar baz"
    # 'bar' 위치 [4,7), 'qux' 위치 [4,7)
    assert (row.left_spans[0].start, row.left_spans[0].end) == (4, 7)
    assert (row.right_spans[0].start, row.right_spans[0].end) == (4, 7)


def test_intraline_suffix_change():
    result = compute_diff(["value = 10"], ["value = 20"])
    row = result.rows[0]
    # 마지막 숫자만 다름
    seg_left = "value = 10"[row.left_spans[0].start:row.left_spans[0].end]
    seg_right = "value = 20"[row.right_spans[0].start:row.right_spans[0].end]
    assert "1" in seg_left
    assert "2" in seg_right


# ---------------------------------------------------------------------------
# hunk 그룹화
# ---------------------------------------------------------------------------


def test_hunks_group_consecutive_changes():
    left = ["same", "a", "b", "same2"]
    right = ["same", "x", "y", "same2"]
    result = compute_diff(left, right)
    assert len(result.hunks) == 1
    h = result.hunks[0]
    assert h.kind == KIND_CHANGE
    assert h.row_start == 1
    assert h.row_end == 3
    assert h.left_range == (1, 3)
    assert h.right_range == (1, 3)


def test_multiple_hunks():
    left = ["a", "KEEP", "b", "KEEP2", "c"]
    right = ["x", "KEEP", "y", "KEEP2", "z"]
    result = compute_diff(left, right)
    assert len(result.hunks) == 3
    for h in result.hunks:
        assert h.kind == KIND_CHANGE


def test_replace_aligns_by_similarity_not_position():
    # 크기가 다른 replace 블록: 비슷한 라인(x=1↔x=10)이 짝지어지고
    # 나머지(def_unused/pass/blank)는 delete로 떨어져야 자연스럽다.
    left = ["def unused_helper():", "    pass", "", "", "x = 1", "y = 2"]
    right = ["x = 10", "y = 2"]
    result = compute_diff(left, right)
    pairs = [(r.left_index, r.right_index, r.kind) for r in result.rows]
    assert pairs == [
        (0, None, KIND_DELETE),
        (1, None, KIND_DELETE),
        (2, None, KIND_DELETE),
        (3, None, KIND_DELETE),
        (4, 0, KIND_CHANGE),   # x = 1  ↔  x = 10
        (5, 1, KIND_EQUAL),    # y = 2
    ]


def test_equal_size_replace_still_pairs_positionally():
    # 같은 크기 블록은 유사도가 낮아도 위치대로 change(빈 행 없이 정렬).
    result = compute_diff(["a", "b"], ["x", "y"])
    assert [r.kind for r in result.rows] == [KIND_CHANGE, KIND_CHANGE]


def test_insert_only_hunk_kind():
    result = compute_diff(["a", "b"], ["a", "NEW", "b"])
    assert len(result.hunks) == 1
    assert result.hunks[0].kind == KIND_INSERT
    assert result.hunks[0].left_range is None
    assert result.hunks[0].right_range == (1, 2)
