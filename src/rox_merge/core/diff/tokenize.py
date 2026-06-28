"""라인 토크나이저 — 단어 단위 2차 diff용 (PLAN §4.2).

언어 무관 기본 규칙: 공백 / 식별자(\\w+) / 기호(단일 문자) 단위로 쪼갠다.
공백 토큰도 보존해 위치 계산을 정확히 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 공백 런 | 단어(영숫자+밑줄, 유니코드 포함) | 그 외 단일 기호
_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Token:
    text: str
    start: int  # 라인 내 시작 오프셋
    end: int    # 끝 오프셋(exclusive)


def tokenize(line: str) -> list[Token]:
    """라인을 토큰 목록으로 분해한다(공백 토큰 포함)."""
    return [Token(mo.group(), mo.start(), mo.end()) for mo in _TOKEN_RE.finditer(line)]
