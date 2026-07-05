"""앱 메인 윈도우 — 탭 단위 비교 세션 (PLAN §6.1).

하나의 창 안에서 파일 비교/폴더 비교 세션을 탭으로 연다. 상단 툴바의
'파일 비교'/'폴더 비교'로 탭을 추가하고, 각 탭(패널)은 자체 툴바를 갖는다.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QTabWidget, QToolBar

from rox_merge.core.document import Document
from rox_merge.ui.file_pane import FileComparePane
from rox_merge.ui.folder_pane import FolderComparePane


class AppWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("rox-merge")
        self.resize(1150, 780)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._sync_window_title)
        self.setCentralWidget(self._tabs)

        bar = QToolBar("세션")
        self.addToolBar(bar)
        self._act(bar, "＋ 파일 비교", "Ctrl+N", lambda: self.add_file_tab())
        self._act(bar, "＋ 폴더 비교", "Ctrl+D", self.add_folder_tab)

    def _act(self, bar, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        bar.addAction(action)
        self.addAction(action)
        return action

    # ------------------------------------------------------------- 탭 추가
    def add_file_tab(self, left: Document | None = None, right: Document | None = None):
        pane = FileComparePane()
        if left is not None:
            pane._set_doc("left", left)
        if right is not None:
            pane._set_doc("right", right)
        pane._recompute()
        index = self._tabs.addTab(pane, pane.title())
        pane.title_changed.connect(lambda t, p=pane: self._set_tab_title(p, t))
        pane.status_changed.connect(self.statusBar().showMessage)
        self._tabs.setCurrentIndex(index)
        return pane

    def add_folder_tab(self, left=None, right=None):
        pane = FolderComparePane()
        index = self._tabs.addTab(pane, pane.title())
        pane.title_changed.connect(lambda t, p=pane: self._set_tab_title(p, t))
        self._tabs.setCurrentIndex(index)
        if left and right:
            pane.set_roots(left, right)
        else:
            pane.prompt_roots()
        return pane

    # --------------------------------------------------------------- helpers
    def _set_tab_title(self, pane, title: str) -> None:
        idx = self._tabs.indexOf(pane)
        if idx >= 0:
            self._tabs.setTabText(idx, title)
        self._sync_window_title()

    def _sync_window_title(self, *_args) -> None:
        idx = self._tabs.currentIndex()
        name = self._tabs.tabText(idx) if idx >= 0 else ""
        self.setWindowTitle(f"rox-merge — {name}" if name else "rox-merge")

    def _close_tab(self, index: int) -> None:
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        if self._tabs.count() == 0:
            self.add_file_tab()  # 최소 한 탭 유지
