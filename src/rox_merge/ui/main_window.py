"""파일 비교 메인 윈도우 (PLAN §6.2).

좌/우 문서 세션, 툴바, 단축키를 묶는다. 편집/병합/Undo/재계산은
:class:`DiffController` 에 위임한다(폴더 비교 창과 공유).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.fileio import BinaryFileError, read_document, write_document
from rox_merge.ui.diff_controller import DiffController
from rox_merge.ui.diff_view import DiffView
from rox_merge.ui.overview_bar import OverviewBar


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("rox-merge")
        self.resize(1100, 720)

        self._view = DiffView()
        self._overview = OverviewBar()
        self._ctl = DiffController(self._view, DiffOptions(), self)
        self._ctl.recomputed.connect(self._on_recomputed)
        self._view.active_side_changed.connect(self._update_title)
        self._overview.row_clicked.connect(self._view.verticalScrollBar().setValue)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._overview)
        self.setCentralWidget(central)

        self._build_actions()
        self._ctl.recompute()

    # ------------------------------------------------------------- actions
    def _build_actions(self) -> None:
        bar = self.addToolBar("main")

        self._add_action(bar, "왼쪽 열기", "Ctrl+O", lambda: self._open("left"))
        self._add_action(bar, "오른쪽 열기", "Ctrl+Shift+O", lambda: self._open("right"))
        self._add_action(bar, "저장", "Ctrl+S", self._save_active)
        self._add_action(bar, "다른 이름으로", "Ctrl+Shift+S", lambda: self._save_active(as_new=True))
        bar.addSeparator()
        self._add_action(bar, "실행 취소", "Ctrl+Z", self._ctl.undo_action)
        self._add_action(bar, "다시 실행", ["Ctrl+Shift+Z", "Ctrl+Y"], self._ctl.redo_action)
        bar.addSeparator()
        self._add_action(bar, "이전 차이", "Ctrl+1", lambda: self._ctl.jump(-1))
        self._add_action(bar, "다음 차이", "Ctrl+2", lambda: self._ctl.jump(+1))
        bar.addSeparator()
        move_action = QAction("이동 탐지", self)
        move_action.setCheckable(True)
        move_action.setChecked(self._ctl.options.detect_moves)
        move_action.toggled.connect(self._toggle_moves)
        bar.addAction(move_action)
        bar.addSeparator()
        # Ctrl++ 는 대다수 키보드에서 Ctrl+= 로 입력돼 둘 다 바인딩 (PLAN §6.2)
        self._add_action(bar, "글꼴 +", ["Ctrl++", "Ctrl+="], lambda: self._ctl.zoom(+1))
        self._add_action(bar, "글꼴 -", "Ctrl+-", lambda: self._ctl.zoom(-1))
        self._add_action(bar, "글꼴 100%", "Ctrl+0", self._ctl.zoom_reset)
        bar.addSeparator()
        self._add_action(bar, "닫기", "Ctrl+W", self.close)

    def _toggle_moves(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, detect_moves=enabled))

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
        self._update_title()

    # --------------------------------------------------------------- helpers
    def _on_recomputed(self) -> None:
        self._overview.set_result(self._view.result)
        self._update_title()

    def _update_title(self, *_args) -> None:
        def label(doc: Document) -> str:
            name = doc.path if doc.path else "(빈 버퍼)"
            return ("*" if doc.dirty else "") + name

        self.setWindowTitle(
            f"rox-merge — {label(self._ctl.left)}  ⇄  {label(self._ctl.right)}"
        )

    # ------------------------------------------------------ compat shims
    # (app.py / 검증 스크립트 호환)
    @property
    def _left(self) -> Document:
        return self._ctl.left

    @_left.setter
    def _left(self, doc: Document) -> None:
        self._ctl.left = doc

    @property
    def _right(self) -> Document:
        return self._ctl.right

    @_right.setter
    def _right(self, doc: Document) -> None:
        self._ctl.right = doc

    def _set_doc(self, side: str, doc: Document) -> None:
        if side == "left":
            self._ctl.left = doc
        else:
            self._ctl.right = doc

    def _recompute(self) -> None:
        self._ctl.recompute()

    def _jump(self, delta: int) -> None:
        self._ctl.jump(delta)

    def _undo_action(self) -> None:
        self._ctl.undo_action()

    def _on_merge(self, hunk_id: int, direction: str) -> None:
        self._ctl._on_merge(hunk_id, direction)
