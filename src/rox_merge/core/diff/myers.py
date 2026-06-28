"""Myers O(ND) diff 알고리즘 (PLAN §4.1).

두 시퀀스 ``a``, ``b`` 의 최소 편집 스크립트를 difflib 호환 opcode로 반환한다:
``(tag, i1, i2, j1, j2)``, ``tag ∈ {equal, delete, insert, replace}``.
의미: ``a[i1:i2]`` 와 ``b[j1:j2]`` 를 ``tag`` 관계로 묶는다.

라인 diff(시퀀스=라인)와 단어 diff(시퀀스=토큰) 모두에 재사용된다.
"""

from __future__ import annotations

from typing import Sequence

Opcode = tuple[str, int, int, int, int]


def diff(a: Sequence, b: Sequence) -> list[Opcode]:
    """``a`` → ``b`` 변환의 최소 편집 스크립트를 opcode 목록으로 반환."""
    ops = _edit_ops(a, b)
    return _ops_to_opcodes(ops)


def _edit_ops(a: Sequence, b: Sequence) -> list[str]:
    """Myers O(ND)로 단위 편집열을 구한다: 'equal' / 'delete' / 'insert' 의 순열."""
    n, m = len(a), len(b)
    if n == 0 and m == 0:
        return []

    maxd = n + m
    off = maxd
    v = [0] * (2 * maxd + 1)
    trace: list[list[int]] = []

    for d in range(maxd + 1):
        trace.append(v[:])
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[off + k - 1] < v[off + k + 1]):
                x = v[off + k + 1]          # 아래로 이동 = insert
            else:
                x = v[off + k - 1] + 1      # 오른쪽 이동 = delete
            y = x - k
            while x < n and y < m and a[x] == b[y]:  # 대각선 = equal(snake)
                x += 1
                y += 1
            v[off + k] = x
            if x >= n and y >= m:
                return _backtrack(trace, n, m, off, d)

    # 도달 불가(안전망).
    return _backtrack(trace, n, m, off, maxd)


def _backtrack(trace: list[list[int]], n: int, m: int, off: int, d_final: int) -> list[str]:
    """트레이스를 역추적해 순방향 단위 편집열을 만든다."""
    ops: list[str] = []
    x, y = n, m

    for d in range(d_final, 0, -1):
        v = trace[d]
        k = x - y
        if k == -d or (k != d and v[off + k - 1] < v[off + k + 1]):
            prev_k = k + 1
        else:
            prev_k = k - 1
        prev_x = v[off + prev_k]
        prev_y = prev_x - prev_k

        while x > prev_x and y > prev_y:  # 대각선(equal) 되감기
            ops.append("equal")
            x -= 1
            y -= 1

        if x == prev_x:
            ops.append("insert")
        else:
            ops.append("delete")
        x, y = prev_x, prev_y

    while x > 0 and y > 0:  # d=0: 원점까지 남은 대각선
        ops.append("equal")
        x -= 1
        y -= 1

    ops.reverse()
    return ops


def _ops_to_opcodes(ops: list[str]) -> list[Opcode]:
    """단위 편집열을 difflib 호환 opcode로 묶는다.

    연속된 비-equal(삭제/추가) 구간은 하나로 합쳐 delete/insert/replace 로 분류.
    """
    opcodes: list[Opcode] = []
    i = j = 0
    idx = 0
    length = len(ops)

    while idx < length:
        if ops[idx] == "equal":
            i1, j1 = i, j
            while idx < length and ops[idx] == "equal":
                i += 1
                j += 1
                idx += 1
            opcodes.append(("equal", i1, i, j1, j))
        else:
            i1, j1 = i, j
            while idx < length and ops[idx] != "equal":
                if ops[idx] == "delete":
                    i += 1
                else:
                    j += 1
                idx += 1
            has_del = i > i1
            has_ins = j > j1
            if has_del and has_ins:
                tag = "replace"
            elif has_del:
                tag = "delete"
            else:
                tag = "insert"
            opcodes.append((tag, i1, i, j1, j))

    return opcodes
