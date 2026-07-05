"""파일 비교 창의 비교 옵션 토글(공백/대소문자/이동) 헤드리스 테스트."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from rox_merge.core.diff import KIND_EQUAL, KIND_WHITESPACE  # noqa: E402
from rox_merge.core.document import Document  # noqa: E402
from rox_merge.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    w = MainWindow()
    w._set_doc("left", Document(path="L", lines=["    return 1"]))
    w._set_doc("right", Document(path="R", lines=["\treturn 1"]))
    w._recompute()
    return w


def _kinds(w):
    return [r.kind for r in w._view.result.rows]


def test_default_shows_whitespace(win):
    assert _kinds(win) == [KIND_WHITESPACE]


def test_toggle_ignore_whitespace_promotes_to_equal(win):
    win._toggle_whitespace(True)
    assert win._ctl.options.ignore_whitespace is True
    assert _kinds(win) == [KIND_EQUAL]
    win._toggle_whitespace(False)
    assert _kinds(win) == [KIND_WHITESPACE]


def test_toggle_ignore_case(app):
    w = MainWindow()
    w._set_doc("left", Document(path="L", lines=["Hello"]))
    w._set_doc("right", Document(path="R", lines=["hello"]))
    w._recompute()
    assert _kinds(w) != [KIND_EQUAL]
    w._toggle_case(True)
    assert w._ctl.options.ignore_case is True
    assert _kinds(w) == [KIND_EQUAL]


def test_toggle_moves(win):
    assert win._ctl.options.detect_moves is True
    win._toggle_moves(False)
    assert win._ctl.options.detect_moves is False
