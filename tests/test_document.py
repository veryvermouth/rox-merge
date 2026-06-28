"""Document 모델 단위 테스트."""

from rox_merge.core.document import (
    DEFAULT_LINE_ENDING,
    LINE_ENDING_CHARS,
    Document,
)


def test_default_document_is_empty():
    doc = Document()
    assert doc.path is None
    assert doc.lines == []
    assert doc.dirty is False
    assert doc.is_empty is True


def test_is_empty_variants():
    assert Document(lines=[]).is_empty is True
    assert Document(lines=[""]).is_empty is True
    assert Document(lines=["a"]).is_empty is False
    assert Document(lines=["", ""]).is_empty is False  # 빈 두 줄은 '내용 있음'


def test_line_ending_chars_mapping():
    assert LINE_ENDING_CHARS["LF"] == "\n"
    assert LINE_ENDING_CHARS["CRLF"] == "\r\n"
    assert LINE_ENDING_CHARS["CR"] == "\r"


def test_default_line_ending_is_valid():
    assert DEFAULT_LINE_ENDING in LINE_ENDING_CHARS
