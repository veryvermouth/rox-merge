"""Document 데이터 모델 (PLAN §5).

순수 데이터 + 줄바꿈 상수. 파일 I/O는 ``rox_merge.fileio`` 가 담당한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

#: 지원하는 줄바꿈 종류.
LineEnding = Literal["LF", "CRLF", "CR"]

#: 줄바꿈 이름 → 실제 문자 매핑.
LINE_ENDING_CHARS: dict[LineEnding, str] = {
    "LF": "\n",
    "CRLF": "\r\n",
    "CR": "\r",
}

#: 새 버퍼의 기본 줄바꿈. 플랫폼 native (Windows=CRLF, 그 외=LF).
DEFAULT_LINE_ENDING: LineEnding = "CRLF" if os.linesep == "\r\n" else "LF"


@dataclass
class Document:
    """편집기 한쪽(좌 또는 우)의 문서 상태.

    Attributes:
        path: 파일 경로. ``None`` 이면 빈 새 버퍼.
        encoding: 읽기/쓰기에 사용할 인코딩 이름 (예: ``utf-8``, ``utf-8-sig``).
        line_ending: 저장 시 사용할 줄바꿈 종류.
        lines: 줄바꿈 문자를 **포함하지 않는** 라인 목록.
        dirty: 미저장 변경 여부.
        final_newline: 파일이 줄바꿈으로 끝나는지(라운드트립 보존용).
        mixed_line_endings: 원본에 줄바꿈이 혼합돼 있었는지(표시/정규화 안내용).
    """

    path: str | None = None
    encoding: str = "utf-8"
    line_ending: LineEnding = DEFAULT_LINE_ENDING
    lines: list[str] = field(default_factory=list)
    dirty: bool = False
    final_newline: bool = False
    mixed_line_endings: bool = False

    @property
    def is_empty(self) -> bool:
        """내용이 비었는지. diff 계산 선행 조건(PLAN §4.6) 판정에 사용.

        빈 버퍼(``[]``)와 빈 한 줄(``[""]``)을 모두 '비어 있음'으로 본다.
        """
        return not self.lines or self.lines == [""]
