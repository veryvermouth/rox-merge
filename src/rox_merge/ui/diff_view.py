"""side-by-side Diff 뷰 — 커스텀 페인팅 (PLAN §6.2).

정렬(Row) 기반으로 좌/우를 같은 행에 그리고, gap은 빈 칸으로 채워 행을 맞춘다.
종류별 배경색 + 단어 단위 intraline 강조 + 현재 차이 강조 + 스크롤 동기화.

Phase 2는 뷰어(읽기 전용). 직접 편집/병합은 Phase 3에서 추가.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QAbstractScrollArea

from rox_merge.core.diff import KIND_EQUAL, DiffResult
from rox_merge.ui.theme import Theme

_GUTTER_PAD = 10
_TEXT_PAD = 6
_CENTER_W = 14
_MIN_FONT_PT = 6
_MAX_FONT_PT = 40


class DiffView(QAbstractScrollArea):
    """좌/우 라인 목록 + DiffResult를 받아 정렬 렌더링하는 뷰어."""

    active_side_changed = Signal(str)  # "left" | "right"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = Theme()
        self._left: list[str] = []
        self._right: list[str] = []
        self._result = DiffResult()
        self._current_hunk = -1
        self._active_side = "left"
        self._base_font_pt = 11

        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(self._base_font_pt)
        self.setFont(font)
        self._update_metrics()

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setMouseTracking(True)

    # ------------------------------------------------------------------ data
    def set_data(self, left: list[str], right: list[str], result: DiffResult) -> None:
        self._left = left
        self._right = right
        self._result = result
        if self._current_hunk >= len(result.hunks):
            self._current_hunk = -1
        self._update_scrollbars()
        self.viewport().update()

    @property
    def result(self) -> DiffResult:
        return self._result

    @property
    def active_side(self) -> str:
        return self._active_side

    # --------------------------------------------------------------- metrics
    def _update_metrics(self) -> None:
        fm = QFontMetrics(self.font())
        self._row_h = fm.height()
        self._char_w = fm.horizontalAdvance("0")  # 모노스페이스 가정
        self._ascent = fm.ascent()
        self._fm = fm

    def _gutter_w(self) -> int:
        rows = max(len(self._left), len(self._right), 1)
        digits = len(str(rows))
        return digits * self._char_w + 2 * _GUTTER_PAD

    def _side_w(self) -> int:
        return max(0, (self.viewport().width() - _CENTER_W) // 2)

    def _visible_rows(self) -> int:
        return max(1, self.viewport().height() // self._row_h)

    def _content_width(self) -> int:
        longest = 0
        for s in self._left:
            longest = max(longest, len(s))
        for s in self._right:
            longest = max(longest, len(s))
        return longest * self._char_w + 2 * _TEXT_PAD

    # ------------------------------------------------------------ scrollbars
    def _update_scrollbars(self) -> None:
        total = len(self._result.rows)
        vbar = self.verticalScrollBar()
        vbar.setRange(0, max(0, total - self._visible_rows()))
        vbar.setPageStep(self._visible_rows())
        vbar.setSingleStep(1)

        text_area = self._side_w() - self._gutter_w()
        hbar = self.horizontalScrollBar()
        hbar.setRange(0, max(0, self._content_width() - max(1, text_area)))
        hbar.setPageStep(max(1, text_area))
        hbar.setSingleStep(self._char_w)

    def resizeEvent(self, event):  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._update_scrollbars()

    def scrollContentsBy(self, dx, dy):  # noqa: N802 (Qt)
        self.viewport().update()

    # ------------------------------------------------------------ navigation
    def set_current_hunk(self, idx: int) -> None:
        self._current_hunk = idx
        if 0 <= idx < len(self._result.hunks):
            self._scroll_row_into_center(self._result.hunks[idx].row_start)
        self.viewport().update()

    @property
    def current_hunk(self) -> int:
        return self._current_hunk

    def _scroll_row_into_center(self, row: int) -> None:
        target = max(0, row - self._visible_rows() // 2)
        self.verticalScrollBar().setValue(target)

    # ---------------------------------------------------------------- events
    def wheelEvent(self, event):  # noqa: N802 (Qt)
        delta = event.angleDelta().y()
        steps = -delta // 120 * 3
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + steps)

    def mousePressEvent(self, event):  # noqa: N802 (Qt)
        x = event.position().x()
        side = "left" if x < self._side_w() + _CENTER_W / 2 else "right"
        if side != self._active_side:
            self._active_side = side
            self.active_side_changed.emit(side)
            self.viewport().update()

    def set_font_point_size(self, pt: int) -> None:
        pt = max(_MIN_FONT_PT, min(_MAX_FONT_PT, pt))
        font = self.font()
        font.setPointSize(pt)
        self.setFont(font)
        self._update_metrics()
        self._update_scrollbars()
        self.viewport().update()

    def font_point_size(self) -> int:
        return self.font().pointSize()

    def base_font_point_size(self) -> int:
        return self._base_font_pt

    # --------------------------------------------------------------- painting
    def paintEvent(self, event):  # noqa: N802 (Qt)
        painter = QPainter(self.viewport())
        painter.setFont(self.font())
        vp = self.viewport().rect()
        painter.fillRect(vp, self.theme.background)

        rows = self._result.rows
        first = self.verticalScrollBar().value()
        last = min(len(rows), first + self._visible_rows() + 1)
        hscroll = self.horizontalScrollBar().value()

        side_w = self._side_w()
        gutter_w = self._gutter_w()
        current_rows = self._current_hunk_row_set()

        # 거터 배경 + 가운데 구분선
        painter.fillRect(QRect(0, 0, gutter_w, vp.height()), self.theme.gutter_bg)
        painter.fillRect(
            QRect(side_w + _CENTER_W, 0, gutter_w, vp.height()), self.theme.gutter_bg
        )
        painter.fillRect(
            QRect(side_w, 0, _CENTER_W, vp.height()), self.theme.divider
        )

        for vi in range(first, last):
            row = rows[vi]
            y = (vi - first) * self._row_h
            is_current = vi in current_rows
            self._paint_cell(
                painter, 0, side_w, gutter_w, y, hscroll,
                row.left_index, self._left, row.kind, row.left_spans, is_current,
            )
            self._paint_cell(
                painter, side_w + _CENTER_W, side_w, gutter_w, y, hscroll,
                row.right_index, self._right, row.kind, row.right_spans, is_current,
            )
        painter.end()

    def _paint_cell(self, painter, x0, side_w, gutter_w, y, hscroll,
                    line_index, lines, kind, spans, is_current):
        row_h = self._row_h
        text_x0 = x0 + gutter_w + _TEXT_PAD
        text_area_x = x0 + gutter_w
        text_area_w = side_w - gutter_w

        if line_index is None:
            # gap: 빈 칸 채우기
            painter.fillRect(QRect(text_area_x, y, text_area_w, row_h), self.theme.gap_fill)
            return

        # 라인 배경색
        bg = None if kind == KIND_EQUAL else self.theme.line_bg(kind)
        if bg is not None:
            painter.fillRect(QRect(text_area_x, y, text_area_w, row_h), bg)

        # intraline 강조
        intra = self.theme.intraline_bg(kind)
        if intra is not None:
            for sp in spans:
                sx = text_x0 - hscroll + sp.start * self._char_w
                sw = (sp.end - sp.start) * self._char_w
                painter.fillRect(QRect(int(sx), y, int(sw), row_h), intra)

        # 현재 차이 강조 액센트
        if is_current:
            painter.fillRect(QRect(x0, y, 3, row_h), self.theme.current_accent)

        # 라인 번호
        painter.setPen(self.theme.gutter_text)
        num = str(line_index + 1)
        painter.drawText(
            QRect(x0, y, gutter_w - _GUTTER_PAD, row_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            num,
        )

        # 본문 텍스트 (거터로 넘치지 않게 클립)
        painter.save()
        painter.setClipRect(QRect(text_area_x, y, text_area_w, row_h))
        painter.setPen(self.theme.text)
        painter.drawText(int(text_x0 - hscroll), y + self._ascent, lines[line_index])
        painter.restore()

    def _current_hunk_row_set(self) -> set[int]:
        if not (0 <= self._current_hunk < len(self._result.hunks)):
            return set()
        h = self._result.hunks[self._current_hunk]
        return set(range(h.row_start, h.row_end))
