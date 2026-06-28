"""Myers diff 알고리즘 단위 테스트."""

import random

import pytest

from rox_merge.core.diff import myers


def _apply_opcodes(a, b, opcodes):
    """opcode대로 a에서 b를 재구성한다 (정확성 검증용)."""
    out = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            out.extend(a[i1:i2])
        elif tag == "delete":
            pass
        elif tag == "insert":
            out.extend(b[j1:j2])
        elif tag == "replace":
            out.extend(b[j1:j2])
    return out


def _lcs_len(a, b):
    """LCS 길이 (DP) — 최소 편집 거리 검증용."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    return dp[0][0]


def _edit_count(opcodes):
    count = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "delete":
            count += i2 - i1
        elif tag == "insert":
            count += j2 - j1
        elif tag == "replace":
            count += (i2 - i1) + (j2 - j1)
    return count


# ---------------------------------------------------------------------------
# 기본 케이스
# ---------------------------------------------------------------------------


def test_empty_both():
    assert myers.diff([], []) == []


def test_empty_left_all_insert():
    assert myers.diff([], ["a", "b"]) == [("insert", 0, 0, 0, 2)]


def test_empty_right_all_delete():
    assert myers.diff(["a", "b"], []) == [("delete", 0, 2, 0, 0)]


def test_identical_is_single_equal():
    a = ["a", "b", "c"]
    assert myers.diff(a, a) == [("equal", 0, 3, 0, 3)]


def test_pure_insert_middle():
    opcodes = myers.diff(["a", "c"], ["a", "b", "c"])
    assert opcodes == [
        ("equal", 0, 1, 0, 1),
        ("insert", 1, 1, 1, 2),
        ("equal", 1, 2, 2, 3),
    ]


def test_pure_delete_middle():
    opcodes = myers.diff(["a", "b", "c"], ["a", "c"])
    # difflib 규약: delete는 b를 소비하지 않아 j1==j2, 이후 equal의 j가 당겨진다.
    assert opcodes == [
        ("equal", 0, 1, 0, 1),
        ("delete", 1, 2, 1, 1),
        ("equal", 2, 3, 1, 2),
    ]


def test_replace():
    opcodes = myers.diff(["a", "x", "c"], ["a", "y", "c"])
    assert opcodes == [
        ("equal", 0, 1, 0, 1),
        ("replace", 1, 2, 1, 2),
        ("equal", 2, 3, 2, 3),
    ]


def test_all_different():
    opcodes = myers.diff(["a", "b"], ["x", "y"])
    assert opcodes == [("replace", 0, 2, 0, 2)]


# ---------------------------------------------------------------------------
# 난수 검증: 재구성 정확성 + 최소 편집 거리
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(50))
def test_random_reconstruct_and_minimal(seed):
    rng = random.Random(seed)
    alphabet = "abcd"  # 작은 알파벳으로 충돌(공통 부분수열) 유도
    a = [rng.choice(alphabet) for _ in range(rng.randint(0, 12))]
    b = [rng.choice(alphabet) for _ in range(rng.randint(0, 12))]

    opcodes = myers.diff(a, b)

    # 1) opcode로 b가 정확히 재구성돼야 한다.
    assert _apply_opcodes(a, b, opcodes) == b

    # 2) 편집 횟수가 이론적 최소(n+m-2*LCS)와 같아야 한다(replace=del+ins).
    assert _edit_count(opcodes) == len(a) + len(b) - 2 * _lcs_len(a, b)


@pytest.mark.parametrize("seed", range(20))
def test_opcodes_are_contiguous(seed):
    """opcode 범위가 빈틈/겹침 없이 연속이어야 한다."""
    rng = random.Random(seed + 100)
    a = [rng.randint(0, 3) for _ in range(rng.randint(0, 10))]
    b = [rng.randint(0, 3) for _ in range(rng.randint(0, 10))]

    opcodes = myers.diff(a, b)
    i = j = 0
    for tag, i1, i2, j1, j2 in opcodes:
        assert i1 == i and j1 == j
        i, j = i2, j2
    assert i == len(a) and j == len(b)
