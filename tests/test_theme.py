"""라이트/다크 테마 토큰 테스트."""

import pytest

pytest.importorskip("PySide6.QtGui")

from rox_merge.core.diff import (  # noqa: E402
    KIND_CHANGE,
    KIND_DELETE,
    KIND_INSERT,
    KIND_MOVED,
    KIND_WHITESPACE,
)
from rox_merge.ui.theme import Theme, dark_palette  # noqa: E402


def test_light_and_dark_differ():
    light, dark = Theme(dark=False), Theme(dark=True)
    assert light.background.getRgb() != dark.background.getRgb()
    assert light.text.getRgb() != dark.text.getRgb()
    assert dark.dark is True and light.dark is False


def test_all_kinds_have_line_colors():
    for theme in (Theme(False), Theme(True)):
        for kind in (KIND_INSERT, KIND_DELETE, KIND_CHANGE, KIND_WHITESPACE, KIND_MOVED):
            assert theme.line_bg(kind) is not None
        assert theme.line_bg("equal") is None


def test_intraline_colors():
    for theme in (Theme(False), Theme(True)):
        for kind in (KIND_INSERT, KIND_DELETE, KIND_CHANGE):
            assert theme.intraline_bg(kind) is not None


def test_dark_palette_returns_palette():
    from PySide6.QtGui import QPalette

    assert isinstance(dark_palette(), QPalette)
