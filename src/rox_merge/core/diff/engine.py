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
        else:  # replace: 라인 쌍을 짝지어 change/whitespace, 나머지는 insert/delete
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                rows.append(_change_row(i1 + k, j1 + k, left[i1 + k], right[j1 + k]))
            for i in range(i1 + paired, i2):
                rows.append(Row(i, None, KIND_DELETE))
            for j in range(j1 + paired, j2):
                rows.append(Row(None, j, KIND_INSERT))
    return rows


def _change_row(li: int, rj: int, lline: str, rline: str) -> Row:
    """짝지어진 두 라인을 change 또는 whitespace 로 분류하고 intraline 계산."""
    if lline != rline and normalize_whitespace(lline) == normalize_whitespace(rline):
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
