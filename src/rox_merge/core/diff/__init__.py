"""Diff 엔진 (PLAN §4). 순수 Python, UI/Qt 무의존."""

from rox_merge.core.diff.engine import compute_diff, normalize_whitespace
from rox_merge.core.diff.models import (
    KIND_CHANGE,
    KIND_DELETE,
    KIND_EQUAL,
    KIND_INSERT,
    KIND_MOVED,
    KIND_WHITESPACE,
    VALID_KINDS,
    DiffOptions,
    DiffResult,
    Hunk,
    MovePair,
    Row,
    Span,
)

__all__ = [
    "compute_diff",
    "normalize_whitespace",
    "DiffOptions",
    "DiffResult",
    "Row",
    "Hunk",
    "MovePair",
    "Span",
    "VALID_KINDS",
    "KIND_EQUAL",
    "KIND_CHANGE",
    "KIND_WHITESPACE",
    "KIND_INSERT",
    "KIND_DELETE",
    "KIND_MOVED",
]
