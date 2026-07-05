"""미니맵 / 오버뷰 바 (PLAN §6.2).

전체 파일 대비 변경 위치를 색상으로 축소 표시하고, 클릭하면 해당 위치로 점프.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from rox_merge.core.diff import KIND_EQUAL, DiffResult
from rox_merge.ui.theme import Theme

_WIDTH = 14


class OverviewBar(QWidget):
    """클릭 시 row 인덱스를 emit 하는 세로 미니맵."""

    row_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = Theme()
        self._result = DiffResult()
        self.setFixedWidth(_WIDTH)

    def set_result(self, result: DiffResult) -> None:
        self._result = result
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def _total_rows(self) -> int:
        return max(1, len(self._result.rows))

    def paintEvent(self, event):  # noqa: N802 (Qt)
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.theme.gutter_bg)

        total = self._total_rows()
        h = self.height()
        for i, row in enumerate(self._result.rows):
            if row.kind == KIND_EQUAL:
                continue
            bg = self.theme.line_bg(row.kind)
            if bg is None:
                continue
            y = int(i / total * h)
            band = max(2, int(h / total))
            painter.fillRect(QRect(2, y, _WIDTH - 4, band), bg)
        painter.end()

    def mousePressEvent(self, event):  # noqa: N802 (Qt)
        total = self._total_rows()
        row = int(event.position().y() / max(1, self.height()) * total)
        self.row_clicked.emit(max(0, min(total - 1, row)))
