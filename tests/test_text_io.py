"""파일 I/O(인코딩·줄바꿈·바이너리 감지, 읽기/쓰기) 단위 테스트."""

import pytest

from rox_merge.core.document import DEFAULT_LINE_ENDING
from rox_merge.fileio import (
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

# ---------------------------------------------------------------------------
# 바이너리 감지
# ---------------------------------------------------------------------------


def test_is_binary_detects_nul():
    assert is_binary(b"hello\x00world") is True


def test_is_binary_plain_text():
    assert is_binary(b"hello world\n") is False


def test_is_binary_utf16_with_bom_is_text():
    # UTF-16 LE는 ASCII 문자마다 NUL을 포함하지만 BOM이 있으면 텍스트.
    data = "hello".encode("utf-16")  # BOM 포함
    assert b"\x00" in data
    assert is_binary(data) is False


# ---------------------------------------------------------------------------
# 인코딩 감지
# ---------------------------------------------------------------------------


def test_detect_encoding_ascii_treated_as_utf8():
    assert detect_encoding(b"plain ascii text") == "utf-8"


def test_detect_encoding_utf8_bom():
    assert detect_encoding(b"\xef\xbb\xbfhello") == "utf-8-sig"


def test_detect_encoding_utf16():
    assert detect_encoding("안녕".encode("utf-16")) == "utf-16"


def test_detect_encoding_utf8_korean():
    assert detect_encoding("안녕하세요 세계".encode("utf-8")) == "utf-8"


# ---------------------------------------------------------------------------
# 줄바꿈 감지
# ---------------------------------------------------------------------------


def test_detect_line_ending_lf():
    assert detect_line_ending("a\nb\nc\n") == ("LF", False)


def test_detect_line_ending_crlf():
    assert detect_line_ending("a\r\nb\r\n") == ("CRLF", False)


def test_detect_line_ending_cr():
    assert detect_line_ending("a\rb\rc") == ("CR", False)


def test_detect_line_ending_mixed():
    ending, mixed = detect_line_ending("a\r\nb\nc\n")
    assert mixed is True
    assert ending == "LF"  # LF 2 vs CRLF 1 → 대표는 LF


def test_detect_line_ending_none():
    assert detect_line_ending("single line no newline") == (DEFAULT_LINE_ENDING, False)


# ---------------------------------------------------------------------------
# split_lines / join_lines 라운드트립
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a",
        "a\nb",
        "a\nb\n",
        "\n",
        "a\n\nb\n",
    ],
)
def test_split_join_roundtrip_lf(text):
    lines, final_nl = split_lines(text)
    # LF 텍스트는 그대로 복원돼야 한다.
    assert join_lines(lines, "LF", final_nl) == text


def test_split_lines_empty():
    assert split_lines("") == ([], False)


def test_split_lines_basic():
    assert split_lines("a\nb\n") == (["a", "b"], True)
    assert split_lines("a\nb") == (["a", "b"], False)


def test_split_lines_normalizes_crlf():
    lines, final_nl = split_lines("a\r\nb\r\n")
    assert lines == ["a", "b"]
    assert final_nl is True


# ---------------------------------------------------------------------------
# read_document / write_document
# ---------------------------------------------------------------------------


def test_read_document_lf(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"line1\nline2\n")
    doc = read_document(p)
    assert doc.lines == ["line1", "line2"]
    assert doc.line_ending == "LF"
    assert doc.encoding == "utf-8"
    assert doc.final_newline is True
    assert doc.dirty is False
    assert doc.path == str(p)


def test_read_document_crlf(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"line1\r\nline2\r\n")
    doc = read_document(p)
    assert doc.lines == ["line1", "line2"]
    assert doc.line_ending == "CRLF"


def test_read_document_binary_raises(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x89PNG\x00\x00binary")
    with pytest.raises(BinaryFileError):
        read_document(p)


@pytest.mark.parametrize(
    "raw",
    [
        b"line1\nline2\n",          # LF, 끝 줄바꿈 O
        b"line1\nline2",            # LF, 끝 줄바꿈 X
        b"line1\r\nline2\r\n",      # CRLF
        b"\xef\xbb\xbfhello\nbye\n",  # UTF-8 BOM
        "안녕\n세계\n".encode("utf-16"),  # UTF-16
        "한글 텍스트\n둘째 줄\n".encode("utf-8"),  # UTF-8 한국어
    ],
)
def test_read_write_roundtrip_preserves_bytes(tmp_path, raw):
    src = tmp_path / "src.txt"
    src.write_bytes(raw)

    doc = read_document(src)
    out = tmp_path / "out.txt"
    write_document(doc, out)

    assert out.read_bytes() == raw
    assert doc.path == str(out)
    assert doc.dirty is False


def test_write_document_clears_dirty(tmp_path):
    doc = new_document()
    doc.lines = ["hello"]
    doc.final_newline = True
    doc.dirty = True

    out = tmp_path / "new.txt"
    write_document(doc, out)

    assert doc.dirty is False
    assert doc.path == str(out)
    assert out.read_bytes() == b"hello" + ("\r\n" if DEFAULT_LINE_ENDING == "CRLF" else "\n").encode()


def test_write_document_no_path_raises():
    doc = new_document()
    doc.lines = ["x"]
    with pytest.raises(ValueError):
        write_document(doc)  # path=None, doc.path=None


def test_new_document_is_empty():
    doc = new_document()
    assert doc.path is None
    assert doc.lines == []
    assert doc.is_empty is True
    assert doc.encoding == "utf-8"
