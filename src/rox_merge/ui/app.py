"""애플리케이션 진입점."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from rox_merge.ui.app_window import AppWindow


def run(argv: list[str] | None = None) -> int:
    """GUI를 실행한다.

    인자가 폴더 2개면 폴더 비교 탭을, 아니면 파일 비교 탭을 연다.
    파일 비교 탭에는 선택적으로 좌/우 파일 경로 2개를 줄 수 있다.
    실행 후에는 툴바로 파일/폴더 비교 탭을 더 추가할 수 있다.
    """
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setOrganizationName("rox-merge")
    app.setApplicationName("rox-merge")
    window = AppWindow()

    args = argv[1:3]
    if len(args) == 2 and all(os.path.isdir(a) for a in args):
        window.add_folder_tab(args[0], args[1])
    else:
        left = right = None
        if args:
            from rox_merge.fileio import BinaryFileError, read_document

            docs = []
            for path in args:
                try:
                    docs.append(read_document(path))
                except (OSError, BinaryFileError, UnicodeDecodeError):
                    docs.append(None)
            left = docs[0] if len(docs) > 0 else None
            right = docs[1] if len(docs) > 1 else None
        window.add_file_tab(left, right)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
