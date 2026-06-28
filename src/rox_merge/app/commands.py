"""편집/병합 커맨드와 Undo/Redo 스택 (PLAN §3, §5).

순수 로직 — Document.lines 를 조작하며 Qt에 의존하지 않는다.
편집과 병합은 같은 :class:`UndoStack` 을 공유한다(통합 스택, PLAN §6.2).
"""

from __future__ import annotations

from typing import Protocol

from rox_merge.core.diff import DiffResult, Hunk
from rox_merge.core.document import Document


class Command(Protocol):
    """apply/undo 를 갖는 명령 (PLAN §5)."""

    def apply(self) -> None: ...
    def undo(self) -> None: ...


class ReplaceLinesCommand:
    """대상 문서의 라인 구간을 새 라인들로 교체하는 기본 명령.

    병합(ApplyHunk)·직접 편집 모두 이 한 가지 연산으로 표현된다.
    최초 apply 때 교체 전 내용을 기억해 undo/redo가 정확히 복원된다.
    """

    def __init__(
        self,
        target: Document,
        start: int,
        old_len: int,
        new_lines: list[str],
    ):
        self._target = target
        self._start = start
        self._old_len = old_len
        self._new_lines = list(new_lines)
        self._old_lines: list[str] | None = None

    def apply(self) -> None:
        if self._old_lines is None:
            self._old_lines = list(
                self._target.lines[self._start : self._start + self._old_len]
            )
        self._target.lines[self._start : self._start + self._old_len] = self._new_lines
        self._target.dirty = True

    def undo(self) -> None:
        assert self._old_lines is not None, "apply 전에 undo 불가"
        self._target.lines[self._start : self._start + len(self._new_lines)] = self._old_lines
        self._target.dirty = True


def make_apply_hunk(
    left: Document, right: Document, hunk: Hunk, direction: str
) -> ReplaceLinesCommand:
    """hunk를 한 방향으로 적용하는 명령을 만든다 (PLAN §6.2).

    direction: ``"l2r"`` (왼쪽→오른쪽 적용) 또는 ``"r2l"``.
    대상 쪽 구간을 원본 쪽 구간 내용으로 교체한다(없으면 추가/삭제).
    """
    left_len = hunk.left_range[1] - hunk.left_range[0] if hunk.left_range else 0
    right_len = hunk.right_range[1] - hunk.right_range[0] if hunk.right_range else 0

    if direction == "l2r":
        src_lines = left.lines[hunk.left_anchor : hunk.left_anchor + left_len]
        return ReplaceLinesCommand(right, hunk.right_anchor, right_len, src_lines)
    if direction == "r2l":
        src_lines = right.lines[hunk.right_anchor : hunk.right_anchor + right_len]
        return ReplaceLinesCommand(left, hunk.left_anchor, left_len, src_lines)
    raise ValueError(f"알 수 없는 방향: {direction!r}")


class UndoStack:
    """편집·병합 공유 Undo/Redo 스택 (PLAN §6.2 통합 스택)."""

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def push(self, command: Command) -> None:
        """명령을 실행하고 스택에 쌓는다. 새 명령은 redo 이력을 비운다."""
        command.apply()
        self._undo.append(command)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo:
            return
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)

    def redo(self) -> None:
        if not self._redo:
            return
        command = self._redo.pop()
        command.apply()
        self._undo.append(command)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
