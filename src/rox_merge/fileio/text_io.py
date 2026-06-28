"""텍스트 파일 I/O: 인코딩 감지, 줄바꿈 감지/보존, 바이너리 감지 (PLAN §7).

설계 원칙:
- 저장 시 원본 인코딩·줄바꿈을 보존한다(사용자가 바꾸지 않는 한).
- 라인은 줄바꿈 문자를 제외하고 저장하며, ``final_newline`` 으로 마지막 줄바꿈
  유무를 따로 보존해 라운드트립(읽기→쓰기) 시 바이트가 보존되도록 한다.
"""

from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from rox_merge.core.document import (
    DEFAULT_LINE_ENDING,
    LINE_ENDING_CHARS,
    Document,
    LineEnding,
)

# 바이너리 판별 시 검사할 선두 바이트 수.
_BINARY_SCAN_BYTES = 8192

# 알려진 텍스트 BOM (이 BOM으로 시작하면 NUL이 있어도 텍스트로 간주).
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"
_TEXT_BOMS = (_UTF8_BOM, _UTF16_LE_BOM, _UTF16_BE_BOM)


class BinaryFileError(Exception):
    """바이너리로 판별돼 텍스트 비교를 거부할 때 발생 (PLAN §7)."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        super().__init__(f"바이너리 파일 - 비교 불가: {self.path}")


def is_binary(data: bytes) -> bool:
    """선두 바이트에 NUL이 있으면 바이너리로 본다.

    UTF-16/UTF-8 등 알려진 BOM으로 시작하면(ASCII 문자가 NUL을 포함하는
    UTF-16이라도) 텍스트로 간주한다.
    """
    if data.startswith(_TEXT_BOMS):
        return False
    return b"\x00" in data[:_BINARY_SCAN_BYTES]


def detect_encoding(data: bytes) -> str:
    """바이트로부터 인코딩 이름을 추정한다.

    BOM 우선(결정적), 없으면 charset-normalizer로 추정, 실패 시 utf-8.
    순수 ASCII는 utf-8로 취급해(비ASCII 편집 후 저장 시) 인코딩 오류를 피한다.
    """
    if data.startswith(_UTF8_BOM):
        return "utf-8-sig"
    if data.startswith((_UTF16_LE_BOM, _UTF16_BE_BOM)):
        return "utf-16"

    best = from_bytes(data).best()
    if best is None:
        return "utf-8"
    # charset-normalizer는 'utf_8'처럼 언더스코어 이름을 줄 수 있어 정규화한다.
    encoding = (best.encoding or "utf-8").lower().replace("_", "-")
    if encoding == "ascii":
        return "utf-8"
    return encoding


def detect_line_ending(text: str) -> tuple[LineEnding, bool]:
    """줄바꿈 종류를 추정한다. 반환: (대표 줄바꿈, 혼합 여부).

    줄바꿈이 전혀 없으면 (기본 줄바꿈, False).
    """
    crlf = text.count("\r\n")
    cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf

    counts: dict[LineEnding, int] = {"CRLF": crlf, "CR": cr, "LF": lf}
    present = [name for name, n in counts.items() if n > 0]
    if not present:
        return DEFAULT_LINE_ENDING, False

    mixed = len(present) > 1
    predominant = max(counts, key=lambda k: counts[k])
    return predominant, mixed


def split_lines(text: str) -> tuple[list[str], bool]:
    """텍스트를 줄바꿈 제외 라인 목록으로 분할한다.

    반환: (lines, final_newline). ``final_newline`` 은 텍스트가 줄바꿈으로
    끝나는지 여부로, 라운드트립 보존에 쓰인다. 빈 문자열은 ([], False).
    """
    if text == "":
        return [], False

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    final_newline = normalized.endswith("\n")
    parts = normalized.split("\n")
    if final_newline:
        parts = parts[:-1]  # 마지막 줄바꿈 뒤의 빈 조각 제거
    return parts, final_newline


def join_lines(lines: list[str], line_ending: LineEnding, final_newline: bool) -> str:
    """라인 목록을 지정 줄바꿈으로 결합한다. ``split_lines`` 의 역연산."""
    if not lines:
        return ""
    eol = LINE_ENDING_CHARS[line_ending]
    text = eol.join(lines)
    if final_newline:
        text += eol
    return text


def read_document(path: str | Path) -> Document:
    """경로에서 문서를 읽어 :class:`Document` 로 반환한다.

    Raises:
        BinaryFileError: 바이너리로 판별된 경우.
    """
    path = Path(path)
    raw = path.read_bytes()
    if is_binary(raw):
        raise BinaryFileError(path)

    encoding = detect_encoding(raw)
    text = raw.decode(encoding)
    line_ending, mixed = detect_line_ending(text)
    lines, final_newline = split_lines(text)

    return Document(
        path=str(path),
        encoding=encoding,
        line_ending=line_ending,
        lines=lines,
        dirty=False,
        final_newline=final_newline,
        mixed_line_endings=mixed,
    )


def write_document(doc: Document, path: str | Path | None = None) -> None:
    """문서를 저장한다. 원본 인코딩·줄바꿈을 보존한다.

    ``path`` 를 주면 그 경로에 저장(다른 이름으로 저장)하고 ``doc.path`` 를 갱신한다.
    저장 성공 시 ``dirty`` 를 해제한다.

    Raises:
        ValueError: 저장 경로가 없고 ``doc.path`` 도 ``None`` 인 경우.
    """
    target = Path(path) if path is not None else (
        Path(doc.path) if doc.path is not None else None
    )
    if target is None:
        raise ValueError("저장 경로가 필요합니다 (path=None, doc.path=None).")

    text = join_lines(doc.lines, doc.line_ending, doc.final_newline)
    target.write_bytes(text.encode(doc.encoding))

    doc.path = str(target)
    doc.dirty = False


def new_document() -> Document:
    """빈 새 버퍼 문서를 만든다 (PLAN §6.5)."""
    return Document(
        path=None,
        encoding="utf-8",
        line_ending=DEFAULT_LINE_ENDING,
        lines=[],
        dirty=False,
        final_newline=False,
        mixed_line_endings=False,
    )
