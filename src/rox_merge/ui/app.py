"""애플리케이션 진입점."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from rox_merge.core.document import Document
from rox_merge.ui.main_window import MainWindow


def run(argv: list[str] | None = None) -> int:
    """GUI를 실행한다. 인자로 좌/우 파일 경로 2개를 받을 수 있다."""
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    window = MainWindow()

    files = argv[1:3]
    if files:
        from rox_merge.fileio import BinaryFileError, read_document

        sides = ["left", "right"]
        for side, path in zip(sides, files):
            try:
                window._set_doc(side, read_document(path))  # noqa: SLF001
            except (OSError, BinaryFileError, UnicodeDecodeError):
                pass
        window._recompute()  # noqa: SLF001

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
