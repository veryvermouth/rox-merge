"""파일 비교 메인 윈도우 (PLAN §6.2).

좌/우 문서 세션, 툴바, 단축키(열기/저장/점프/글꼴 줌)를 묶는다.
직접 편집·병합·Undo/Redo·실시간 재계산은 Phase 3에서 추가.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from rox_merge.app.commands import UndoStack, make_apply_hunk
from rox_merge.app.compare_model import build_result, step_hunk
from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.fileio import BinaryFileError, new_document, read_document, write_document
from rox_merge.ui.diff_view import DiffView
from rox_merge.ui.overview_bar import OverviewBar


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("rox-merge")
        self.resize(1100, 720)

        self._left: Document = new_document()
        self._right: Document = new_document()
        self._options = DiffOptions()
        self._undo = UndoStack()

        self._view = DiffView()
        self._overview = OverviewBar()
        self._view.active_side_changed.connect(self._on_active_side_changed)
        self._view.merge_requested.connect(self._on_merge)
        self._overview.row_clicked.connect(self._view.verticalScrollBar().setValue)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._overview)
        self.setCentralWidget(central)

        self._build_actions()
        self._recompute()

    # ------------------------------------------------------------- actions
    def _build_actions(self) -> None:
        bar = self.addToolBar("main")

        self._add_action(bar, "왼쪽 열기", "Ctrl+O", lambda: self._open("left"))
        self._add_action(bar, "오른쪽 열기", "Ctrl+Shift+O", lambda: self._open("right"))
        self._add_action(bar, "저장", "Ctrl+S", self._save_active)
        self._add_action(bar, "다른 이름으로", "Ctrl+Shift+S", lambda: self._save_active(as_new=True))
        bar.addSeparator()
        self._add_action(bar, "실행 취소", "Ctrl+Z", self._undo_action)
        self._add_action(bar, "다시 실행", ["Ctrl+Shift+Z", "Ctrl+Y"], self._redo_action)
        bar.addSeparator()
        self._add_action(bar, "이전 차이", "Ctrl+2", lambda: self._jump(-1))
        self._add_action(bar, "다음 차이", "Ctrl+3", lambda: self._jump(+1))
        bar.addSeparator()
        # Ctrl++ 는 대다수 키보드에서 Ctrl+= 로 입력돼 둘 다 바인딩 (PLAN §6.2)
        self._add_action(bar, "글꼴 +", ["Ctrl++", "Ctrl+="], lambda: self._zoom(+1))
        self._add_action(bar, "글꼴 -", "Ctrl+-", lambda: self._zoom(-1))
        self._add_action(bar, "글꼴 100%", "Ctrl+0", self._zoom_reset)
        bar.addSeparator()
        self._add_action(bar, "닫기", "Ctrl+W", self.close)

    def _add_action(self, bar, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if isinstance(shortcut, list):
            action.setShortcuts([QKeySequence(s) for s in shortcut])
        else:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        bar.addAction(action)  # 툴바가 윈도우에 속해 단축키는 윈도우 레벨로 동작
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
        self._set_doc(side, doc)
        self._recompute()

    def _save_active(self, as_new: bool = False) -> None:
        side = self._view.active_side
        doc = self._left if side == "left" else self._right
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
        self._update_title()

    def _on_merge(self, hunk_id: int, direction: str) -> None:
        hunks = self._view.result.hunks
        if not (0 <= hunk_id < len(hunks)):
            return
        command = make_apply_hunk(self._left, self._right, hunks[hunk_id], direction)
        self._undo.push(command)
        self._recompute()

    def _undo_action(self) -> None:
        if self._undo.can_undo():
            self._undo.undo()
            self._recompute()

    def _redo_action(self) -> None:
        if self._undo.can_redo():
            self._undo.redo()
            self._recompute()

    def _jump(self, delta: int) -> None:
        result = self._view.result
        idx = step_hunk(self._view.current_hunk, delta, len(result.hunks))
        if idx >= 0:
            self._view.set_current_hunk(idx)

    def _zoom(self, delta: int) -> None:
        self._view.set_font_point_size(self._view.font_point_size() + delta)

    def _zoom_reset(self) -> None:
        self._view.set_font_point_size(self._view.base_font_point_size())

    def _on_active_side_changed(self, side: str) -> None:
        self._update_title()

    # --------------------------------------------------------------- helpers
    def _set_doc(self, side: str, doc: Document) -> None:
        if side == "left":
            self._left = doc
        else:
            self._right = doc

    def _recompute(self) -> None:
        result = build_result(self._left, self._right, self._options)
        self._view.set_data(self._left.lines, self._right.lines, result)
        self._overview.set_result(result)
        self._update_title()

    def _update_title(self) -> None:
        def label(doc: Document) -> str:
            name = doc.path if doc.path else "(빈 버퍼)"
            return ("*" if doc.dirty else "") + name

        self.setWindowTitle(f"rox-merge — {label(self._left)}  ⇄  {label(self._right)}")
