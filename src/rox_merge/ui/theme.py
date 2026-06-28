"""색상 테마 토큰 (PLAN §6.3). 라이트 테마 기준.

종류별 라인 배경색 + intraline(단어) 강조색을 분리해 둔다.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from rox_merge.core.diff import (
    KIND_CHANGE,
    KIND_DELETE,
    KIND_INSERT,
    KIND_MOVED,
    KIND_WHITESPACE,
)


class Theme:
    """라이트 테마 색상. (QColor는 mutable이라 dataclass 대신 일반 클래스 사용.)"""

    def __init__(self) -> None:
        self.background = QColor(255, 255, 255)
        self.text = QColor(30, 30, 30)
        self.gutter_bg = QColor(245, 245, 245)
        self.gutter_text = QColor(150, 150, 150)
        self.divider = QColor(200, 200, 200)
        self.gap_fill = QColor(247, 247, 247)
        self.current_accent = QColor(0, 120, 215)

    def line_bg(self, kind: str) -> QColor | None:
        """라인 배경색(블록 종류). equal/None이면 배경 없음."""
        return _LINE_BG.get(kind)

    def intraline_bg(self, kind: str) -> QColor | None:
        """라인 내 단어 강조색."""
        return _INTRALINE_BG.get(kind)


_LINE_BG = {
    KIND_INSERT: QColor(218, 251, 225),      # 초록 계열
    KIND_DELETE: QColor(255, 228, 228),      # 빨강 계열
    KIND_CHANGE: QColor(255, 249, 196),      # 노랑 계열
    KIND_WHITESPACE: QColor(236, 240, 245),  # 옅은 색 (약한 강조)
    KIND_MOVED: QColor(233, 222, 252),       # 보라 계열 (Phase 4)
}

_INTRALINE_BG = {
    KIND_INSERT: QColor(150, 235, 170),
    KIND_DELETE: QColor(245, 170, 170),
    KIND_CHANGE: QColor(255, 224, 130),
}
