"""Diff 엔진 오케스트레이션 (PLAN §4).

라인 단위 Myers diff → side-by-side 정렬(Row) → replace 쌍의 단어 단위 2차 diff
(intraline) → 공백만 다른 라인 분류(whitespace) → hunk 그룹화.

moved 블록 탐지(PLAN §4.3)는 Phase 4에서 추가한다.
"""

from __future__ import annotations

import re

from rox_merge.core.diff import myers
from rox_merge.core.diff.models import (
    KIND_CHANGE,
    KIND_DELETE,
    KIND_EQUAL,
    KIND_INSERT,
    KIND_WHITESPACE,
    DiffOptions,
    DiffResult,
    Hunk,
    Row,
    Span,
)
from rox_merge.core.diff.tokenize import tokenize

_WS_RUN = re.compile(r"\s+")


def normalize_whitespace(s: str) -> str:
    """선행/후행 공백 제거 + 연속 공백 축약 (PLAN §4.4 공백 정규화)."""
    return _WS_RUN.sub(" ", s.strip())


def compute_diff(
    left: list[str],
    right: list[str],
    options: DiffOptions = DiffOptions(),
) -> DiffResult:
    """좌/우 라인 목록을 비교해 :class:`DiffResult` 를 만든다.

    PLAN §4.6의 '양쪽 텍스트 존재' 게이팅은 호출자(앱 계층)의 책임이며,
    엔진은 주어진 입력을 그대로 비교한다.
    """
    left_keys = [_line_key(s, options) for s in left]
    right_keys = [_line_key(s, options) for s in right]

    opcodes = myers.diff(left_keys, right_keys)
    rows = _build_rows(opcodes, left, right)
    hunks = _build_hunks(rows)
    return DiffResult(rows=rows, hunks=hunks, moves=[])


def _line_key(line: str, options: DiffOptions) -> str:
    """Myers 동등 비교에 쓸 정규화 키 (비교 옵션 반영)."""
    key = line
    if options.ignore_whitespace:
        key = normalize_whitespace(key)
    if options.ignore_case:
        key = key.lower()
    return key


def _build_rows(opcodes: list[myers.Opcode], left: list[str], right: list[str]) -> list[Row]:
    rows: list[Row] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append(Row(i1 + k, j1 + k, KIND_EQUAL))
        elif tag == "delete":
            for i in range(i1, i2):
                rows.append(Row(i, None, KIND_DELETE))
        elif tag == "insert":
            for j in range(j1, j2):
                rows.append(Row(None, j, KIND_INSERT))
        else:  # replace: 유사도 기반으로 라인을 짝짓는다(위치 순서 짝짓기 대신)
            for li, rj in _align_replace(left, right, i1, i2, j1, j2):
                if li is not None and rj is not None:
                    rows.append(_change_row(li, rj, left[li], right[rj]))
                elif li is not None:
                    rows.append(Row(li, None, KIND_DELETE))
                else:
                    rows.append(Row(None, rj, KIND_INSERT))
    return rows


# replace 블록 정렬 파라미터
# 매칭 점수 = 유사도 - 임계값. 0이면 '동점 시 짝짓기 선호'가 되어,
# 같은 크기 블록은 위치대로 change, 크기가 다른 블록은 가장 비슷한 라인끼리 짝지어진다.
_SIM_THRESHOLD = 0.0
_ALIGN_CELL_CAP = 4000        # 블록이 너무 크면(성능) 위치 순서 짝짓기로 폴백


