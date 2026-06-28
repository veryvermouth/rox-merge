"""side-by-side Diff 뷰 — 커스텀 페인팅 + 직접 편집 (PLAN §6.2, §3).

정렬(Row) 기반으로 좌/우를 같은 행에 그리고, gap은 빈 칸으로 채워 행을 맞춘다.
종류별 배경색 + 단어 단위 intraline 강조 + 현재 차이 강조 + 스크롤 동기화.
병합 버튼(→/←)과 직접 텍스트 편집(커서/키 입력)을 지원한다.

편집은 활성 쪽 Document.lines 를 직접 수정하고, 타이핑 묶음 단위로
``edit_committed`` 시그널을 내보내 상위(앱)에서 Undo 스택에 기록하게 한다.
편집 직후 ``edited`` 시그널로 상위가 debounce 재계산을 트리거한다.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea

from rox_merge.core.diff import KIND_EQUAL, DiffResult
from rox_merge.core.document import Document
from rox_merge.ui.theme import Theme

_GUTTER_PAD = 10
_TEXT_PAD = 6
_CENTER_W = 18
_BTN_W = 18
_MIN_FONT_PT = 6
_MAX_FONT_PT = 40

_BTN_BG = QColor(255, 255, 255)
_BTN_BORDER = QColor(150, 150, 150)
_BTN_TEXT = QColor(60, 60, 60)
_CARET = QColor(20, 20, 20)
_MOVE_LINE = QColor(150, 120, 210)


class DiffView(QAbstractScrollArea):
    """좌/우 문서 + DiffResult를 렌더링하고 직접 편집을 지원하는 위젯."""

    active_side_changed = Signal(str)        # "left" | "right"
    merge_requested = Signal(int, str)       # (hunk_id, "l2r" | "r2l")
    edited = Signal()                        # 편집 발생(디바운스 재계산 트리거)
    edit_committed = Signal(str, object, object)  # (side, old_lines, new_lines)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = Theme()
        self._left_doc = Document()
        self._right_doc = Document()
        self._result = DiffResult()
        self._current_hunk = -1
        self._active_side = "left"
        self._base_font_pt = 11
        self._read_only = False

        # 커서(활성 쪽 문서 기준): 라인/열
        self._cur_line = 0
        self._cur_col = 0
        # 편집 트랜잭션(타이핑 묶음) 스냅샷
        self._txn_side: str | None = None
        self._txn_old: list[str] | None = None

        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(self._base_font_pt)
        self.setFont(font)
        self._update_metrics()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setMouseTracking(True)

    # ------------------------------------------------------------------ data
    def set_data(self, left_doc: Document, right_doc: Document, result: DiffResult) -> None:
        self._left_doc = left_doc
        self._right_doc = right_doc
        self._result = result
        if self._current_hunk >= len(result.hunks):
            self._current_hunk = -1
        self._clamp_cursor()
        self._update_scrollbars()
        self.viewport().update()

    @property
    def result(self) -> DiffResult:
        return self._result

    @property
    def active_side(self) -> str:
        return self._active_side

    def _left(self) -> list[str]:
        return self._left_doc.lines

    def _right(self) -> list[str]:
        return self._right_doc.lines

    def _active_doc(self) -> Document:
        return self._left_doc if self._active_side == "left" else self._right_doc

    def _active_lines(self) -> list[str]:
        return self._active_doc().lines

    # --------------------------------------------------------------- metrics
    def _update_metrics(self) -> None:
        fm = QFontMetrics(self.font())
        self._row_h = fm.height()
        self._char_w = fm.horizontalAdvance("0")
        self._ascent = fm.ascent()
        self._fm = fm

    def _gutter_w(self) -> int:
        rows = max(len(self._left()), len(self._right()), 1)
        digits = len(str(rows))
        return digits * self._char_w + 2 * _GUTTER_PAD

    def _side_w(self) -> int:
        return max(0, (self.viewport().width() - _CENTER_W) // 2)

    def _visible_rows(self) -> int:
        return max(1, self.viewport().height() // self._row_h)

    def _content_width(self) -> int:
        longest = 0
        for s in self._left():
            longest = max(longest, len(s))
        for s in self._right():
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

    # ------------------------------------------------------------- font zoom
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

    # --------------------------------------------------------------- editing
    def set_read_only(self, value: bool) -> None:
        self._read_only = value

    def commit_edit(self) -> None:
        """진행 중인 타이핑 묶음을 마무리해 edit_committed로 내보낸다."""
        if self._txn_old is None:
            return
        doc = self._left_doc if self._txn_side == "left" else self._right_doc
        new = list(doc.lines)
        if new != self._txn_old:
            self.edit_committed.emit(self._txn_side, self._txn_old, new)
        self._txn_old = None
        self._txn_side = None

    def _begin_txn(self) -> None:
        if self._txn_old is None or self._txn_side != self._active_side:
            self.commit_edit()
            self._txn_side = self._active_side
            self._txn_old = list(self._active_doc().lines)

    def _after_edit(self) -> None:
        self.edited.emit()
        self._ensure_cursor_visible()
        self.viewport().update()

    def keyPressEvent(self, event):  # noqa: N802 (Qt)
        key = event.key()
        mods = event.modifiers()
        nav = {
            Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up,
            Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End,
        }
        if key in nav:
            self.commit_edit()
            self._move(key)
            self._ensure_cursor_visible()
            self.viewport().update()
            return
        if key == Qt.Key.Key_Backspace:
            self._backspace()
            return
        if key == Qt.Key.Key_Delete:
            self._delete()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._newline()
            return

        text = event.text()
        ctrl_alt = mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                           | Qt.KeyboardModifier.MetaModifier)
        if text and text.isprintable() and not ctrl_alt:
            self._insert(text)
            return
        super().keyPressEvent(event)

    def _insert(self, s: str) -> None:
        if self._read_only:
            return
        lines = self._active_lines()
        if not lines:
            lines.append("")
        self._cur_line = min(self._cur_line, len(lines) - 1)
        self._begin_txn()
        line = lines[self._cur_line]
        col = min(self._cur_col, len(line))
        lines[self._cur_line] = line[:col] + s + line[col:]
        self._cur_col = col + len(s)
        self._after_edit()

    def _backspace(self) -> None:
        if self._read_only:
            return
        lines = self._active_lines()
        if not lines:
            return
        self._cur_line = min(self._cur_line, len(lines) - 1)
        line = lines[self._cur_line]
        col = min(self._cur_col, len(line))
        if col > 0:
            self._begin_txn()
            lines[self._cur_line] = line[: col - 1] + line[col:]
            self._cur_col = col - 1
            self._after_edit()
        elif self._cur_line > 0:
            self._begin_txn()
            prev = lines[self._cur_line - 1]
            self._cur_col = len(prev)
            lines[self._cur_line - 1] = prev + line
            del lines[self._cur_line]
            self._cur_line -= 1
            self._after_edit()

    def _delete(self) -> None:
        if self._read_only:
            return
        lines = self._active_lines()
        if not lines:
            return
        self._cur_line = min(self._cur_line, len(lines) - 1)
        line = lines[self._cur_line]
        col = min(self._cur_col, len(line))
        if col < len(line):
            self._begin_txn()
            lines[self._cur_line] = line[:col] + line[col + 1 :]
            self._after_edit()
        elif self._cur_line < len(lines) - 1:
            self._begin_txn()
            lines[self._cur_line] = line + lines[self._cur_line + 1]
            del lines[self._cur_line + 1]
            self._after_edit()

    def _newline(self) -> None:
        if self._read_only:
            return
        lines = self._active_lines()
        if not lines:
            lines.append("")
        self._cur_line = min(self._cur_line, len(lines) - 1)
        self._begin_txn()
        line = lines[self._cur_line]
        col = min(self._cur_col, len(line))
        lines[self._cur_line] = line[:col]
        lines.insert(self._cur_line + 1, line[col:])
        self._cur_line += 1
        self._cur_col = 0
        self._after_edit()

    def _move(self, key) -> None:
        lines = self._active_lines()
        n = len(lines)
        if n == 0:
            self._cur_line = self._cur_col = 0
            return
        self._cur_line = min(self._cur_line, n - 1)
        cur_len = len(lines[self._cur_line])
        col = min(self._cur_col, cur_len)
        if key == Qt.Key.Key_Left:
            if col > 0:
                self._cur_col = col - 1
            elif self._cur_line > 0:
                self._cur_line -= 1
                self._cur_col = len(lines[self._cur_line])
        elif key == Qt.Key.Key_Right:
            if col < cur_len:
                self._cur_col = col + 1
            elif self._cur_line < n - 1:
                self._cur_line += 1
                self._cur_col = 0
        elif key == Qt.Key.Key_Up and self._cur_line > 0:
            self._cur_line -= 1
            self._cur_col = min(col, len(lines[self._cur_line]))
        elif key == Qt.Key.Key_Down and self._cur_line < n - 1:
            self._cur_line += 1
            self._cur_col = min(col, len(lines[self._cur_line]))
        elif key == Qt.Key.Key_Home:
            self._cur_col = 0
        elif key == Qt.Key.Key_End:
            self._cur_col = cur_len

    def _clamp_cursor(self) -> None:
        lines = self._active_lines()
        if not lines:
            self._cur_line = self._cur_col = 0
            return
        self._cur_line = min(self._cur_line, len(lines) - 1)
        self._cur_col = min(self._cur_col, len(lines[self._cur_line]))

    def _ensure_cursor_visible(self) -> None:
        row = self._cursor_row()
        if row is None:
            return
        first = self.verticalScrollBar().value()
        visible = self._visible_rows()
        if row < first:
            self.verticalScrollBar().setValue(row)
        elif row >= first + visible:
            self.verticalScrollBar().setValue(row - visible + 1)

    def _cursor_row(self) -> int | None:
        """활성 쪽 커서 라인이 위치한 정렬 행 인덱스(없으면 None)."""
        for i, row in enumerate(self._result.rows):
            idx = row.left_index if self._active_side == "left" else row.right_index
            if idx == self._cur_line:
                return i
        return None

    # ---------------------------------------------------------------- events
    def wheelEvent(self, event):  # noqa: N802 (Qt)
        delta = event.angleDelta().y()
        steps = -delta // 120 * 3
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + steps)

    def mousePressEvent(self, event):  # noqa: N802 (Qt)
        self.setFocus()
        pos = event.position()
        # 병합 버튼 먼저 히트 테스트
        for rect, hid, direction in self._button_rects():
            if rect.contains(int(pos.x()), int(pos.y())):
                self.merge_requested.emit(hid, direction)
                return

        self.commit_edit()
        side = "left" if pos.x() < self._side_w() + _CENTER_W / 2 else "right"
        if side != self._active_side:
            self._active_side = side
            self.active_side_changed.emit(side)
        self._place_cursor_at(pos.x(), pos.y(), side)
        self.viewport().update()

    def _place_cursor_at(self, x: float, y: float, side: str) -> None:
        first = self.verticalScrollBar().value()
        row_idx = first + int(y // self._row_h)
        rows = self._result.rows
        if not (0 <= row_idx < len(rows)):
            return
        line_index = rows[row_idx].left_index if side == "left" else rows[row_idx].right_index
        if line_index is None:
            return
        lines = self._left() if side == "left" else self._right()
        if line_index >= len(lines):
            return
        self._cur_line = line_index
        self._cur_col = self._col_at_x(lines[line_index], x, side)

    def _col_at_x(self, text: str, x: float, side: str) -> int:
        x0 = self._text_x0(side)
        hscroll = self.horizontalScrollBar().value()
        local = x - x0 + hscroll
        if local <= 0:
            return 0
        acc = 0
        for i, ch in enumerate(text):
            w = self._fm.horizontalAdvance(ch)
            if acc + w / 2 >= local:
                return i
            acc += w
        return len(text)

    def _text_x0(self, side: str) -> int:
        gutter_w = self._gutter_w()
        if side == "left":
            return gutter_w + _TEXT_PAD
        return self._side_w() + _CENTER_W + gutter_w + _TEXT_PAD

    def _button_rects(self) -> list[tuple[QRect, int, str]]:
        rects: list[tuple[QRect, int, str]] = []
        first = self.verticalScrollBar().value()
        last = first + self._visible_rows() + 1
        side_w = self._side_w()
        gutter_w = self._gutter_w()
        for h in self._result.hunks:
            if not (first <= h.row_start < last):
                continue
            y = (h.row_start - first) * self._row_h
            # 왼쪽 버튼: 왼쪽 텍스트 영역의 안쪽(가운데 쪽) 끝
            left_btn = QRect(side_w - _BTN_W, y, _BTN_W, self._row_h)
            # 오른쪽 버튼: 오른쪽 거터(줄 번호) 다음, 텍스트 영역 시작점 (줄 번호 가리지 않게)
            right_btn = QRect(side_w + _CENTER_W + gutter_w, y, _BTN_W, self._row_h)
            rects.append((left_btn, h.id, "l2r"))
            rects.append((right_btn, h.id, "r2l"))
        return rects

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

        painter.fillRect(QRect(0, 0, gutter_w, vp.height()), self.theme.gutter_bg)
        painter.fillRect(
            QRect(side_w + _CENTER_W, 0, gutter_w, vp.height()), self.theme.gutter_bg
        )
        painter.fillRect(QRect(side_w, 0, _CENTER_W, vp.height()), self.theme.divider)

        for vi in range(first, last):
            row = rows[vi]
            y = (vi - first) * self._row_h
            is_current = vi in current_rows
            self._paint_cell(
                painter, 0, side_w, gutter_w, y, hscroll,
                row.left_index, self._left(), row.kind, row.left_spans, is_current,
            )
            self._paint_cell(
                painter, side_w + _CENTER_W, side_w, gutter_w, y, hscroll,
                row.right_index, self._right(), row.kind, row.right_spans, is_current,
            )

        self._paint_move_connectors(painter, first, side_w)
        self._paint_caret(painter, first, hscroll)
        self._paint_buttons(painter)
        painter.end()

    def _paint_move_connectors(self, painter, first, side_w) -> None:
        moves = self._result.moves
        if not moves:
            return
        left_row: dict[int, int] = {}
        right_row: dict[int, int] = {}
        for i, r in enumerate(self._result.rows):
            if r.left_index is not None:
                left_row[r.left_index] = i
            if r.right_index is not None:
                right_row[r.right_index] = i

        visible_first = first
        visible_last = first + self._visible_rows() + 1
        painter.save()
        painter.setPen(QPen(_MOVE_LINE, 1))
        for mv in moves:
            lr = left_row.get(mv.left_range[0])
            rr = right_row.get(mv.right_range[0])
            if lr is None or rr is None:
                continue
            if not (visible_first <= lr < visible_last or visible_first <= rr < visible_last):
                continue
            ly = (lr - first) * self._row_h + self._row_h // 2
            ry = (rr - first) * self._row_h + self._row_h // 2
            painter.drawLine(side_w, ly, side_w + _CENTER_W, ry)
        painter.restore()

    def _paint_cell(self, painter, x0, side_w, gutter_w, y, hscroll,
                    line_index, lines, kind, spans, is_current):
        row_h = self._row_h
        text_x0 = x0 + gutter_w + _TEXT_PAD
        text_area_x = x0 + gutter_w
        text_area_w = side_w - gutter_w

        if line_index is None or line_index >= len(lines):
            painter.fillRect(QRect(text_area_x, y, text_area_w, row_h), self.theme.gap_fill)
            return

        text = lines[line_index]

        bg = None if kind == KIND_EQUAL else self.theme.line_bg(kind)
        if bg is not None:
            painter.fillRect(QRect(text_area_x, y, text_area_w, row_h), bg)

        intra = self.theme.intraline_bg(kind)
        if intra is not None:
            for sp in spans:
                sx = text_x0 - hscroll + self._fm.horizontalAdvance(text[: sp.start])
                sw = self._fm.horizontalAdvance(text[sp.start : sp.end])
                painter.fillRect(QRect(int(sx), y, int(sw), row_h), intra)

        if is_current:
            painter.fillRect(QRect(x0, y, 3, row_h), self.theme.current_accent)

        painter.setPen(self.theme.gutter_text)
        painter.drawText(
            QRect(x0, y, gutter_w - _GUTTER_PAD, row_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(line_index + 1),
        )

        painter.save()
        painter.setClipRect(QRect(text_area_x, y, text_area_w, row_h))
        painter.setPen(self.theme.text)
        painter.drawText(int(text_x0 - hscroll), y + self._ascent, text)
        painter.restore()

    def _paint_caret(self, painter, first, hscroll) -> None:
        if not self.hasFocus():
            return
        row = self._cursor_row()
        if row is None or not (first <= row < first + self._visible_rows() + 1):
            return
        lines = self._active_lines()
        if self._cur_line >= len(lines):
            return
        text = lines[self._cur_line]
        col = min(self._cur_col, len(text))
        x0 = self._text_x0(self._active_side)
        cx = int(x0 - hscroll + self._fm.horizontalAdvance(text[:col]))
        y = (row - first) * self._row_h
        painter.fillRect(QRect(cx, y, 2, self._row_h), _CARET)

    def _paint_buttons(self, painter) -> None:
        painter.save()
        for rect, _hid, direction in self._button_rects():
            painter.fillRect(rect, _BTN_BG)
            painter.setPen(_BTN_BORDER)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setPen(_BTN_TEXT)
            arrow = "→" if direction == "l2r" else "←"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, arrow)
        painter.restore()

    def _current_hunk_row_set(self) -> set[int]:
        if not (0 <= self._current_hunk < len(self._result.hunks)):
            return set()
        h = self._result.hunks[self._current_hunk]
        return set(range(h.row_start, h.row_end))
