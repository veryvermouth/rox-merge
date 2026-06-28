"""Core 계층 — 순수 Python 데이터 모델과 diff 엔진. UI/Qt에 의존하지 않는다."""

from rox_merge.core.document import (
    DEFAULT_LINE_ENDING,
    LINE_ENDING_CHARS,
    Document,
    LineEnding,
)

__all__ = [
    "Document",
    "LineEnding",
    "LINE_ENDING_CHARS",
    "DEFAULT_LINE_ENDING",
]