def _similarity(a: str, b: str) -> float:
    """두 라인의 문자 단위 유사도 [0,1] (LCS 기반)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    ops = myers.diff(list(a), list(b))
    lcs = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in ops if tag == "equal")
    return 2 * lcs / (len(a) + len(b))


def _align_replace(
    left: list[str], right: list[str], i1: int, i2: int, j1: int, j2: int
) -> list[tuple[int | None, int | None]]:
    """replace 블록의 좌/우 라인을 유사도 최대화로 정렬한다(Needleman–Wunsch).

    비슷한 라인은 change 쌍으로 묶고, 그렇지 않은 라인은 delete/insert로 남긴다.
    """
    n, m = i2 - i1, j2 - j1
    if n == 0 or m == 0 or n * m > _ALIGN_CELL_CAP:
        return _positional_pairs(i1, i2, j1, j2)

    sims = [[_similarity(left[i1 + i], right[j1 + j]) for j in range(m)] for i in range(n)]

    # score[i][j]: 좌측 i개·우측 j개를 정렬했을 때 최대 점수. gap 점수=0,
    # 매칭 점수=유사도-임계값(임계값 미만이면 음수라 짝짓지 않는 게 유리).
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match = score[i - 1][j - 1] + (sims[i - 1][j - 1] - _SIM_THRESHOLD)
            score[i][j] = max(match, score[i - 1][j], score[i][j - 1])

    pairs: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and score[i][j] == score[i - 1][j - 1] + (sims[i - 1][j - 1] - _SIM_THRESHOLD)
        ):
            pairs.append((i1 + i - 1, j1 + j - 1))
            i -= 1
            j -= 1
        elif i > 0 and score[i][j] == score[i - 1][j]:
            pairs.append((i1 + i - 1, None))
            i -= 1
        else:
            pairs.append((None, j1 + j - 1))
            j -= 1
    pairs.reverse()
    return pairs


def _positional_pairs(
    i1: int, i2: int, j1: int, j2: int
) -> list[tuple[int | None, int | None]]:
    paired = min(i2 - i1, j2 - j1)
    pairs: list[tuple[int | None, int | None]] = [(i1 + k, j1 + k) for k in range(paired)]
    pairs += [(i, None) for i in range(i1 + paired, i2)]
    pairs += [(None, j) for j in range(j1 + paired, j2)]
    return pairs


def _change_row(li: int, rj: int, lline: str, rline: str) -> Row:
    """짝지어진 두 라인을 equal/whitespace/change 로 분류하고 intraline 계산."""
    if lline == rline:
        # 정렬 과정에서 동일 라인이 짝지어질 수 있음 → equal
        return Row(li, rj, KIND_EQUAL)
    if normalize_whitespace(lline) == normalize_whitespace(rline):
        # 내용은 같고 공백/들여쓰기만 다름 (PLAN §4.4)
        return Row(li, rj, KIND_WHITESPACE)

    left_spans, right_spans = _intraline_spans(lline, rline)
    return Row(li, rj, KIND_CHANGE, left_spans=left_spans, right_spans=right_spans)


def _intraline_spans(lline: str, rline: str) -> tuple[list[Span], list[Span]]:
    """두 라인의 단어 단위 diff로 좌/우 변경 구간(span)을 만든다 (PLAN §4.2)."""
    ltok = tokenize(lline)
    rtok = tokenize(rline)
    ops = myers.diff([t.text for t in ltok], [t.text for t in rtok])

    left_spans: list[Span] = []
    right_spans: list[Span] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("delete", "replace") and i2 > i1:
            left_spans.append(Span(ltok[i1].start, ltok[i2 - 1].end))
        if tag in ("insert", "replace") and j2 > j1:
            right_spans.append(Span(rtok[j1].start, rtok[j2 - 1].end))
    return _merge_spans(left_spans), _merge_spans(right_spans)


def _merge_spans(spans: list[Span]) -> list[Span]:
    """겹치거나 맞닿은 span을 합친다."""
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: s.start)
    merged = [spans[0]]
    for s in spans[1:]:
        last = merged[-1]
        if s.start <= last.end:
            merged[-1] = Span(last.start, max(last.end, s.end))
        else:
            merged.append(s)
    return merged


def _build_hunks(rows: list[Row]) -> list[Hunk]:
    """연속된 비-equal 행을 hunk로 묶는다."""
    hunks: list[Hunk] = []
    hid = 0
    i = 0
    n = len(rows)
    while i < n:
        if rows[i].kind == KIND_EQUAL:
            i += 1
            continue
        start = i
        while i < n and rows[i].kind != KIND_EQUAL:
            i += 1
        block = rows[start:i]

        left_idxs = [r.left_index for r in block if r.left_index is not None]
        right_idxs = [r.right_index for r in block if r.right_index is not None]
        left_range = (left_idxs[0], left_idxs[-1] + 1) if left_idxs else None
        right_range = (right_idxs[0], right_idxs[-1] + 1) if right_idxs else None

        if not left_idxs:
            kind = KIND_INSERT
        elif not right_idxs:
            kind = KIND_DELETE
        else:
            kind = KIND_CHANGE

        hunks.append(
            Hunk(
                id=hid,
                kind=kind,
                row_start=start,
                row_end=i,
                left_range=left_range,
                right_range=right_range,
            )
        )
        hid += 1
    return hunks
