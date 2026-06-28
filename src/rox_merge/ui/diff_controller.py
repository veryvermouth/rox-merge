"""DiffView 편집/병합/Undo/재계산을 묶는 공용 컨트롤러.

파일 비교 창과 폴더 비교(분할 하단) 창이 동일한 편집 동작을 공유하도록,
toolbar/dialog 같은 창 고유 부분을 제외한 핵심 로직을 한곳에 모은다.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from rox_merge.app.commands import SetLinesCommand, UndoStack, make_apply_hunk
from rox_merge.app.compare_model import build_result, step_hunk
from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.fileio import new_document
from rox_merge.ui.diff_view import DiffView

_DEBOUNCE_MS = 150  # 편집 후 재계산 디바운스 (PLAN §4.6)


class DiffController(QObject):
    recomputed = Signal()  # 재계산/편집 후 — 상위 창이 제목·미니맵 등 갱신

    def __init__(self, view: DiffView, options: DiffOptions | None = None, parent=None):
        super().__init__(parent)
        self.view = view
        self.options = options or DiffOptions()
        self.left: Document = new_document()
        self.right: Document = new_document()
        self.undo = UndoStack()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_DEBOUNCE_MS)
        self._timer.timeout.connect(self.recompute)

        view.merge_requested.connect(self._on_merge)
        view.edited.connect(self._timer.start)
        view.edit_committed.connect(self._on_edit_committed)

    # --------------------------------------------------------------- documents
    def set_documents(self, left: Document, right: Document) -> None:
        self.left, self.right = left, right
        self.undo.clear()
        self.recompute()

    def set_document(self, side: str, doc: Document) -> None:
        if side == "left":
            self.left = doc
        else:
            self.right = doc
        self.recompute()

    def set_options(self, options: DiffOptions) -> None:
        self.options = options
        self.recompute()

    def active_doc(self) -> Document:
        return self.left if self.view.active_side == "left" else self.right

    # ----------------------------------------------------------------- compute
    def recompute(self) -> None:
        result = build_result(self.left, self.right, self.options)
        self.view.set_data(self.left, self.right, result)
        self.recomputed.emit()

    # ------------------------------------------------------------ edit / merge
    def commit_edit(self) -> None:
        self.view.commit_edit()

    def _on_merge(self, hunk_id: int, direction: str) -> None:
        self.commit_edit()
        hunks = self.view.result.hunks
        if 0 <= hunk_id < len(hunks):
            self.undo.push(make_apply_hunk(self.left, self.right, hunks[hunk_id], direction))
            self.recompute()

    def _on_edit_committed(self, side: str, old_lines, new_lines) -> None:
        doc = self.left if side == "left" else self.right
        doc.dirty = True  # 직접 편집도 미저장 변경으로 표시
        self.undo.record(SetLinesCommand(doc, old_lines, new_lines))
        self.recomputed.emit()

    def undo_action(self) -> None:
        self.commit_edit()
        if self.undo.can_undo():
            self.undo.undo()
            self.recompute()

    def redo_action(self) -> None:
        self.commit_edit()
        if self.undo.can_redo():
            self.undo.redo()
            self.recompute()

    # -------------------------------------------------------------- navigation
    def jump(self, delta: int) -> None:
        idx = step_hunk(self.view.current_hunk, delta, len(self.view.result.hunks))
        if idx >= 0:
            self.view.set_current_hunk(idx)

    def zoom(self, delta: int) -> None:
        self.view.set_font_point_size(self.view.font_point_size() + delta)

    def zoom_reset(self) -> None:
        self.view.set_font_point_size(self.view.base_font_point_size())
