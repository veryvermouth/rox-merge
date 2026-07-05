"""폴더 비교 윈도우 (PLAN §6.4) — 분할 모드.

위: 좌/우 대응 폴더 트리(왼쪽 | 오른쪽, 가운데 기준 동일 너비), 상태는 색으로 표시.
아래: 더블클릭한 파일의 diff 뷰(편집 가능). diff 보기 중 Esc → 트리 화면 복귀.
필터(다른 항목만), 전체 펼치기/접기(Ctrl+]/[/0), 비교 정밀도 토글,
초기 확장은 '차이 있는 곳만'.
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

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["왼쪽", "오른쪽"])
        self._tree.setColumnCount(2)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._diff = DiffView()  # 편집 가능
        self._diff.hide()        # 파일 더블클릭 전에는 숨김
        self._ctl = DiffController(self._diff, parent=self)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._tree)
        self._splitter.addWidget(self._diff)
        self.setCentralWidget(self._splitter)

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
        bar.addSeparator()

        # 하단 diff 편집용
        self._act(bar, "저장", "Ctrl+S", self._save_active)
        self._act(bar, "실행 취소", "Ctrl+Z", self._ctl.undo_action)
        self._act(bar, "다시 실행", ["Ctrl+Shift+Z", "Ctrl+Y"], self._ctl.redo_action)
        self._act(bar, "이전 차이", "Ctrl+1", lambda: self._ctl.jump(-1))
        self._act(bar, "다음 차이", "Ctrl+2", lambda: self._ctl.jump(+1))

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
        # 분할 모드 dirty 경고 (PLAN §6.4): 아래 창에 미저장 변경이 있으면
        # 곧바로 교체하지 않고 2지선다(현재 창 유지 / 무시하고 열기)로 확인.
        if not self._diff.isHidden():
            self._ctl.commit_edit()  # 진행 중 타이핑 반영
            if self._ctl.left.dirty or self._ctl.right.dirty:
                if not self._confirm_discard():
                    return

        left_doc = self._load(self._left_root / node.relpath) if node.left_exists else new_document()
        if left_doc is None:
            return
        right_doc = self._load(self._right_root / node.relpath) if node.right_exists else new_document()
        if right_doc is None:
            return
        self._ctl.set_documents(left_doc, right_doc)
        self._show_diff()

    def _save_active(self) -> None:
        if self._diff.isHidden():
            return
        self._ctl.commit_edit()
        side = self._diff.active_side
        doc = self._ctl.left if side == "left" else self._ctl.right
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
        self._refresh()  # 저장 후 상태 갱신

    def _confirm_discard(self) -> bool:
        """미저장 변경 경고. '무시하고 열기'면 True, '현재 창 유지'면 False."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("저장하지 않은 변경")
        box.setText("아래 비교 창에 저장하지 않은 편집이 있습니다.\n무시하고 다른 파일을 열까요?")
        discard = box.addButton("무시하고 열기", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("현재 창 유지", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is discard

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
