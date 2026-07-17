"""파일 비교 패널 (PLAN §6.2) — 탭에 들어가는 QWidget.

side-by-side DiffView + 미니맵. 편집/병합/Undo/재계산은 DiffController에 위임.
툴바/메뉴는 상위 AppWindow가 제공하며, 이 패널의 공개 메서드를 호출한다.
"""

from __future__ import annotations

import os
from dataclasses import replace

from PySide6.QtCore import Qt, QStringListModel, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rox_merge.app.compare_model import guard_note
from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.fileio import BinaryFileError, read_document, write_document
from rox_merge.ui.diff_controller import DiffController
from rox_merge.ui.diff_view import DiffView
from rox_merge.ui.overview_bar import OverviewBar
from rox_merge.ui.theme import Theme


class _PathEdit(QLineEdit):
    """포커스가 오면 최근 파일 completer 목록을 자동으로 펼쳐 보여주는 경로 입력칸."""

    def focusInEvent(self, event):  # noqa: N802 (Qt)
        super().focusInEvent(event)
        completer = self.completer()
        if completer is not None:
            completer.setCompletionPrefix(self.text())
            completer.complete()


class FileComparePane(QWidget):
    title_changed = Signal(str)
    status_changed = Signal(str)
    file_opened = Signal(str)  # 파일을 열면 경로를 알림(최근 목록용)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)  # 파일 드래그&드롭
        self._view = DiffView()
        self._overview = OverviewBar()
        self._ctl = DiffController(self._view, DiffOptions(), self)
        self._ctl.recomputed.connect(self._on_recomputed)
        self._view.active_side_changed.connect(lambda *_: self._emit_title())
        self._overview.row_clicked.connect(self._view.verticalScrollBar().setValue)

        # 좌/우: [찾아보기 ...][경로 입력칸(포커스 시 최근 목록 자동 표시)]
        self._left_model = QStringListModel([])
        self._right_model = QStringListModel([])
        self._left_browse = self._make_browse_button("left")
        self._left_path = self._make_path_edit("왼쪽 파일 경로 (Enter로 열기)", "left", self._left_model)
        self._right_browse = self._make_browse_button("right")
        self._right_path = self._make_path_edit("오른쪽 파일 경로 (Enter로 열기)", "right", self._right_model)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(2, 2, 2, 2)
        path_row.setSpacing(2)
        path_row.addWidget(self._left_browse)
        path_row.addWidget(self._left_path, 1)
        path_row.addSpacing(6)
        path_row.addWidget(self._right_browse)
        path_row.addWidget(self._right_path, 1)
        path_row.addSpacing(self._overview.width() or 14)  # 미니맵 폭만큼 우측 정렬

        body = QWidget()
        brow = QHBoxLayout(body)
        brow.setContentsMargins(0, 0, 0, 0)
        brow.setSpacing(0)
        brow.addWidget(self._view, 1)
        brow.addWidget(self._overview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(path_row)
        layout.addWidget(body, 1)

        # 외부(디스크) 변경 감지용: 측별 기준 지문 + '무시' 지문 + 모달 재진입 가드
        self._disk_sig: dict[str, tuple[int, int] | None] = {"left": None, "right": None}
        self._ignored_sig: dict[str, tuple[int, int] | None] = {"left": None, "right": None}
        self._prompting = False

        self._ctl.recompute()

    # --------------------------------------------------------- 경로바 위젯
    def _make_browse_button(self, side: str) -> QToolButton:
        btn = QToolButton()
        btn.setText("...")
        btn.setToolTip(f"{side} 파일 찾아보기")
        btn.clicked.connect(lambda: self._open(side))
        return btn

    def _make_path_edit(self, placeholder: str, side: str, model: QStringListModel) -> _PathEdit:
        edit = _PathEdit()
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.returnPressed.connect(lambda s=side: self._load_path(s))
        completer = QCompleter(model, edit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        # 최근 항목 선택 시 바로 로드
        completer.activated.connect(lambda text, s=side: self._load(s, text))
        edit.setCompleter(completer)
        return edit

    def set_recent(self, paths: list[str]) -> None:
        """최근 파일 목록을 좌/우 경로칸 자동완성에 반영한다."""
        self._left_model.setStringList(list(paths))
        self._right_model.setStringList(list(paths))

    # ---------------------------------------------------- AppWindow 공개 API
    def controller(self) -> DiffController:
        return self._ctl

    def open_side(self, side: str) -> None:
        self._open(side)

    def save(self, as_new: bool = False) -> None:
        self._save_active(as_new)

    def options(self) -> DiffOptions:
        return self._ctl.options

    def apply_theme(self, theme: Theme) -> None:
        self._view.set_theme(theme)
        self._overview.set_theme(theme)

    def apply_font(self, pt: int) -> None:
        self._view.set_font_point_size(pt)

    def apply_options(self, opts: DiffOptions) -> None:
        self._ctl.set_options(opts)

    # --------------------------------------------------------------- slots
    def prompt_files(self) -> None:
        """왼쪽 → 오른쪽 파일을 순서대로 선택받아 비교한다(새 파일 비교용)."""
        left, _ = QFileDialog.getOpenFileName(self.window(), "왼쪽 파일 선택")
        if not left:
            return
        self._load("left", left)
        right, _ = QFileDialog.getOpenFileName(self.window(), "오른쪽 파일 선택")
        if not right:
            return
        self._load("right", right)

    # ------------------------------------------------------- 드래그&드롭(파일)
    def _dropped_files(self, event) -> list[str]:
        md = event.mimeData()
        if not md.hasUrls():
            return []
        return [
            u.toLocalFile() for u in md.urls()
            if u.isLocalFile() and os.path.isfile(u.toLocalFile())
        ]

    def dragEnterEvent(self, event):  # noqa: N802 (Qt)
        if self._dropped_files(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):  # noqa: N802 (Qt)
        if self._dropped_files(event):
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802 (Qt)
        files = self._dropped_files(event)
        if not files:
            return
        if len(files) >= 2:
            self._load("left", files[0])
            self._load("right", files[1])
        else:
            side = "left" if event.position().x() < self.width() / 2 else "right"
            self._load(side, files[0])
        event.acceptProposedAction()

    def _open(self, side: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self.window(), f"{side} 파일 열기")
        if not path:
            return
        self._load(side, path)

    def _load_path(self, side: str) -> None:
        edit = self._left_path if side == "left" else self._right_path
        path = edit.text().strip()
        if path:
            self._load(side, path)

    def _load(self, side: str, path: str) -> None:
        try:
            doc = read_document(path)
        except BinaryFileError as exc:
            QMessageBox.warning(self.window(), "바이너리 파일", str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self.window(), "열기 실패", str(exc))
            return
        self._ctl.set_document(side, doc)
        self._snapshot_side(side)
        if doc.path:
            self.file_opened.emit(doc.path)

    def _save_active(self, as_new: bool = False) -> None:
        self._ctl.commit_edit()
        side = self._view.active_side
        doc = self._ctl.left if side == "left" else self._ctl.right
        path = doc.path
        if as_new or path is None:
            path, _ = QFileDialog.getSaveFileName(self.window(), f"{side} 저장")
            if not path:
                return  # 취소(Esc) → 저장 안 함
        try:
            write_document(doc, path)
        except OSError as exc:
            QMessageBox.critical(self.window(), "저장 실패", str(exc))
            return
        self._snapshot_side(side)  # 우리 저장으로 바뀐 mtime을 기준선에 반영(자기 저장 오탐 방지)
        self._emit_title()

    # ------------------------------------------------ 외부(디스크) 변경 감지/재로드
    def _file_sig(self, path: str | None) -> tuple[int, int] | None:
        """파일의 (mtime_ns, size) 지문. 경로 없음·접근 불가면 None."""
        if not path:
            return None
        try:
            st = os.stat(path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _doc(self, side: str) -> Document:
        return self._ctl.left if side == "left" else self._ctl.right

    def _snapshot_side(self, side: str) -> None:
        """현재 버퍼가 반영하는 디스크 상태를 기준선으로 저장(무시 상태 해제)."""
        self._disk_sig[side] = self._file_sig(self._doc(side).path)
        self._ignored_sig[side] = None

    def _externally_changed_sides(self) -> list[str]:
        """load/save 이후 디스크에서 바뀐(그리고 아직 '무시'하지 않은) 측 목록."""
        changed: list[str] = []
        for side in ("left", "right"):
            base = self._disk_sig.get(side)
            path = self._doc(side).path
            if not path or base is None:
                continue
            cur = self._file_sig(path)
            if cur is None:
                continue  # 삭제/접근 불가는 이번 범위에서 알리지 않음
            if cur != base and cur != self._ignored_sig.get(side):
                changed.append(side)
        return changed

    def _reload_sides(self, sides: list[str]) -> None:
        for side in sides:
            path = self._doc(side).path
            if not path:
                continue
            try:
                new = read_document(path)
            except BinaryFileError as exc:
                QMessageBox.warning(self.window(), "바이너리 파일", str(exc))
                continue
            except OSError as exc:
                QMessageBox.critical(self.window(), "열기 실패", str(exc))
                continue
            self._ctl.set_document(side, new)
            self._snapshot_side(side)

    def check_external_changes(self) -> None:
        """창 활성화·탭 전환 시 호출: 디스크가 바뀌었으면 모달로 재로드 여부를 묻는다."""
        if self._prompting:
            return
        sides = self._externally_changed_sides()
        if not sides:
            return
        self._prompting = True
        try:
            names = ", ".join(os.path.basename(self._doc(s).path or "") for s in sides)
            box = QMessageBox(self.window())
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("파일이 디스크에서 변경됨")
            box.setText(
                f"다음 파일이 외부에서 변경되었습니다:\n{names}\n\n"
                "다시 불러올까요? (저장하지 않은 편집은 사라집니다)"
            )
            reload_btn = box.addButton("다시 불러오기", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("무시", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is reload_btn:
                self._reload_sides(sides)
            else:
                for side in sides:  # '무시'는 이 상태를 다음 변경 때까지 유지
                    self._ignored_sig[side] = self._file_sig(self._doc(side).path)
        finally:
            self._prompting = False

    def reload_from_disk(self) -> None:
        """F5: 좌/우 파일을 디스크에서 다시 로드. 미저장 편집이 있으면 확인 후 진행."""
        self._ctl.commit_edit()  # 진행 중(미확정) 편집을 확정해 dirty 상태를 정확히 반영
        sides = [s for s in ("left", "right") if self._doc(s).path]
        if not sides:
            return
        if any(self._doc(s).dirty for s in sides) and not self._confirm_reload_discard():
            return
        self._reload_sides(sides)

    def _confirm_reload_discard(self) -> bool:
        box = QMessageBox(self.window())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("저장하지 않은 변경")
        box.setText("저장하지 않은 편집이 있습니다.\n디스크 내용으로 다시 불러올까요? (편집 사라짐)")
        ok = box.addButton("다시 불러오기", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is ok

    def _toggle_moves(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, detect_moves=enabled))

    def _toggle_whitespace(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, ignore_whitespace=enabled))

    def _toggle_case(self, enabled: bool) -> None:
        self._ctl.set_options(replace(self._ctl.options, ignore_case=enabled))

    # --------------------------------------------------------------- helpers
    def _on_recomputed(self) -> None:
        self._overview.set_result(self._view.result)
        self._emit_title()
        self._sync_paths()
        self.status_changed.emit(guard_note(self._ctl.left, self._ctl.right) or "")

    def _sync_paths(self) -> None:
        # 입력 중이 아니면 현재 문서 경로로 갱신
        if not self._left_path.hasFocus():
            self._left_path.setText(self._ctl.left.path or "")
        if not self._right_path.hasFocus():
            self._right_path.setText(self._ctl.right.path or "")

    def _emit_title(self) -> None:
        self.title_changed.emit(self.title())

    def title(self) -> str:
        def name(doc: Document) -> str:
            base = os.path.basename(doc.path) if doc.path else "(빈)"
            return ("*" if doc.dirty else "") + base

        return f"{name(self._ctl.left)} ⇄ {name(self._ctl.right)}"

    # ------------------------------------------------------ 외부/테스트용
    def _set_doc(self, side: str, doc: Document) -> None:
        if side == "left":
            self._ctl.left = doc
        else:
            self._ctl.right = doc
        self._snapshot_side(side)  # CLI/외부에서 넣은 문서도 외부 변경 감지 기준선 설정

    def _recompute(self) -> None:
        self._ctl.recompute()
