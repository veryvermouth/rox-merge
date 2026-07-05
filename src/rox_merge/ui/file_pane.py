"""파일 비교 패널 (PLAN §6.2) — 탭에 들어가는 QWidget.

자체 툴바 + side-by-side DiffView + 미니맵. 편집/병합/Undo/재계산은
:class:`DiffController` 에 위임. 제목/상태는 시그널로 상위(AppWindow)에 알린다.
"""

from __future__ import annotations

import os
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from rox_merge.app.compare_model import guard_note
from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.fileio import BinaryFileError, read_document, write_document
from rox_merge.ui.diff_controller import DiffController
from rox_merge.ui.diff_view import DiffView
from rox_merge.ui.overview_bar import OverviewBar
from rox_merge.ui.theme import Theme, dark_palette


class FileComparePane(QWidget):
    title_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._light_palette = QApplication.instance().palette()
        self._view = DiffView()
        self._overview = OverviewBar()
        self._ctl = DiffController(self._view, DiffOptions(), self)
        self._ctl.recomputed.connect(self._on_recomputed)
        self._view.active_side_changed.connect(lambda *_: self._emit_title())
        self._overview.row_clicked.connect(self._view.verticalScrollBar().setValue)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())

        body = QWidget()
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._view, 1)
        row.addWidget(self._overview)
        layout.addWidget(body, 1)

        self._ctl.recompute()

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar()
        self._add(bar, "왼쪽 열기", "Ctrl+O", lambda: self._open("left"))
        self._add(bar, "오른쪽 열기", "Ctrl+Shift+O", lambda: self._open("right"))
        self._add(bar, "저장", "Ctrl+S", self._save_active)
        self._add(bar, "다른 이름으로", "Ctrl+Shift+S", lambda: self._save_active(as_new=True))
        bar.addSeparator()
        self._add(bar, "실행 취소", "Ctrl+Z", self._ctl.undo_action)
        self._add(bar, "다시 실행", ["Ctrl+Shift+Z", "Ctrl+Y"], self._ctl.redo_action)
        bar.addSeparator()
        self._add(bar, "이전 차이", "Ctrl+1", lambda: self._ctl.jump(-1))
        self._add(bar, "다음 차이", "Ctrl+2", lambda: self._ctl.jump(+1))
        bar.addSeparator()
        opts = self._ctl.options
        self._toggle(bar, "이동 탐지", opts.detect_moves, self._toggle_moves)
        self._toggle(bar, "공백 무시", opts.ignore_whitespace, self._toggle_whitespace)
        self._toggle(bar, "대소문자 무시", opts.ignore_case, self._toggle_case)
        bar.addSeparator()
        self._add(bar, "글꼴 +", ["Ctrl++", "Ctrl+="], lambda: self._ctl.zoom(+1))
        self._add(bar, "글꼴 -", "Ctrl+-", lambda: self._ctl.zoom(-1))
        self._add(bar, "글꼴 100%", "Ctrl+0", self._ctl.zoom_reset)
        self._toggle(bar, "다크 테마", False, self._toggle_dark)
        return bar

    def _add(self, bar, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if isinstance(shortcut, list):
            action.setShortcuts([QKeySequence(s) for s in shortcut])
        else:
            action.setShortcut(QKeySequence(shortcut))
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(slot)
        bar.addAction(action)
        self.addAction(action)  # 현재 탭(위젯)에 포커스 있을 때 단축키 동작
        return action

    def _toggle(self, bar, text, checked, slot) -> QAction:
        action = QAction(text, self)
        action.setCheckable(True)
        action.setChecked(checked)
        action.toggled.connect(slot)
        bar.addAction(action)
        return action

    # --------------------------------------------------------------- slots
    def _open(self, side: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"{side} 파일 열기")
        if not path:
            return
        try:
            doc = read_document(path)
        except BinaryFileError as exc:
            QMessageBox.warning(self, "바이너리 파일", str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, "열기 실패", str(exc))
            return
        self._ctl.set_document(side, doc)

    def _save_active(self, as_new: bool = False) -> None:
        self._ctl.commit_edit()
        side = self._view.active_side
        doc = self._ctl.left if side == "left" else self._ctl.right
        path = doc.path
        if as_new or path is None:
            path, _ = QFileDialog.getSaveFileName(self, f"{side} 저장")
            if not path:
                return
        try:
            write_document(doc, path)
        except OSError as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        self._emit_title()

    def _toggle_dark(self, enabled: bool) -> None:
        theme = Theme(dark=enabled)
        self._view.set_theme(theme)
        self._overview.set_theme(theme)
        app = QApplication.instance()
        if app is not None:
            app.setPalette(dark_palette() if enabled else self._light_palette)

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
        def name(doc: Document) -> str:
            base = os.path.basename(doc.path) if doc.path else "(빈)"
            return ("*" if doc.dirty else "") + base

        self.title_changed.emit(f"{name(self._ctl.left)} ⇄ {name(self._ctl.right)}")

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
