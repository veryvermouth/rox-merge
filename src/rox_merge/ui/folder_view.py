"""폴더 비교 윈도우 (PLAN §6.4).

위: 좌/우 대응 폴더 트리(왼쪽 | 오른쪽, 가운데 기준 동일 너비), 상태는 색으로 표시.
파일 더블클릭 시 여는 방식은 툴바 토글로 두 가지:
- **분할 모드(기본)**: 트리 아래 diff 창에 표시(하단만 교체). Esc로 트리 복귀.
- **새 탭 모드**: 더블클릭할 때마다 새 비교 탭 생성. Esc로 폴더 탭 복귀.
diff 뷰는 편집 가능. 필터/펼치기·접기(Ctrl+]/[/0)/비교 정밀도 토글 지원.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
)

from rox_merge.core.folder_compare import (
    DIFFERENT,
    LEFT_ONLY,
    MODE_EXACT,
    MODE_FAST,
    RIGHT_ONLY,
    SAME,
    CompareNode,
    compare_dirs,
)
from rox_merge.fileio import BinaryFileError, new_document, read_document, write_document
from rox_merge.ui.diff_controller import DiffController
from rox_merge.ui.diff_view import DiffView

_STATUS_COLOR = {
    SAME: QColor(120, 120, 120),
    DIFFERENT: QColor(180, 120, 0),
    LEFT_ONLY: QColor(200, 60, 60),
    RIGHT_ONLY: QColor(40, 150, 60),
}
_ROLE_NODE = Qt.ItemDataRole.UserRole


class FolderCompareWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("rox-merge — 폴더 비교")
        self.resize(1100, 760)

        self._left_root: Path | None = None
        self._right_root: Path | None = None
        self._mode = MODE_FAST
        self._diff_only = False
        self._tab_mode = False
        self._tab_controllers: dict[object, DiffController] = {}  # DiffView -> DiffController
        self._children: list = []  # 이 창에서 연 다른 비교 창 참조 유지

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["왼쪽", "오른쪽"])
        self._tree.setColumnCount(2)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        # 폴더 탭(탭 0): 트리 + 분할 모드용 하단 diff
        self._diff = DiffView()
        self._diff.hide()
        self._ctl = DiffController(self._diff, parent=self)
        self._folder_page = QSplitter(Qt.Orientation.Vertical)
        self._folder_page.addWidget(self._tree)
        self._folder_page.addWidget(self._diff)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.addTab(self._folder_page, "폴더")
        self._tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.setCentralWidget(self._tabs)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._on_escape)

        self._build_actions()

    # ------------------------------------------------------------- actions
    def _build_actions(self) -> None:
        bar = self.addToolBar("main")
        self._act(bar, "파일 비교", "Ctrl+N", self._open_file_compare)
        self._act(bar, "새 폴더 비교", "Ctrl+D", self._open_folder_compare)
        bar.addSeparator()
        self._act(bar, "왼쪽 폴더", None, lambda: self._pick_root("left"))
        self._act(bar, "오른쪽 폴더", None, lambda: self._pick_root("right"))
        self._act(bar, "새로고침", "F5", self._refresh)
        bar.addSeparator()

        self._filter_act = QAction("다른 항목만", self)
        self._filter_act.setCheckable(True)
        self._filter_act.toggled.connect(self._toggle_filter)
        bar.addAction(self._filter_act)

        self._mode_act = QAction("정확 비교(해시)", self)
        self._mode_act.setCheckable(True)
        self._mode_act.toggled.connect(self._toggle_mode)
        bar.addAction(self._mode_act)

        self._tabmode_act = QAction("새 탭 모드", self)
        self._tabmode_act.setCheckable(True)
        self._tabmode_act.toggled.connect(self._toggle_tab_mode)
        bar.addAction(self._tabmode_act)
        bar.addSeparator()

        self._act(bar, "전체 펼침", "Ctrl+]", self._tree.expandAll)
        self._act(bar, "전체 접기", "Ctrl+[", self._tree.collapseAll)
        self._act(bar, "초기 상태", "Ctrl+0", self._expand_differences)
        bar.addSeparator()

        # 하단/탭 diff 편집용 (현재 활성 diff 대상)
        self._act(bar, "저장", "Ctrl+S", self._save_active)
        self._act(bar, "실행 취소", "Ctrl+Z", lambda: self._active_controller().undo_action())
        self._act(bar, "다시 실행", ["Ctrl+Shift+Z", "Ctrl+Y"],
                  lambda: self._active_controller().redo_action())
        self._act(bar, "이전 차이", "Ctrl+1", lambda: self._active_controller().jump(-1))
        self._act(bar, "다음 차이", "Ctrl+2", lambda: self._active_controller().jump(+1))

    def _act(self, bar, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if isinstance(shortcut, list):
            action.setShortcuts([QKeySequence(s) for s in shortcut])
        elif shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        bar.addAction(action)
        return action

    # --------------------------------------------------------------- public
    def set_roots(self, left: str | Path, right: str | Path) -> None:
        self._left_root = Path(left)
        self._right_root = Path(right)
        self._refresh()

    def prompt_roots(self) -> None:
        """좌/우 폴더를 순서대로 선택받아 비교한다."""
        left = QFileDialog.getExistingDirectory(self, "왼쪽 폴더 선택")
        if not left:
            return
        right = QFileDialog.getExistingDirectory(self, "오른쪽 폴더 선택")
        if not right:
            return
        self.set_roots(left, right)

    # -------------------------------------------------------- 다른 모드 열기
    def _open_file_compare(self) -> None:
        from rox_merge.ui.main_window import MainWindow

        win = MainWindow()
        self._children.append(win)
        win.show()

    def _open_folder_compare(self) -> None:
        win = FolderCompareWindow()
        self._children.append(win)
        win.show()
        win.prompt_roots()

    # --------------------------------------------------------------- slots
    def _pick_root(self, side: str) -> None:
        path = QFileDialog.getExistingDirectory(self, f"{side} 폴더 선택")
        if not path:
            return
        if side == "left":
            self._left_root = Path(path)
        else:
            self._right_root = Path(path)
        if self._left_root and self._right_root:
            self._refresh()

    def _refresh(self) -> None:
        if not (self._left_root and self._right_root):
            return
        root = compare_dirs(self._left_root, self._right_root, self._mode)
        self._tree.clear()
        for child in root.children:
            self._add_node(self._tree.invisibleRootItem(), child)
        self._expand_differences()
        self.setWindowTitle(f"rox-merge — 폴더 비교: {self._left_root}  ⇄  {self._right_root}")

    def _add_node(self, parent_item, node: CompareNode) -> QTreeWidgetItem | None:
        if self._diff_only and not node.has_difference:
            return None
        left_name = node.name if node.left_exists else ""
        right_name = node.name if node.right_exists else ""
        item = QTreeWidgetItem([left_name, right_name])
        item.setData(0, _ROLE_NODE, node)
        color = QBrush(_STATUS_COLOR.get(node.status, QColor(0, 0, 0)))
        item.setForeground(0, color)
        item.setForeground(1, color)
        parent_item.addChild(item)
        for child in node.children:
            self._add_node(item, child)
        return item

    def _expand_differences(self) -> None:
        def walk(item):
            node: CompareNode = item.data(0, _ROLE_NODE)
            if node and node.is_dir:
                item.setExpanded(node.has_difference)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))

    def _toggle_filter(self, enabled: bool) -> None:
        self._diff_only = enabled
        self._refresh()

    def _toggle_mode(self, exact: bool) -> None:
        self._mode = MODE_EXACT if exact else MODE_FAST
        self._refresh()

    def _toggle_tab_mode(self, enabled: bool) -> None:
        self._tab_mode = enabled

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        node: CompareNode = item.data(0, _ROLE_NODE)
        if node is None or node.is_dir:
            item.setExpanded(not item.isExpanded())
            return
        self._open_file_pair(node)

    def _open_file_pair(self, node: CompareNode) -> None:
        # 분할 모드에서 하단이 dirty면 교체 전 2지선다 경고 (PLAN §6.4)
        if not self._tab_mode and not self._diff.isHidden():
            self._ctl.commit_edit()
            if (self._ctl.left.dirty or self._ctl.right.dirty) and not self._confirm_discard():
                return

        left_doc = self._load(self._left_root / node.relpath) if node.left_exists else new_document()
        if left_doc is None:
            return
        right_doc = self._load(self._right_root / node.relpath) if node.right_exists else new_document()
        if right_doc is None:
            return

        if self._tab_mode:
            self._open_in_new_tab(node.name, left_doc, right_doc)
        else:
            self._ctl.set_documents(left_doc, right_doc)
            self._show_diff()

    def _open_in_new_tab(self, name, left_doc, right_doc) -> None:
        view = DiffView()
        ctl = DiffController(view, self._ctl.options, self)
        self._tab_controllers[view] = ctl
        ctl.set_documents(left_doc, right_doc)
        idx = self._tabs.addTab(view, name)
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        if index == 0:
            return
        view = self._tabs.widget(index)
        ctl = self._tab_controllers.get(view)
        if ctl is not None:
            ctl.commit_edit()
            if (ctl.left.dirty or ctl.right.dirty) and not self._confirm_discard():
                return
            del self._tab_controllers[view]
        self._tabs.removeTab(index)
        view.deleteLater()

    def _active_controller(self) -> DiffController:
        """현재 탭의 diff 컨트롤러(폴더 탭이면 하단 diff)."""
        widget = self._tabs.currentWidget()
        return self._tab_controllers.get(widget, self._ctl)

    def _save_active(self) -> None:
        ctl = self._active_controller()
        if ctl is self._ctl and self._diff.isHidden():
            return
        ctl.commit_edit()
        side = ctl.view.active_side
        doc = ctl.left if side == "left" else ctl.right
        path = doc.path
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, f"{side} 저장")
            if not path:
                return
        try:
            write_document(doc, path)
        except OSError as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        self._refresh()

    def _on_escape(self) -> None:
        """Esc: 새 탭 모드면 폴더 탭으로, 분할 모드면 하단 diff 숨김."""
        if self._tabs.currentIndex() != 0:
            self._tabs.setCurrentIndex(0)
        else:
            self._hide_diff()

    def _confirm_discard(self) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("저장하지 않은 변경")
        box.setText("저장하지 않은 편집이 있습니다.\n무시하고 계속할까요?")
        discard = box.addButton("무시하고 계속", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is discard

    def _show_diff(self) -> None:
        if self._diff.isHidden():
            self._diff.show()
            total = self._folder_page.height() or 760
            self._folder_page.setSizes([total // 2, total // 2])

    def _hide_diff(self) -> None:
        if not self._diff.isHidden():
            self._diff.hide()
            self._tree.setFocus()

    def _load(self, path: Path):
        try:
            return read_document(path)
        except BinaryFileError:
            QMessageBox.information(self, "바이너리 파일", f"바이너리 파일 - 비교 불가:\n{path}")
            return None
        except OSError as exc:
            QMessageBox.warning(self, "열기 실패", str(exc))
            return None
