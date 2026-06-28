"""폴더 비교 윈도우 (PLAN §6.4) — 분할 모드.

위: 폴더 비교 트리, 아래: 더블클릭한 파일의 diff 뷰(읽기 전용).
필터(다른 항목만), 전체 펼치기/접기(Ctrl+]/[/0), 비교 정밀도 토글,
초기 확장은 '차이 있는 곳만'.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
)

from rox_merge.app.compare_model import build_result
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
from rox_merge.fileio import BinaryFileError, new_document, read_document
from rox_merge.ui.diff_view import DiffView

_STATUS_LABEL = {
    SAME: "동일",
    DIFFERENT: "내용 다름",
    LEFT_ONLY: "좌측만",
    RIGHT_ONLY: "우측만",
}
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

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["왼쪽", "상태", "오른쪽"])
        self._tree.setColumnWidth(0, 430)
        self._tree.setColumnWidth(1, 90)
        self._tree.setColumnWidth(2, 430)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._diff = DiffView()
        self._diff.set_read_only(True)
        self._diff.hide()  # 파일 더블클릭 전에는 숨김

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._tree)
        self._splitter.addWidget(self._diff)
        self.setCentralWidget(self._splitter)

        # diff 보기 중 Esc → 트리 화면으로 복귀
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._hide_diff)

        self._build_actions()

    # ------------------------------------------------------------- actions
    def _build_actions(self) -> None:
        bar = self.addToolBar("main")
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
        bar.addSeparator()

        self._act(bar, "전체 펼침", "Ctrl+]", self._tree.expandAll)
        self._act(bar, "전체 접기", "Ctrl+[", self._tree.collapseAll)
        self._act(bar, "초기 상태", "Ctrl+0", self._expand_differences)

    def _act(self, bar, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        bar.addAction(action)
        return action

    # --------------------------------------------------------------- public
    def set_roots(self, left: str | Path, right: str | Path) -> None:
        self._left_root = Path(left)
        self._right_root = Path(right)
        self._refresh()

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
        # 좌/우 대응: 한쪽만 존재하면 반대쪽 칸은 빈칸
        left_name = node.name if node.left_exists else ""
        right_name = node.name if node.right_exists else ""
        item = QTreeWidgetItem(
            [left_name, _STATUS_LABEL.get(node.status, node.status), right_name]
        )
        item.setData(0, _ROLE_NODE, node)
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
        color = QBrush(_STATUS_COLOR.get(node.status, QColor(0, 0, 0)))
        for col in (0, 1, 2):
            item.setForeground(col, color)
        parent_item.addChild(item)
        for child in node.children:
            self._add_node(item, child)
        return item

    def _expand_differences(self) -> None:
        """차이 있는 폴더만 펼친다(초기 확장 상태)."""
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

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        node: CompareNode = item.data(0, _ROLE_NODE)
        if node is None or node.is_dir:
            item.setExpanded(not item.isExpanded())
            return
        self._open_file_pair(node)

    def _open_file_pair(self, node: CompareNode) -> None:
        left_doc = self._load(self._left_root / node.relpath) if node.left_exists else new_document()
        if left_doc is None:
            return
        right_doc = self._load(self._right_root / node.relpath) if node.right_exists else new_document()
        if right_doc is None:
            return
        result = build_result(left_doc, right_doc)
        self._diff.set_data(left_doc, right_doc, result)
        self._show_diff()

    def _show_diff(self) -> None:
        if self._diff.isHidden():
            self._diff.show()
            total = self._splitter.height() or 760
            self._splitter.setSizes([total // 2, total // 2])

    def _hide_diff(self) -> None:
        """diff 보기 종료 → 트리 화면으로 복귀 (Esc)."""
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
