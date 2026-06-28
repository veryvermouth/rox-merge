"""파일 I/O 계층 — 인코딩·줄바꿈·바이너리 감지, 문서 읽기/쓰기 (PLAN §7).

순수 Python. Qt에 의존하지 않는다.
"""

from rox_merge.fileio.text_io import (
    BinaryFileError,
    detect_encoding,
    detect_line_ending,
    is_binary,
    join_lines,
    new_document,
    read_document,
    split_lines,
    write_document,
)

__all__ = [
    "BinaryFileError",
    "is_binary",
    "detect_encoding",
    "detect_line_ending",
    "split_lines",
    "join_lines",
    "read_document",
    "write_document",
    "new_document",
]
