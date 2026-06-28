"""애플리케이션 진입점."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from rox_merge.ui.folder_view import FolderCompareWindow
from rox_merge.ui.main_window import MainWindow


def run(argv: list[str] | None = None) -> int:
    """GUI를 실행한다.

    인자가 폴더 2개면 폴더 비교 창을, 아니면 파일 비교 창을 띄운다.
    파일 비교 창에는 선택적으로 좌/우 파일 경로 2개를 줄 수 있다.
    """
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    args = argv[1:3]

    if len(args) == 2 and all(os.path.isdir(a) for a in args):
        window = FolderCompareWindow()
        window.set_roots(args[0], args[1])
    else:
        window = MainWindow()
        if args:
            from rox_merge.fileio import BinaryFileError, read_document

            for side, path in zip(["left", "right"], args):
                try:
                    window._set_doc(side, read_document(path))  # noqa: SLF001
                except (OSError, BinaryFileError, UnicodeDecodeError):
                    pass
            window._recompute()  # noqa: SLF001

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
