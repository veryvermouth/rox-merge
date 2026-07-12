"""앱 메인 윈도우 — 탭 단위 비교 세션 + 메뉴바/툴바 (PLAN §6.1).

하나의 창에서 파일/폴더 비교 세션을 탭으로 연다. 메뉴바(전체 기능)와 간단
툴바는 여기 한 곳에 있고, 각 항목은 현재 활성 탭(패널)으로 동작을 전달한다.
현재 탭에 맞지 않는 항목은 비활성(회색) 처리한다.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QToolBar

from rox_merge.core.diff import DiffOptions
from rox_merge.core.document import Document
from rox_merge.ui.diff_view import DiffView
from rox_merge.ui.file_pane import FileComparePane
from rox_merge.ui.folder_pane import FolderComparePane
from rox_merge.ui.theme import Theme, dark_palette, light_palette


class AppWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("rox-merge")
        self.resize(1150, 780)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._sync)
        self.setCentralWidget(self._tabs)

        self._file_only: list[QAction] = []
        self._folder_only: list[QAction] = []

        # 저장된 설정 복원 (폰트/테마/비교 옵션)
        self._settings = QSettings()
        s = self._settings
        self._file_font_pt = int(s.value("file_font_pt", 11))
        self._folder_font_pt = int(s.value("folder_font_pt", 11))
        self._dark = s.value("dark", False, type=bool)
        self._default_options = DiffOptions(
            detect_moves=s.value("detect_moves", True, type=bool),
            ignore_whitespace=s.value("ignore_whitespace", False, type=bool),
            ignore_case=s.value("ignore_case", False, type=bool),
        )
        self._folder_exact = s.value("folder_exact", False, type=bool)

        # 라이트/다크 모두 Fusion 스타일 + 명시적 팔레트로 고정(OS 테마 무관).
        _app = QApplication.instance()
        _app.setStyle("Fusion")
        _app.setPalette(dark_palette() if self._dark else light_palette())
        self._apply_tab_style()
        self._build_menu_and_toolbar()

    def _apply_tab_style(self) -> None:
        """탭 높이를 줄이되(패딩), 배경/글자색은 현재 팔레트에 맞춰 테마와 연동."""
        pal = QApplication.instance().palette()
        win = pal.color(QPalette.ColorRole.Window).name()
        base = pal.color(QPalette.ColorRole.Base).name()
        text = pal.color(QPalette.ColorRole.WindowText).name()
        self._tabs.setStyleSheet(
            f"QTabBar::tab {{ padding: 2px 12px; background: {win}; color: {text}; }}"
            f"QTabBar::tab:selected {{ background: {base}; }}"
        )

    # ------------------------------------------------------- 메뉴/툴바 구성
    def _build_menu_and_toolbar(self) -> None:
        mb = self.menuBar()

        # --- 파일
        m = mb.addMenu("파일(&F)")
        a_newfile = self._mk("새 파일 비교", "Ctrl+N", lambda: self.add_file_tab())
        a_newfolder = self._mk("새 폴더 비교", "Ctrl+D", self.add_folder_tab)
        m.addAction(a_newfile)
        m.addAction(a_newfolder)
        m.addSeparator()
        self._act_open_l = self._mk("왼쪽 열기", "Ctrl+O", lambda: self._open_side("left"))
        self._act_open_r = self._mk("오른쪽 열기", "Ctrl+Shift+O", lambda: self._open_side("right"))
        m.addAction(self._act_open_l)
        m.addAction(self._act_open_r)
        m.addSeparator()
        a_save = self._mk("저장", "Ctrl+S", lambda: self._save(False))
        a_saveas = self._mk("다른 이름으로 저장", "Ctrl+Shift+S", lambda: self._save(True), file_only=True)
        m.addAction(a_save)
        m.addAction(a_saveas)
        m.addSeparator()
        a_closetab = self._mk("탭 닫기", "Ctrl+W", self._close_current_tab)
        a_quit = self._mk("종료", "Ctrl+Q", self.close)
        m.addAction(a_closetab)
        m.addAction(a_quit)

        # --- 편집 (포커스된 편집창 대상)
        m = mb.addMenu("편집(&E)")
        a_undo = self._mk("실행 취소", "Ctrl+Z", self._undo)
        a_redo = self._mk("다시 실행", ["Ctrl+Shift+Z", "Ctrl+Y"], self._redo)
        m.addAction(a_undo)
        m.addAction(a_redo)
        m.addSeparator()
        m.addAction(self._mk("잘라내기", "Ctrl+X", self._cut))
        m.addAction(self._mk("복사", "Ctrl+C", self._copy))
        m.addAction(self._mk("붙여넣기", "Ctrl+V", self._paste))
        m.addAction(self._mk("모두 선택", "Ctrl+A", self._select_all))

        # --- 보기
        m = mb.addMenu("보기(&V)")
        a_prev = self._mk("이전 차이", "Ctrl+1", lambda: self._jump(-1))
        a_next = self._mk("다음 차이", "Ctrl+2", lambda: self._jump(+1))
        m.addAction(a_prev)
        m.addAction(a_next)
        m.addSeparator()
        m.addAction(self._mk("글꼴 확대", ["Ctrl++", "Ctrl+="], lambda: self._zoom(+1)))
        m.addAction(self._mk("글꼴 축소", "Ctrl+-", lambda: self._zoom(-1)))
        m.addAction(self._mk("원래 크기 / 초기 상태", "Ctrl+0", self._reset0))
        m.addSeparator()
        self._act_dark = self._mk("다크 테마", None, self._toggle_dark, checkable=True)
        m.addAction(self._act_dark)
        m.addSeparator()
        self._act_expand = self._mk("전체 펼침", "Ctrl+]", self._expand_all, folder_only=True)
        self._act_collapse = self._mk("전체 접기", "Ctrl+[", self._collapse_all, folder_only=True)
        m.addAction(self._act_expand)
        m.addAction(self._act_collapse)

        # --- 비교
        m = mb.addMenu("비교(&C)")
        self._act_moves = self._mk("이동 탐지", None, self._toggle_moves, checkable=True, file_only=True)
        self._act_ws = self._mk("공백 무시", None, self._toggle_ws, checkable=True, file_only=True)
        self._act_case = self._mk("대소문자 무시", None, self._toggle_case, checkable=True, file_only=True)
        for a in (self._act_moves, self._act_ws, self._act_case):
            m.addAction(a)
        m.addSeparator()
        self._act_exact = self._mk("정확 비교(해시)", None, self._toggle_exact, checkable=True, folder_only=True)
        self._act_filter = self._mk("다른 항목만", None, self._toggle_filter, checkable=True, folder_only=True)
        self._act_tabmode = self._mk("새 탭 모드", None, self._toggle_tabmode, checkable=True, folder_only=True)
        a_refresh = self._mk("새로고침", "F5", self._refresh, folder_only=True)
        for a in (self._act_exact, self._act_filter, self._act_tabmode, a_refresh):
            m.addAction(a)

        # --- 도움말
        m = mb.addMenu("도움말(&H)")
        m.addAction(self._mk("정보", None, self._about))

        # --- 툴바 (자주 쓰는 것만, 같은 액션 재사용)
        bar = QToolBar("main")
        self.addToolBar(bar)
        for a in (a_newfile, a_newfolder):
            bar.addAction(a)
        bar.addSeparator()
        for a in (self._act_open_l, self._act_open_r, a_save):
            bar.addAction(a)
        bar.addSeparator()
        for a in (a_undo, a_redo):
            bar.addAction(a)
        bar.addSeparator()
        for a in (a_prev, a_next):
            bar.addAction(a)
        bar.addSeparator()
        bar.addAction(self._act_dark)

    def _mk(self, text, shortcut, slot, checkable=False, file_only=False, folder_only=False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            if isinstance(shortcut, list):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        self.addAction(a)  # 창 레벨 단축키
        if file_only:
            self._file_only.append(a)
        if folder_only:
            self._folder_only.append(a)
        return a

    # ------------------------------------------------------------- 탭 추가
    def add_file_tab(self, left: Document | None = None, right: Document | None = None):
        pane = FileComparePane()
        if left is not None:
            pane._set_doc("left", left)
        if right is not None:
            pane._set_doc("right", right)
        pane.apply_options(self._default_options)  # 저장된 비교 옵션 + 재계산
        pane.apply_theme(Theme(dark=self._dark))
        pane.apply_font(self._file_font_pt)
        index = self._tabs.addTab(pane, pane.title())
        pane.title_changed.connect(lambda t, p=pane: self._set_tab_title(p, t))
        pane.status_changed.connect(self.statusBar().showMessage)
        self._tabs.setCurrentIndex(index)
        return pane

    def add_folder_tab(self, left=None, right=None):
        pane = FolderComparePane()
        pane.apply_theme(Theme(dark=self._dark))
        pane.apply_font(self._folder_font_pt)
        if self._folder_exact:
            pane.toggle_exact(True)
        index = self._tabs.addTab(pane, pane.title())
        pane.title_changed.connect(lambda t, p=pane: self._set_tab_title(p, t))
        self._tabs.setCurrentIndex(index)
        if left and right:
            pane.set_roots(left, right)
        else:
            pane.prompt_roots()
        return pane

    # ------------------------------------------------------------- 디스패치
    def _pane(self):
        return self._tabs.currentWidget()

    def _controller(self):
        p = self._pane()
        return p.controller() if hasattr(p, "controller") else None

    def _focused_view(self) -> DiffView | None:
        w = QApplication.focusWidget()
        return w if isinstance(w, DiffView) else None

    def _open_side(self, side: str) -> None:
        p = self._pane()
        if hasattr(p, "open_side"):
            p.open_side(side)

    def _save(self, as_new: bool) -> None:
        p = self._pane()
        if isinstance(p, FileComparePane):
            p.save(as_new)
        elif isinstance(p, FolderComparePane):
            p.save()

    def _undo(self) -> None:
        c = self._controller()
        if c:
            c.undo_action()

    def _redo(self) -> None:
        c = self._controller()
        if c:
            c.redo_action()

    def _jump(self, delta: int) -> None:
        c = self._controller()
        if c:
            c.jump(delta)

    def _zoom(self, delta: int) -> None:
        # 텍스트 비교와 폴더 비교의 글꼴 크기는 따로 관리
        p = self._pane()
        if isinstance(p, FileComparePane):
            self._file_font_pt = max(6, min(40, self._file_font_pt + delta))
        elif isinstance(p, FolderComparePane):
            self._folder_font_pt = max(6, min(40, self._folder_font_pt + delta))
        self._apply_font_all()

    def _apply_font_all(self) -> None:
        for i in range(self._tabs.count()):
            p = self._tabs.widget(i)
            if isinstance(p, FileComparePane):
                p.apply_font(self._file_font_pt)
            elif isinstance(p, FolderComparePane):
                p.apply_font(self._folder_font_pt)

    def _reset0(self) -> None:
        p = self._pane()
        if isinstance(p, FileComparePane):
            self._file_font_pt = 11  # 텍스트 비교 글꼴 원래 크기
            self._apply_font_all()
        elif isinstance(p, FolderComparePane):
            p.reset_expand()

    def _copy(self) -> None:
        v = self._focused_view()
        if v:
            v.copy_selection()

    def _cut(self) -> None:
        v = self._focused_view()
        if v:
            v.cut_selection()

    def _paste(self) -> None:
        v = self._focused_view()
        if v:
            v.paste_clipboard()

    def _select_all(self) -> None:
        v = self._focused_view()
        if v:
            v.select_all()

    def _toggle_moves(self, on: bool) -> None:
        self._default_options = replace(self._default_options, detect_moves=on)
        p = self._pane()
        if isinstance(p, FileComparePane):
            p._toggle_moves(on)

    def _toggle_ws(self, on: bool) -> None:
        self._default_options = replace(self._default_options, ignore_whitespace=on)
        p = self._pane()
        if isinstance(p, FileComparePane):
            p._toggle_whitespace(on)

    def _toggle_case(self, on: bool) -> None:
        self._default_options = replace(self._default_options, ignore_case=on)
        p = self._pane()
        if isinstance(p, FileComparePane):
            p._toggle_case(on)

    def _toggle_dark(self, on: bool) -> None:
        self._dark = on
        theme = Theme(dark=on)
        app = QApplication.instance()
        if app is not None:
            # 둘 다 Fusion. 라이트도 네이티브로 되돌리지 않고 라이트 팔레트를 써서
            # OS가 다크 모드여도 라이트 크롬이 유지되게 한다.
            app.setStyle("Fusion")
            app.setPalette(dark_palette() if on else light_palette())
        self._apply_tab_style()  # 탭 스타일시트도 새 팔레트 색으로 갱신
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if hasattr(pane, "apply_theme"):
                pane.apply_theme(theme)

    def _toggle_exact(self, on: bool) -> None:
        self._folder_exact = on
        p = self._pane()
        if isinstance(p, FolderComparePane):
            p.toggle_exact(on)

    def _toggle_filter(self, on: bool) -> None:
        p = self._pane()
        if isinstance(p, FolderComparePane):
            p.toggle_filter(on)

    def _toggle_tabmode(self, on: bool) -> None:
        p = self._pane()
        if isinstance(p, FolderComparePane):
            p.toggle_tab_mode(on)

    def _refresh(self) -> None:
        p = self._pane()
        if isinstance(p, FolderComparePane):
            p.refresh()

    def _expand_all(self) -> None:
        p = self._pane()
        if isinstance(p, FolderComparePane):
            p.expand_all()

    def _collapse_all(self) -> None:
        p = self._pane()
        if isinstance(p, FolderComparePane):
            p.collapse_all()

    def _about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from rox_merge import __version__

        QMessageBox.information(
            self,
            "정보",
            f"rox-merge {__version__}\n\n"
            "Araxis Merge 류의 파일·폴더 비교/병합 도구\n"
            "두 파일이나 폴더를 나란히 비교하고, 차이를 한 방향으로 병합·편집할 수 있습니다.\n\n"
            "만든 사람: 박상",
        )

    # --------------------------------------------------------------- helpers
    def _sync(self, *_args) -> None:
        p = self._pane()
        is_file = isinstance(p, FileComparePane)
        is_folder = isinstance(p, FolderComparePane)
        for a in self._file_only:
            a.setEnabled(is_file)
        for a in self._folder_only:
            a.setEnabled(is_folder)
        self._act_open_l.setText("왼쪽 폴더" if is_folder else "왼쪽 열기")
        self._act_open_r.setText("오른쪽 폴더" if is_folder else "오른쪽 열기")
        if is_file:
            o = p.options()
            self._set_check(self._act_moves, o.detect_moves)
            self._set_check(self._act_ws, o.ignore_whitespace)
            self._set_check(self._act_case, o.ignore_case)
        elif is_folder:
            self._set_check(self._act_exact, p.is_exact())
            self._set_check(self._act_filter, p.is_filter())
            self._set_check(self._act_tabmode, p.is_tab_mode())
        self._set_check(self._act_dark, self._dark)  # 다크는 전역
        self._sync_window_title()

    @staticmethod
    def _set_check(action: QAction, value: bool) -> None:
        action.blockSignals(True)
        action.setChecked(value)
        action.blockSignals(False)

    def _set_tab_title(self, pane, title: str) -> None:
        idx = self._tabs.indexOf(pane)
        if idx >= 0:
            self._tabs.setTabText(idx, title)
        self._sync_window_title()

    def _sync_window_title(self, *_args) -> None:
        idx = self._tabs.currentIndex()
        name = self._tabs.tabText(idx) if idx >= 0 else ""
        self.setWindowTitle(f"rox-merge — {name}" if name else "rox-merge")

    def _close_current_tab(self) -> None:
        idx = self._tabs.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    def _close_tab(self, index: int) -> None:
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        if self._tabs.count() == 0:
            self.add_file_tab()  # 최소 한 탭 유지

    def closeEvent(self, event):  # noqa: N802 (Qt) — 종료 시 설정 저장
        s = self._settings
        s.setValue("file_font_pt", self._file_font_pt)
        s.setValue("folder_font_pt", self._folder_font_pt)
        s.setValue("dark", self._dark)
        s.setValue("detect_moves", self._default_options.detect_moves)
        s.setValue("ignore_whitespace", self._default_options.ignore_whitespace)
        s.setValue("ignore_case", self._default_options.ignore_case)
        s.setValue("folder_exact", self._folder_exact)
        super().closeEvent(event)
