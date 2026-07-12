"""폴더 비교 패널 (PLAN §6.4) — 탭에 들어가는 QWidget.

위: 좌/우 대응 트리, 아래(분할 모드) 또는 내부 탭(새 탭 모드)에 파일 diff.
툴바/메뉴는 상위 AppWindow가 제공하며, 이 패널의 공개 메서드를 호출한다.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QPainter, QPalette, QPolygon, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QMessageBox,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
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
from rox_merge.ui.theme import Theme

_STATUS_COLOR = {
    SAME: QColor(120, 120, 120),
    DIFFERENT: QColor(180, 120, 0),
    LEFT_ONLY: QColor(200, 60, 60),
    RIGHT_ONLY: QColor(40, 150, 60),
}
_ROLE_NODE = Qt.ItemDataRole.UserRole


class _RightIndentDelegate(QStyledItemDelegate):
    """오른쪽 열(1열)을 트리 depth만큼 들여써서 왼쪽 트리와 정렬을 맞춘다."""

    def __init__(self, tree: QTreeWidget):
        super().__init__(tree)
        self._tree = tree

    def paint(self, painter, option, index):  # noqa: N802 (Qt)
        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        ind = self._tree.indentation()
        indent = (depth + 1) * ind

        # 이름을 depth만큼 들여써서 그림
        opt = QStyleOptionViewItem(option)
        opt.rect = option.rect.adjusted(indent, 0, 0, 0)
        super().paint(painter, opt, index)

        # 폴더(자식 있는 항목)면 이름 왼쪽에 펼침/접힘 삼각형을 직접 그림
        # (스타일의 PE_IndicatorBranch는 이 문맥에서 안 그려져 직접 그린다)
        item = self._tree.itemFromIndex(index)
        if item is not None and item.childCount() > 0:
            arect = QRect(
                option.rect.left() + indent - ind, option.rect.top(),
                ind, option.rect.height(),
            )
            cx, cy = arect.center().x(), arect.center().y()
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(option.palette.color(QPalette.ColorRole.WindowText))
            if item.isExpanded():  # ▾
                painter.drawPolygon(QPolygon([QPoint(cx - 4, cy - 2), QPoint(cx + 4, cy - 2), QPoint(cx, cy + 3)]))
            else:  # ▸
                painter.drawPolygon(QPolygon([QPoint(cx - 2, cy - 4), QPoint(cx - 2, cy + 4), QPoint(cx + 3, cy)]))
            painter.restore()


class FolderComparePane(QWidget):
    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._left_root: Path | None = None
        self._right_root: Path | None = None
        self._mode = MODE_FAST
        self._diff_only = False
        self._tab_mode = False
        self._tab_controllers: dict[object, DiffController] = {}  # DiffView -> DiffController
        self._theme = Theme(dark=False)
        self._font_pt = 11

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["왼쪽", "오른쪽"])
        self._tree.setColumnCount(2)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.setItemDelegateForColumn(1, _RightIndentDelegate(self._tree))
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tabs, 1)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._on_escape)

    # ---------------------------------------------------- AppWindow 공개 API
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._diff.set_theme(theme)
        for view in self._tab_controllers:
            view.set_theme(theme)

    def apply_font(self, pt: int) -> None:
        self._font_pt = pt
        self._diff.set_font_point_size(pt)
        for view in self._tab_controllers:
            view.set_font_point_size(pt)
        # 폴더 트리 글꼴도 함께 조절
        f = self._tree.font()
        f.setPointSize(pt)
        self._tree.setFont(f)

    def controller(self) -> DiffController:
        return self._active_controller()

    def open_side(self, side: str) -> None:
        self._pick_root(side)

    def save(self, as_new: bool = False) -> None:
        self._save_active()

    def refresh(self) -> None:
        self._refresh()

    def expand_all(self) -> None:
        self._tree.expandAll()

    def collapse_all(self) -> None:
        self._tree.collapseAll()

    def reset_expand(self) -> None:
        self._expand_differences()

    def toggle_filter(self, on: bool) -> None:
        self._toggle_filter(on)

    def toggle_exact(self, on: bool) -> None:
        self._toggle_mode(on)

    def toggle_tab_mode(self, on: bool) -> None:
        self._toggle_tab_mode(on)

    def is_filter(self) -> bool:
        return self._diff_only

    def is_exact(self) -> bool:
        return self._mode == MODE_EXACT

    def is_tab_mode(self) -> bool:
        return self._tab_mode

    def set_roots(self, left: str | Path, right: str | Path) -> None:
        self._left_root = Path(left)
        self._right_root = Path(right)
        self._refresh()

    def prompt_roots(self) -> None:
        left = QFileDialog.getExistingDirectory(self.window(), "왼쪽 폴더 선택")
        if not left:
            return
        right = QFileDialog.getExistingDirectory(self.window(), "오른쪽 폴더 선택")
        if not right:
            return
        self.set_roots(left, right)

    def title(self) -> str:
        if self._left_root and self._right_root:
            return f"폴더: {self._left_root.name} ⇄ {self._right_root.name}"
        return "폴더 비교"

    # --------------------------------------------------------------- slots
    def _pick_root(self, side: str) -> None:
        path = QFileDialog.getExistingDirectory(self.window(), f"{side} 폴더 선택")
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
        self.title_changed.emit(self.title())

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
        view.set_theme(self._theme)
        view.set_font_point_size(self._font_pt)
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
            path, _ = QFileDialog.getSaveFileName(self.window(), f"{side} 저장")
            if not path:
                return
        try:
            write_document(doc, path)
        except OSError as exc:
            QMessageBox.critical(self.window(), "저장 실패", str(exc))
            return
        self._refresh()

    def _on_escape(self) -> None:
        if self._tabs.currentIndex() != 0:
            self._tabs.setCurrentIndex(0)
        else:
            self._hide_diff()

    def _confirm_discard(self) -> bool:
        box = QMessageBox(self.window())
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
            QMessageBox.information(self.window(), "바이너리 파일", f"바이너리 파일 - 비교 불가:\n{path}")
            return None
        except OSError as exc:
            QMessageBox.warning(self.window(), "열기 실패", str(exc))
            return None
