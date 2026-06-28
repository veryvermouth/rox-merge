"""Moved block 탐지 테스트 (PLAN §4.3)."""

from rox_merge.core.diff import (
    KIND_DELETE,
    KIND_INSERT,
    KIND_MOVED,
    DiffOptions,
    MovePair,
    compute_diff,
)

# 3줄짜리 블록이 앞에서 뒤로 이동한 케이스.
# Myers는 더 긴 공통 부분(c1~c4)을 equal로 잡고, fA1~3을 삭제+추가로 본다.
MOVED_LEFT = ["fA1", "fA2", "fA3", "c1", "c2", "c3", "c4"]
MOVED_RIGHT = ["c1", "c2", "c3", "c4", "fA1", "fA2", "fA3"]


def _kinds(result):
    return [r.kind for r in result.rows]


def test_detects_moved_block():
    result = compute_diff(MOVED_LEFT, MOVED_RIGHT)
    assert result.moves == [MovePair((0, 3), (4, 7))]


def test_moved_rows_marked_moved():
    result = compute_diff(MOVED_LEFT, MOVED_RIGHT)
    # 이동 블록 행들은 delete/insert가 아니라 moved
    moved_rows = [r for r in result.rows if r.kind == KIND_MOVED]
    left_moved = sorted(r.left_index for r in moved_rows if r.left_index is not None)
    right_moved = sorted(r.right_index for r in moved_rows if r.right_index is not None)
    assert left_moved == [0, 1, 2]
    assert right_moved == [4, 5, 6]
    # 더 이상 순수 delete/insert로 남아있지 않다
    assert KIND_DELETE not in _kinds(result)
    assert KIND_INSERT not in _kinds(result)


def test_below_min_length_not_moved():
    # 2줄 이동은 기본 임계값(3) 미만이라 이동으로 보지 않는다
    left = ["fA1", "fA2", "c1", "c2", "c3"]
    right = ["c1", "c2", "c3", "fA1", "fA2"]
    result = compute_diff(left, right)
    assert result.moves == []
    assert KIND_MOVED not in _kinds(result)
    assert KIND_DELETE in _kinds(result)
    assert KIND_INSERT in _kinds(result)


def test_custom_min_move_lines():
    left = ["fA1", "fA2", "c1", "c2", "c3"]
    right = ["c1", "c2", "c3", "fA1", "fA2"]
    result = compute_diff(left, right, DiffOptions(min_move_lines=2))
    assert result.moves == [MovePair((0, 2), (3, 5))]


def test_detect_moves_disabled():
    result = compute_diff(MOVED_LEFT, MOVED_RIGHT, DiffOptions(detect_moves=False))
    assert result.moves == []
    assert KIND_MOVED not in _kinds(result)
    assert KIND_DELETE in _kinds(result)
    assert KIND_INSERT in _kinds(result)


def test_no_false_move_on_plain_change():
    # 단순 변경엔 이동이 없어야 한다
    result = compute_diff(["a", "b", "c"], ["a", "X", "c"])
    assert result.moves == []
