"""파일 비교 패널 (PLAN §6.2) — 탭에 들어가는 QWidget.

side-by-side DiffView + 미니맵. 편집/병합/Undo/재계산은 DiffController에 위임.
툴바/메뉴는 상위 AppWindow가 제공하며, 이 패널의 공개 메서드를 호출한다.
"""

from __future__ import annotations

import os
from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QWidget,
)

from rox_merge.app.compare_model import guard_note
from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.fileio import BinaryFileError, read_document, write_document
from rox_merge.ui.diff_controller import DiffController
from rox_merge.ui.diff_view import DiffView
from rox_merge.ui.overview_bar import OverviewBar
from rox_merge.ui.theme import Theme


class FileComparePane(QWidget):
    title_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = DiffView()
        self._overview = OverviewBar()
        self._ctl = DiffController(self._view, DiffOptions(), self)
        self._ctl.recomputed.connect(self._on_recomputed)
        self._view.active_side_changed.connect(lambda *_: self._emit_title())
        self._overview.row_clicked.connect(self._view.verticalScrollBar().setValue)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._view, 1)
        row.addWidget(self._overview)

        self._ctl.recompute()

    # ---------------------------------------------------- AppWindow 공개 API
    def controller(self) -> DiffController:
        return self._ctl

    def open_side(self, side: str) -> None:
        self._open(side)

    def save(self, as_new: bool = False) -> None:
        self._save_active(as_new)

    def options(self) -> DiffOptions:
        return self._ctl.options

    def apply_theme(self, theme: Theme) -> None:
        self._view.set_theme(theme)
        self._overview.set_theme(theme)

    def apply_font(self, pt: int) -> None:
        self._view.set_font_point_size(pt)

    def apply_options(self, opts: DiffOptions) -> None:
        self._ctl.set_options(opts)

    # --------------------------------------------------------------- slots
    def _open(self, side: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self.window(), f"{side} 파일 열기")
        if not path:
            return
        try:
            doc = read_document(path)
        except BinaryFileError as exc:
            QMessageBox.warning(self.window(), "바이너리 파일", str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self.window(), "열기 실패", str(exc))
            return
        self._ctl.set_document(side, doc)

    def _save_active(self, as_new: bool = False) -> None:
        self._ctl.commit_edit()
        side = self._view.active_side
        doc = self._ctl.left if side == "left" else self._ctl.right
        path = doc.path
        if as_new or path is None:
            path, _ = QFileDialog.getSaveFileName(self.window(), f"{side} 저장")
            if not path:
                return  # 취소(Esc) → 저장 안 함
        try:
            write_document(doc, path)
        except OSError as exc:
            QMessageBox.critical(self.window(), "저장 실패", str(exc))
            return
        self._emit_title()

    def _toggle_moves(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, detect_moves=enabled))

    def _toggle_whitespace(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, ignore_whitespace=enabled))

    def _toggle_case(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, ignore_case=enabled))

    # --------------------------------------------------------------- helpers
    def _on_recomputed(self) -> None:
        self._overview.set_result(self._view.result)
        self._emit_title()
        self.status_changed.emit(guard_note(self._ctl.left, self._ctl.right) or "")

    def _emit_title(self) -> None:
        self.title_changed.emit(self.title())

    def title(self) -> str:
        def name(doc: Document) -> str:
            base = os.path.basename(doc.path) if doc.path else "(빈)"
            return ("*" if doc.dirty else "") + base

        return f"{name(self._ctl.left)} ⇄ {name(self._ctl.right)}"

    # ------------------------------------------------------ 외부/테스트용
    def _set_doc(self, side: str, doc: Document) -> None:
        if side == "left":
            self._ctl.left = doc
        else:
            self._ctl.right = doc

    def _recompute(self) -> None:
        self._ctl.recompute()
