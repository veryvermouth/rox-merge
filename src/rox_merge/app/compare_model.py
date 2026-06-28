"""파일 비교 세션의 순수 로직 — diff 게이팅과 차이 점프 (PLAN §4.6, §6.2).

UI/Qt 무의존이라 단위 테스트 가능.
"""

from __future__ import annotations

from rox_merge.core.diff import (
    KIND_EQUAL,
    DiffOptions,
    DiffResult,
    Row,
    compute_diff,
)
from rox_merge.core.document import Document


def build_result(
    left: Document,
    right: Document,
    options: DiffOptions = DiffOptions(),
) -> DiffResult:
    """두 문서로 diff 결과를 만든다. PLAN §4.6 게이팅 적용.

    한쪽이라도 비어 있으면 diff를 돌리지 않고, 양쪽을 인덱스 순서로 나란히
    놓은 플레인 정렬(모두 equal, 색상/하이라이트 없음)을 반환한다.
    """
    if left.is_empty or right.is_empty:
        return _plain_result(left.lines, right.lines)
    return compute_diff(left.lines, right.lines, options)


def _plain_result(left: list[str], right: list[str]) -> DiffResult:
    rows: list[Row] = []
    n = max(len(left), len(right))
    for i in range(n):
        li = i if i < len(left) else None
        rj = i if i < len(right) else None
        rows.append(Row(li, rj, KIND_EQUAL))
    return DiffResult(rows=rows, hunks=[], moves=[])


def step_hunk(current_idx: int, delta: int, hunk_count: int) -> int:
    """차이 점프 인덱스 계산 (PLAN §6.2 clamp).

    양 끝에서는 순환하지 않고 제자리(clamp). hunk가 없으면 -1.
    ``current_idx == -1`` (아직 선택 안 됨)에서 다음=0, 이전=0.
    """
    if hunk_count == 0:
        return -1
    if current_idx < 0:
        return 0
    return max(0, min(hunk_count - 1, current_idx + delta))
