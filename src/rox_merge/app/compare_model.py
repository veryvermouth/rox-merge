"""파일 비교 세션의 순수 로직 — diff 게이팅과 차이 점프 (PLAN §4.6, §6.2).

UI/Qt 무의존이라 단위 테스트 가능.
"""

from __future__ import annotations

from dataclasses import replace

from rox_merge.core.diff import (
    KIND_EQUAL,
    DiffOptions,
    DiffResult,
    Row,
    compute_diff,
)
from rox_merge.core.document import Document

# 큰 파일 가드 (PLAN §7): 좌+우 총 라인 수 기준.
MOVE_GUARD_LINES = 20_000     # 초과 시 이동 탐지 자동 비활성(비용 큼)
DIFF_GUARD_LINES = 200_000    # 초과 시 diff 생략(메모리/시간 폭증 방지) → 플레인


def build_result(
    left: Document,
    right: Document,
    options: DiffOptions = DiffOptions(),
) -> DiffResult:
    """두 문서로 diff 결과를 만든다. PLAN §4.6 게이팅 + §7 큰 파일 가드 적용.

    - 한쪽이라도 비어 있으면 diff 없이 플레인 정렬(모두 equal).
    - 총 라인 수가 아주 크면 diff를 생략(플레인)하거나 이동 탐지를 끈다.
    """
    if left.is_empty or right.is_empty:
        return _plain_result(left.lines, right.lines)

    total = len(left.lines) + len(right.lines)
    if total > DIFF_GUARD_LINES:
        return _plain_result(left.lines, right.lines)
    if total > MOVE_GUARD_LINES and options.detect_moves:
        options = replace(options, detect_moves=False)
    return compute_diff(left.lines, right.lines, options)


def guard_note(left: Document, right: Document) -> str | None:
    """큰 파일 가드가 적용됐다면 사용자 안내 문구를, 아니면 None을 반환."""
    if left.is_empty or right.is_empty:
        return None
    total = len(left.lines) + len(right.lines)
    if total > DIFF_GUARD_LINES:
        return "파일이 매우 커서 diff를 생략하고 원본만 표시합니다."
    if total > MOVE_GUARD_LINES:
        return "큰 파일이라 이동(moved) 탐지를 자동 비활성화했습니다."
    return None


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
