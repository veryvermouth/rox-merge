"""Diff 결과 데이터 모델 (PLAN §5, §4.5).

순수 데이터. UI/Qt 무의존.

PLAN과의 차이: PLAN의 ``Row.intraline: list[Span]`` 을, side-by-side 렌더에서
좌/우 라인 각각에 하이라이트를 입혀야 하므로 ``left_spans`` / ``right_spans`` 둘로
분리했다(의미는 동일, 표현만 명확화).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Row/Hunk 종류 (PLAN §4.5, §6.3). 'moved' 는 Phase 4에서 채운다.
KIND_EQUAL = "equal"
KIND_CHANGE = "change"
KIND_WHITESPACE = "whitespace"
KIND_INSERT = "insert"
KIND_DELETE = "delete"
KIND_MOVED = "moved"

VALID_KINDS = frozenset(
    {KIND_EQUAL, KIND_CHANGE, KIND_WHITESPACE, KIND_INSERT, KIND_DELETE, KIND_MOVED}
)


@dataclass(frozen=True)
class Span:
    """라인 내 문자 구간 [start, end) — 단어 단위 하이라이트용 (PLAN §4.2)."""

    start: int
    end: int


@dataclass
class Row:
    """side-by-side 정렬의 한 행 (PLAN §4.5).

    한쪽 인덱스가 ``None`` 이면 그쪽은 gap(빈 줄)이다.
    """

    left_index: int | None
    right_index: int | None
    kind: str
    left_spans: list[Span] = field(default_factory=list)
    right_spans: list[Span] = field(default_factory=list)


@dataclass
class Hunk:
    """연속된 비-equal 행 묶음 — 점프(Phase 2)/병합(Phase 3) 단위 (PLAN §5).

    ``row_start``/``row_end`` 는 정렬(rows) 인덱스 범위 [start, end).
    ``left_range``/``right_range`` 는 원본 라인 인덱스 범위 [start, end);
    해당 쪽에 라인이 없으면(순수 insert/delete) ``None``.
    ``left_anchor``/``right_anchor`` 는 각 문서에서 이 hunk가 시작하는 라인 인덱스
    (= hunk 앞쪽 라인 수). 병합 시 삽입/교체 위치로 쓴다. 라인이 있으면
    ``*_range[0]`` 과 같고, 없으면(순수 insert/delete) 삽입 지점을 가리킨다.
    """

    id: int
    kind: str
    row_start: int
    row_end: int
    left_range: tuple[int, int] | None
    right_range: tuple[int, int] | None
    left_anchor: int = 0
    right_anchor: int = 0


@dataclass
class DiffResult:
    """diff 전체 결과 (PLAN §5)."""

    rows: list[Row] = field(default_factory=list)
    hunks: list[Hunk] = field(default_factory=list)
    moves: list = field(default_factory=list)  # Phase 4 (MovePair)


@dataclass(frozen=True)
class DiffOptions:
    """비교 옵션 (PLAN §4.4). 기본은 모두 OFF(공백/대소문자 구분)."""

    ignore_whitespace: bool = False
    ignore_case: bool = False
