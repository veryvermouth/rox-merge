"""색상 테마 토큰 (PLAN §6.3). 라이트/다크 지원.

종류별 라인 배경색 + intraline(단어) 강조색 + 버튼/캐럿/연결선 색을 담는다.
``Theme(dark=True/False)`` 로 팔레트를 고른다. 창 크롬(툴바 등)용 QPalette는
:func:`dark_palette` 로 제공.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from rox_merge.core.diff import (
    KIND_CHANGE,
    KIND_DELETE,
    KIND_INSERT,
    KIND_MOVED,
    KIND_WHITESPACE,
)


class Theme:
    """라이트/다크 테마 색상. (QColor는 mutable이라 dataclass 대신 일반 클래스.)"""

    def __init__(self, dark: bool = False) -> None:
        self.dark = dark
        if dark:
            self.background = QColor(30, 30, 30)
            self.text = QColor(220, 220, 220)
            self.gutter_bg = QColor(40, 40, 40)
            self.gutter_text = QColor(120, 120, 120)
            self.divider = QColor(70, 70, 70)
            self.gap_fill = QColor(38, 38, 38)
            self.current_accent = QColor(80, 160, 255)
            self.btn_bg = QColor(55, 55, 55)
            self.btn_border = QColor(110, 110, 110)
            self.btn_text = QColor(210, 210, 210)
            self.caret = QColor(230, 230, 230)
            self.move_line = QColor(160, 130, 220)
            self.selection = QColor(70, 120, 180, 110)
            self._line_bg = {
                KIND_INSERT: QColor(28, 58, 40),
                KIND_DELETE: QColor(70, 35, 38),
                KIND_CHANGE: QColor(70, 64, 30),
                KIND_WHITESPACE: QColor(44, 50, 58),
                KIND_MOVED: QColor(56, 46, 78),
            }
            self._intraline_bg = {
                KIND_INSERT: QColor(45, 110, 70),
                KIND_DELETE: QColor(130, 62, 62),
                KIND_CHANGE: QColor(120, 105, 45),
            }
        else:
            self.background = QColor(255, 255, 255)
            self.text = QColor(30, 30, 30)
            self.gutter_bg = QColor(245, 245, 245)
            self.gutter_text = QColor(150, 150, 150)
            self.divider = QColor(200, 200, 200)
            self.gap_fill = QColor(247, 247, 247)
            self.current_accent = QColor(0, 120, 215)
            self.btn_bg = QColor(255, 255, 255)
            self.btn_border = QColor(150, 150, 150)
            self.btn_text = QColor(60, 60, 60)
            self.caret = QColor(20, 20, 20)
            self.move_line = QColor(150, 120, 210)
            self.selection = QColor(51, 153, 255, 80)
            # Araxis Merge 라이트 테마 계열: 변경=따뜻한 크림, 추가=연한 초록,
            # 삭제=연한 분홍, 이동=연한 보라.
            self._line_bg = {
                KIND_INSERT: QColor(217, 240, 217),      # 추가(연한 초록)
                KIND_DELETE: QColor(250, 223, 223),      # 삭제(연한 분홍)
                KIND_CHANGE: QColor(252, 242, 224),      # 변경(따뜻한 크림)
                KIND_WHITESPACE: QColor(236, 240, 245),  # 공백만(옅은 회색)
                KIND_MOVED: QColor(233, 224, 250),       # 이동(연한 보라)
            }
            self._intraline_bg = {
                KIND_INSERT: QColor(168, 216, 168),      # 추가 단어(진한 초록)
                KIND_DELETE: QColor(240, 178, 178),      # 삭제 단어(진한 분홍)
                KIND_CHANGE: QColor(246, 221, 165),      # 변경 단어(골든 탄)
            }

    def line_bg(self, kind: str) -> QColor | None:
        """라인 배경색(블록 종류). equal/None이면 배경 없음."""
        return self._line_bg.get(kind)

    def intraline_bg(self, kind: str) -> QColor | None:
        """라인 내 단어 강조색."""
        return self._intraline_bg.get(kind)


def dark_palette() -> QPalette:
    """창 크롬(툴바/트리/상태바 등)용 다크 QPalette."""
    p = QPalette()
    window = QColor(45, 45, 45)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, window)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, window)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Highlight, QColor(70, 130, 200))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(120, 120, 120)
    )
    return p
