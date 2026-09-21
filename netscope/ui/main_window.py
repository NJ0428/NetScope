import base64
import json
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Slot
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QLabel, QMainWindow, QMenu,
    QMessageBox, QSplitter, QStackedWidget, QStatusBar, QTabWidget,
    QVBoxLayout, QWidget,
)
try:
    from PySide6.QtWidgets import QSystemTrayIcon
    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False

from netscope.models.session import SessionEntry, SessionState
from netscope.models.session_table_model import SessionTableModel
from netscope.proxy.engine import ProxyEngine, StubProxyEngine
from netscope.proxy.mitm_engine import MitmproxyEngine
from netscope.rules.rules_engine import RulesEngine
from netscope.ui.composer_panel import ComposerPanel
from netscope.ui.detail_panel import DetailPanel
from netscope.ui.statistics_panel import StatisticsPanel
from netscope.ui.dialogs.breakpoint_dialog import BreakpointDialog
from netscope.ui.dialogs.customize_rules_dialog import CustomizeRulesDialog
from netscope.ui.dialogs.performance_dialog import PerformanceDialog
from netscope.ui.dialogs.proxy_settings_dialog import ProxySettingsDialog
from netscope.ui.dialogs.rules_manager_dialog import RulesManagerDialog
from netscope.ui.dialogs.user_agent_dialog import UserAgentDialog
from netscope.ui.session_table import SessionTableView
from netscope.ui.toolbar import Toolbar
from netscope.ui.welcome_panel import WelcomePanel
from netscope.utils.saz_reader import load_saz
from netscope.utils.system_proxy import clear_system_proxy, set_system_proxy

_RECENT_MAX = 10
_CONFIG_PATH = Path.home() / ".netscope" / "config.json"

_STATUS_IDLE    = "● 대기 중"
_STATUS_CAPTURE = "● 캡처 중"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetScope — Network Traffic Inspector")
        self.setMinimumSize(1024, 640)
        self.resize(1400, 860)

        self._proxy_port = 8888
        self._auto_set_proxy = True   # system proxy 자동 등록 여부
        self._use_real_engine = MitmproxyEngine.AVAILABLE
        self._rules = RulesEngine(self)
        self._session_model = SessionTableModel(self)
        self._engine: ProxyEngine = self._create_engine()
        self._engine.set_rules(self._rules)
        self._current_file: str | None = None
        self._modified = False
        self._recent_files: list[str] = _load_recent_config()
        self._auto_scroll = True
        self._tray_icon = None

        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._apply_global_style()

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()

        # 파일
        file_menu = mb.addMenu("파일")

        # Capture Traffic (F12) — toggle capture start/stop
        self._act_capture = QAction(
            "트래픽 캡처 (Capture Traffic)", self,
            shortcut=QKeySequence(Qt.Key.Key_F12),
            checkable=True,
        )
        self._act_capture.triggered.connect(self._on_capture_toggle)
        file_menu.addAction(self._act_capture)

        file_menu.addSeparator()

        # New Viewer — open a second independent window
        act_new_viewer = QAction("새 뷰어 (New Viewer)", self)
        act_new_viewer.triggered.connect(self._on_new_viewer)
        file_menu.addAction(act_new_viewer)

        # New Session — clear current session list
        act_new = QAction("새 세션 (New Session)", self, shortcut=QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._on_new)
        file_menu.addAction(act_new)

        file_menu.addSeparator()

        # Load Archive — supports .netsession and Fiddler .saz
        act_load = QAction(
            "아카이브 불러오기 (Load Archive)...", self,
            shortcut=QKeySequence.StandardKey.Open,
        )
        act_load.triggered.connect(self._on_load_archive)
        file_menu.addAction(act_load)

        # Recent Archives submenu
        self._recent_menu = file_menu.addMenu("최근 아카이브 (Recent Archives)")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        self._act_save = QAction("저장 (Save)", self, shortcut=QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._on_save)
        file_menu.addAction(self._act_save)

        act_save_as = QAction(
            "다른 이름으로 저장 (Save As)...", self,
            shortcut=QKeySequence("Ctrl+Shift+S"),
        )
        act_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_import = QAction("세션 가져오기 (Import Sessions)...", self)
        act_import.triggered.connect(self._on_import)
        file_menu.addAction(act_import)

        act_export = QAction("세션 내보내기 (Export Sessions)...", self)
        act_export.triggered.connect(self._on_export)
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_quit = QAction("종료 (Exit)", self, shortcut=QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 편집
        edit_menu = mb.addMenu("편집")

        # Copy submenu
        copy_menu = edit_menu.addMenu("복사 (Copy)")

        act_copy_url = QAction("URL 복사 (Copy URL)", self)
        act_copy_url.triggered.connect(self._on_edit_copy_url)
        copy_menu.addAction(act_copy_url)

        act_copy_headers = QAction("헤더 복사 (Copy Headers)", self)
        act_copy_headers.triggered.connect(self._on_edit_copy_headers)
        copy_menu.addAction(act_copy_headers)

        act_copy_request = QAction("요청 복사 (Copy Request)", self)
        act_copy_request.triggered.connect(self._on_edit_copy_request)
        copy_menu.addAction(act_copy_request)

        act_copy_response = QAction("응답 복사 (Copy Response)", self)
        act_copy_response.triggered.connect(self._on_edit_copy_response)
        copy_menu.addAction(act_copy_response)

        act_copy_full = QAction("전체 복사 (Copy Full Session)", self)
        act_copy_full.triggered.connect(self._on_edit_copy_full)
        copy_menu.addAction(act_copy_full)

        edit_menu.addSeparator()

        # Remove submenu
        remove_menu = edit_menu.addMenu("삭제 (Remove)")

        act_remove_selected = QAction(
            "선택 세션 삭제 (Remove Selected)", self,
            shortcut=QKeySequence(Qt.Key.Key_Delete),
        )
        act_remove_selected.triggered.connect(self._on_edit_remove_selected)
        remove_menu.addAction(act_remove_selected)

        act_remove_unselected = QAction("선택 외 세션 삭제 (Remove Unselected)", self)
        act_remove_unselected.triggered.connect(self._on_edit_remove_unselected)
        remove_menu.addAction(act_remove_unselected)

        act_remove_all = QAction("모든 세션 삭제 (Remove All)", self)
        act_remove_all.triggered.connect(self._on_edit_remove_all)
        remove_menu.addAction(act_remove_all)

        edit_menu.addSeparator()

        act_select_all = QAction(
            "전체 선택 (Select All)", self,
            shortcut=QKeySequence.StandardKey.SelectAll,
        )
        act_select_all.triggered.connect(self._on_edit_select_all)
        edit_menu.addAction(act_select_all)

        edit_menu.addSeparator()

        self._act_undelete = QAction("되돌리기 (Undelete)", self)
        self._act_undelete.setEnabled(False)
        self._act_undelete.triggered.connect(self._on_edit_undelete)
        edit_menu.addAction(self._act_undelete)

        edit_menu.addSeparator()

        act_paste_sessions = QAction("세션으로 붙여넣기 (Paste as Sessions)", self)
        act_paste_sessions.triggered.connect(self._on_edit_paste_as_sessions)
        edit_menu.addAction(act_paste_sessions)

        edit_menu.addSeparator()

        # Mark submenu
        mark_menu = edit_menu.addMenu("표시 (Mark)")
        for _label, _color in [
            ("빨강 (Red)",    "#ff6b6b"),
            ("노랑 (Yellow)", "#ffd93d"),
            ("초록 (Green)",  "#6bcb77"),
            ("파랑 (Blue)",   "#4d96ff"),
            ("보라 (Purple)", "#c77dff"),
        ]:
            _act = QAction(_label, self)
            _act.triggered.connect(
                lambda checked, c=_color: self._on_edit_mark(c)
            )
            mark_menu.addAction(_act)
        mark_menu.addSeparator()
        act_clear_mark = QAction("표시 지우기 (Clear Mark)", self)
        act_clear_mark.triggered.connect(lambda checked: self._on_edit_mark(None))
        mark_menu.addAction(act_clear_mark)

        edit_menu.addSeparator()

        act_unlock = QAction(
            "편집 모드 (Unlock for Editing)", self,
            shortcut=QKeySequence(Qt.Key.Key_F2),
        )
        act_unlock.triggered.connect(self._on_edit_unlock)
        edit_menu.addAction(act_unlock)

        edit_menu.addSeparator()

        act_find_sessions = QAction(
            "세션 찾기 (Find Sessions)", self,
            shortcut=QKeySequence.StandardKey.Find,
        )
        act_find_sessions.triggered.connect(self._on_find_sessions)
        edit_menu.addAction(act_find_sessions)

        # 규칙
        rules_menu = mb.addMenu("규칙")

        act_rules_mgr = QAction("규칙 관리...", self)
        act_rules_mgr.triggered.connect(self._on_rules_manager)
        rules_menu.addAction(act_rules_mgr)

        rules_menu.addSeparator()

        # Automatic Breakpoints submenu
        bp_menu = rules_menu.addMenu("중단점 (Automatic Breakpoints)")

        self._act_bp_req = QAction("요청에서 중단 (Before Request)", self, checkable=True)
        self._act_bp_req.triggered.connect(
            lambda checked: self._toggle_rule("breakpoint_requests", checked)
        )
        bp_menu.addAction(self._act_bp_req)

        self._act_bp_resp = QAction("응답에서 중단 (Before Response)", self, checkable=True)
        self._act_bp_resp.triggered.connect(
            lambda checked: self._toggle_rule("breakpoint_responses", checked)
        )
        bp_menu.addAction(self._act_bp_resp)

        rules_menu.addSeparator()

        # Filter toggles
        self._act_hide_images = QAction("이미지 요청 숨기기 (Hide Image Requests)", self, checkable=True)
        self._act_hide_images.triggered.connect(
            lambda checked: self._toggle_rule("hide_image_requests", checked)
        )
        rules_menu.addAction(self._act_hide_images)

        self._act_hide_connects = QAction("CONNECT 요청 숨기기 (Hide CONNECTs)", self, checkable=True)
        self._act_hide_connects.triggered.connect(
            lambda checked: self._toggle_rule("hide_connects", checked)
        )
        rules_menu.addAction(self._act_hide_connects)

        self._act_hide_304s = QAction("304 응답 숨기기 (Hide 304s)", self, checkable=True)
        self._act_hide_304s.triggered.connect(
            lambda checked: self._toggle_rule("hide_304s", checked)
        )
        rules_menu.addAction(self._act_hide_304s)

        rules_menu.addSeparator()

        # Modification toggles
        self._act_proxy_auth = QAction("프록시 인증 요구 (Require Proxy Authentication)", self, checkable=True)
        self._act_proxy_auth.triggered.connect(
            lambda checked: self._toggle_rule("require_proxy_auth", checked)
        )
        rules_menu.addAction(self._act_proxy_auth)

        self._act_gzip = QAction("GZIP 인코딩 적용 (Apply GZIP Encoding)", self, checkable=True)
        self._act_gzip.triggered.connect(
            lambda checked: self._toggle_rule("apply_gzip", checked)
        )
        rules_menu.addAction(self._act_gzip)

        self._act_remove_enc = QAction("모든 인코딩 제거 (Remove All Encodings)", self, checkable=True)
        self._act_remove_enc.triggered.connect(
            lambda checked: self._toggle_rule("remove_encodings", checked)
        )
        rules_menu.addAction(self._act_remove_enc)

        self._act_japanese = QAction("일본어 콘텐츠 요청 (Request Japanese Content)", self, checkable=True)
        self._act_japanese.triggered.connect(
            lambda checked: self._toggle_rule("request_japanese", checked)
        )
        rules_menu.addAction(self._act_japanese)

        self._act_auto_auth = QAction("자동 인증 (Automatically Authenticate)", self, checkable=True)
        self._act_auto_auth.triggered.connect(
            lambda checked: self._toggle_rule("auto_authenticate", checked)
        )
        rules_menu.addAction(self._act_auto_auth)

        rules_menu.addSeparator()

        # User-Agents submenu
        ua_menu = rules_menu.addMenu("User-Agents")

        act_ua_custom = QAction("User-Agent 변경...", self)
        act_ua_custom.triggered.connect(self._on_user_agent)
        ua_menu.addAction(act_ua_custom)

        # Performance submenu
        act_perf = QAction("성능 시뮬레이션 (Performance)...", self)
        act_perf.triggered.connect(self._on_performance)
        rules_menu.addAction(act_perf)

        rules_menu.addSeparator()

        act_customize = QAction("사용자 정의 규칙 (Customize Rules)...", self)
        act_customize.triggered.connect(self._on_customize_rules)
        rules_menu.addAction(act_customize)

        # 도구
        tools_menu = mb.addMenu("도구")
        tools_menu.addAction(QAction("옵션...", self))
        tools_menu.addSeparator()

        act_cert = QAction("인증서 관리자", self)
        act_cert.triggered.connect(self._on_cert_manager)
        tools_menu.addAction(act_cert)

        act_proxy_settings = QAction("프록시 설정...", self)
        act_proxy_settings.triggered.connect(self._on_proxy_settings)
        tools_menu.addAction(act_proxy_settings)

        tools_menu.addSeparator()
        tools_menu.addAction(QAction("WinConfig", self))

        # 보기
        view_menu = mb.addMenu("보기")

        act_show_toolbar = QAction("툴바 표시 (Show Toolbar)", self, checkable=True, checked=True)
        act_show_toolbar.triggered.connect(lambda v: self._toolbar.setVisible(v))
        view_menu.addAction(act_show_toolbar)

        view_menu.addSeparator()

        # Layout (exclusive group)
        layout_group = QActionGroup(self)
        layout_group.setExclusive(True)

        self._act_layout_default = QAction(
            "기본 레이아웃 (Default Layout)", self, checkable=True, checked=True)
        self._act_layout_default.triggered.connect(lambda: self._apply_layout("default"))
        layout_group.addAction(self._act_layout_default)
        view_menu.addAction(self._act_layout_default)

        self._act_layout_stacked = QAction("세로 레이아웃 (Stacked Layout)", self, checkable=True)
        self._act_layout_stacked.triggered.connect(lambda: self._apply_layout("stacked"))
        layout_group.addAction(self._act_layout_stacked)
        view_menu.addAction(self._act_layout_stacked)

        self._act_layout_wide = QAction("넓은 레이아웃 (Wide Layout)", self, checkable=True)
        self._act_layout_wide.triggered.connect(lambda: self._apply_layout("wide"))
        layout_group.addAction(self._act_layout_wide)
        view_menu.addAction(self._act_layout_wide)

        view_menu.addSeparator()

        # Tabs sub-menu
        tabs_menu = view_menu.addMenu("탭 (Tabs)")

        self._act_tab_stats = QAction("통계 (Statistics)", self, checkable=True, checked=True)
        self._act_tab_stats.triggered.connect(
            lambda v: self._toggle_right_tab(self._stats_panel, "통계", v))
        tabs_menu.addAction(self._act_tab_stats)

        self._act_tab_insp = QAction("인스펙터 (Inspectors)", self, checkable=True, checked=True)
        self._act_tab_insp.triggered.connect(
            lambda v: self._toggle_right_tab(self._inspector_container, "인스펙터", v))
        tabs_menu.addAction(self._act_tab_insp)

        self._act_tab_composer = QAction("컴포저 (Composer)", self, checkable=True, checked=True)
        self._act_tab_composer.triggered.connect(
            lambda v: self._toggle_right_tab(self._composer_panel, "컴포저", v))
        tabs_menu.addAction(self._act_tab_composer)

        view_menu.addSeparator()

        act_statistics = QAction(
            "통계 (Statistics)", self, shortcut=QKeySequence(Qt.Key.Key_F7))
        act_statistics.triggered.connect(lambda: self._switch_right_panel(self._stats_panel))
        view_menu.addAction(act_statistics)

        act_inspectors = QAction(
            "인스펙터 (Inspectors)", self, shortcut=QKeySequence(Qt.Key.Key_F8))
        act_inspectors.triggered.connect(
            lambda: self._switch_right_panel(self._inspector_container))
        view_menu.addAction(act_inspectors)

        act_composer_view = QAction(
            "컴포저 (Composer)", self, shortcut=QKeySequence(Qt.Key.Key_F9))
        act_composer_view.triggered.connect(
            lambda: self._switch_right_panel(self._composer_panel))
        view_menu.addAction(act_composer_view)

        view_menu.addSeparator()

        self._act_min_tray = QAction(
            "트레이로 최소화 (Minimize to Tray)", self, checkable=True)
        view_menu.addAction(self._act_min_tray)

        act_stay_top = QAction("항상 위 (Stay on Top)", self, checkable=True)
        act_stay_top.triggered.connect(self._on_stay_on_top)
        view_menu.addAction(act_stay_top)

        view_menu.addSeparator()

        act_squish = QAction(
            "세션 목록 압축 (Squish Session List)", self,
            shortcut=QKeySequence(Qt.Key.Key_F6), checkable=True)
        act_squish.triggered.connect(self._on_squish_sessions)
        view_menu.addAction(act_squish)

        self._act_autoscroll = QAction(
            "자동 스크롤 (AutoScroll Session List)", self, checkable=True, checked=True)
        self._act_autoscroll.triggered.connect(self._on_autoscroll_toggle)
        view_menu.addAction(self._act_autoscroll)

        view_menu.addSeparator()

        act_refresh = QAction(
            "새로 고침 (Refresh)", self, shortcut=QKeySequence(Qt.Key.Key_F5))
        act_refresh.triggered.connect(self._on_refresh)
        view_menu.addAction(act_refresh)

        # 도움말
        help_menu = mb.addMenu("도움말")

        act_welcome_screen = QAction("시작 화면으로 이동", self)
        act_welcome_screen.triggered.connect(self._on_help_welcome_screen)
        help_menu.addAction(act_welcome_screen)

        help_menu.addSeparator()

        act_help = QAction("도움말 (F1)", self, shortcut=QKeySequence(Qt.Key.Key_F1))
        act_help.triggered.connect(self._on_help_docs)
        help_menu.addAction(act_help)

        act_fiddler_book = QAction("Fiddler 학습 자료", self)
        act_fiddler_book.triggered.connect(self._on_help_fiddler_book)
        help_menu.addAction(act_fiddler_book)

        act_discussions = QAction("사용자 커뮤니티", self)
        act_discussions.triggered.connect(self._on_help_discussions)
        help_menu.addAction(act_discussions)

        act_http_ref = QAction("HTTP 참고 자료", self)
        act_http_ref.triggered.connect(self._on_help_http_references)
        help_menu.addAction(act_http_ref)

        help_menu.addSeparator()

        act_troubleshoot = QAction("문제 해결", self)
        act_troubleshoot.triggered.connect(self._on_help_troubleshoot)
        help_menu.addAction(act_troubleshoot)

        act_support = QAction("기술 지원 받기", self)
        act_support.triggered.connect(self._on_help_support)
        help_menu.addAction(act_support)

        help_menu.addSeparator()

        act_check_updates = QAction("업데이트 확인", self)
        act_check_updates.triggered.connect(self._on_help_check_updates)
        help_menu.addAction(act_check_updates)

        act_feedback = QAction("의견 보내기", self)
        act_feedback.triggered.connect(self._on_help_feedback)
        help_menu.addAction(act_feedback)

        help_menu.addSeparator()

        act_about = QAction("NetScope 정보", self)
        act_about.triggered.connect(self._on_help_about)
        help_menu.addAction(act_about)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._toolbar = Toolbar()
        root_layout.addWidget(self._toolbar)
        root_layout.addWidget(_h_line())

        self._h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter.setHandleWidth(2)

        self._table_view = SessionTableView(self._session_model)
        self._h_splitter.addWidget(self._table_view)

        # Right side: tabbed panel (Statistics / Inspectors / Composer)
        self._right_tabs = QTabWidget()
        self._right_tabs.setDocumentMode(True)
        self._right_tabs.currentChanged.connect(self._on_right_tab_changed)

        self._stats_panel = StatisticsPanel()
        self._right_tabs.addTab(self._stats_panel, "통계")

        # Inspectors tab wraps the welcome/detail stack
        self._inspector_container = QWidget()
        _insp_layout = QVBoxLayout(self._inspector_container)
        _insp_layout.setContentsMargins(0, 0, 0, 0)
        _insp_layout.setSpacing(0)
        self._right_stack = QStackedWidget()
        self._welcome_panel = WelcomePanel()
        self._detail_panel  = DetailPanel()
        self._right_stack.addWidget(self._welcome_panel)
        self._right_stack.addWidget(self._detail_panel)
        self._right_stack.setCurrentIndex(0)
        _insp_layout.addWidget(self._right_stack)
        self._right_tabs.addTab(self._inspector_container, "인스펙터")

        self._composer_panel = ComposerPanel()
        self._right_tabs.addTab(self._composer_panel, "컴포저")

        self._right_tabs.setCurrentIndex(1)   # default to Inspectors

        self._h_splitter.addWidget(self._right_tabs)
        self._h_splitter.setSizes([360, 1040])
        self._h_splitter.setStretchFactor(0, 0)
        self._h_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._h_splitter, stretch=1)

        self._setup_tray()

        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self._status_bar)

        self._cap_label     = QLabel(_STATUS_IDLE)
        self._port_label    = _status_sep(f"포트  {self._proxy_port}")
        self._process_label = _status_sep("프로세스  전체")
        self._count_label   = _status_sep("세션  0")

        self._status_bar.addWidget(self._cap_label, stretch=1)
        self._status_bar.addPermanentWidget(self._process_label)
        self._status_bar.addPermanentWidget(self._port_label)
        self._status_bar.addPermanentWidget(self._count_label)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        self._toolbar.start_clicked.connect(self._on_start)
        self._toolbar.stop_clicked.connect(self._on_stop)
        self._toolbar.clear_clicked.connect(self._on_clear)
        self._toolbar.search_changed.connect(self._table_view.set_filter)
        self._toolbar.process_changed.connect(self._on_process_changed)

        self._table_view.session_selected.connect(self._on_session_selected)
        self._table_view.set_rules(self._rules)

        self._engine.session_started.connect(
            self._on_session_started, Qt.ConnectionType.QueuedConnection)
        self._engine.session_completed.connect(
            self._on_session_completed, Qt.ConnectionType.QueuedConnection)
        self._engine.status_changed.connect(
            self._on_status_changed, Qt.ConnectionType.QueuedConnection)
        self._engine.breakpoint_request.connect(
            self._on_breakpoint, Qt.ConnectionType.QueuedConnection)

    # ── Rule helpers ──────────────────────────────────────────────────────────

    def _toggle_rule(self, attr: str, enabled: bool):
        setattr(self._rules, attr, enabled)
        self._rules.notify()

    # ── Rules menu slots ──────────────────────────────────────────────────────

    @Slot()
    def _on_rules_manager(self):
        dlg = RulesManagerDialog(self._rules, self)
        if dlg.exec():
            self._sync_menu_checks()

    @Slot()
    def _on_customize_rules(self):
        CustomizeRulesDialog(self._rules, self).exec()

    @Slot()
    def _on_user_agent(self):
        UserAgentDialog(self._rules, self).exec()

    @Slot()
    def _on_performance(self):
        PerformanceDialog(self._rules, self).exec()

    @Slot()
    def _on_proxy_settings(self):
        dlg = ProxySettingsDialog(
            port=self._proxy_port,
            auto_proxy=self._auto_set_proxy,
            use_real_engine=self._use_real_engine,
            mitm_available=MitmproxyEngine.AVAILABLE,
            parent=self,
        )
        if dlg.exec() != ProxySettingsDialog.DialogCode.Accepted:
            return

        new_port = dlg.get_port()
        new_auto = dlg.get_auto_proxy()
        new_real = dlg.get_use_real_engine()

        engine_changed = new_real != self._use_real_engine
        was_running = self._engine.is_running()

        if was_running:
            self._stop_capture()

        self._proxy_port = new_port
        self._auto_set_proxy = new_auto
        self._use_real_engine = new_real
        self._port_label.setText(f"포트  {self._proxy_port}")

        if engine_changed:
            self._engine.deleteLater()
            self._engine = self._create_engine()
            self._engine.set_rules(self._rules)
            self._engine.session_started.connect(
                self._on_session_started, Qt.ConnectionType.QueuedConnection)
            self._engine.session_completed.connect(
                self._on_session_completed, Qt.ConnectionType.QueuedConnection)
            self._engine.status_changed.connect(
                self._on_status_changed, Qt.ConnectionType.QueuedConnection)
            self._engine.breakpoint_request.connect(
                self._on_breakpoint, Qt.ConnectionType.QueuedConnection)
            kind = "실제 mitmproxy" if new_real else "스텁(테스트)"
            QMessageBox.information(
                self, "엔진 변경",
                f"프록시 엔진이 [{kind}]으로 변경되었습니다.",
            )

        if was_running:
            self._start_capture()

    @Slot()
    def _on_cert_manager(self):
        import sys
        from netscope.utils.system_proxy import install_ca_cert_windows, get_ca_cert_path
        if sys.platform != "win32":
            QMessageBox.information(
                self, "인증서 관리자",
                "Windows에서만 자동 설치를 지원합니다.\n"
                "CA 인증서 위치: ~/.mitmproxy/mitmproxy-ca-cert.pem",
            )
            return
        ok, msg = install_ca_cert_windows()
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "인증서 관리자", msg, parent=self).exec()

    def _sync_menu_checks(self):
        """Sync checkable menu items with current rules state (after dialog edits)."""
        self._act_hide_images.setChecked(self._rules.hide_image_requests)
        self._act_hide_connects.setChecked(self._rules.hide_connects)
        self._act_hide_304s.setChecked(self._rules.hide_304s)
        self._act_bp_req.setChecked(self._rules.breakpoint_requests)
        self._act_bp_resp.setChecked(self._rules.breakpoint_responses)
        self._act_gzip.setChecked(self._rules.apply_gzip)
        self._act_remove_enc.setChecked(self._rules.remove_encodings)
        self._act_japanese.setChecked(self._rules.request_japanese)
        self._act_auto_auth.setChecked(self._rules.auto_authenticate)
        self._act_proxy_auth.setChecked(self._rules.require_proxy_auth)

    # ── Breakpoint slot ───────────────────────────────────────────────────────

    @Slot(int)
    def _on_breakpoint(self, session_id: int):
        session = self._engine.get_pending_session(session_id)
        if session is None:
            self._engine.resume_breakpoint(session_id)
            return
        dlg = BreakpointDialog(session, self)
        dlg.exec()
        if dlg.was_aborted():
            self._engine.resume_breakpoint(session_id)
        else:
            self._engine.resume_breakpoint(
                session_id,
                modified_headers=dlg.get_modified_headers(),
                modified_body=dlg.get_modified_body(),
            )

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_capture_toggle(self, checked: bool):
        if checked:
            self._start_capture()
        else:
            self._stop_capture()

    @Slot()
    def _on_new_viewer(self):
        win = MainWindow()
        win.show()
        # Keep a reference so it isn't GC'd immediately
        if not hasattr(QApplication.instance(), "_extra_windows"):
            QApplication.instance()._extra_windows = []
        QApplication.instance()._extra_windows.append(win)

    @Slot()
    def _on_load_archive(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "아카이브 불러오기", "",
            "지원 형식 (*.netsession *.saz);;"
            "NetScope 세션 (*.netsession);;"
            "Fiddler 아카이브 (*.saz);;"
            "모든 파일 (*)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".saz"):
                sessions = load_saz(path)
                self._session_model.load_sessions(sessions)
                self._right_stack.setCurrentIndex(0)
                self._count_label.setText(f"세션  {len(sessions)}")
                self._current_file = None   # SAZ is read-only; don't overwrite
                self._modified = False
                self._update_title()
            else:
                self._load_file(path)
            self._add_to_recent(path)
        except Exception as exc:
            QMessageBox.critical(self, "불러오기 실패", f"파일을 열 수 없습니다:\n{exc}")

    def _add_to_recent(self, path: str):
        path = str(Path(path).resolve())
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:_RECENT_MAX]
        _save_recent_config(self._recent_files)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        if not self._recent_files:
            empty = QAction("(없음)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for path in self._recent_files:
            label = Path(path).name
            act = QAction(label, self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked, p=path: self._open_recent(p))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        act_clear = QAction("목록 지우기", self)
        act_clear.triggered.connect(self._clear_recent)
        self._recent_menu.addAction(act_clear)

    def _open_recent(self, path: str):
        if not Path(path).exists():
            QMessageBox.warning(self, "파일 없음", f"파일을 찾을 수 없습니다:\n{path}")
            self._recent_files = [p for p in self._recent_files if p != path]
            _save_recent_config(self._recent_files)
            self._rebuild_recent_menu()
            return
        if not self._confirm_discard():
            return
        try:
            if path.lower().endswith(".saz"):
                sessions = load_saz(path)
                self._session_model.load_sessions(sessions)
                self._right_stack.setCurrentIndex(0)
                self._count_label.setText(f"세션  {len(sessions)}")
                self._current_file = None
                self._modified = False
                self._update_title()
            else:
                self._load_file(path)
            self._add_to_recent(path)
        except Exception as exc:
            QMessageBox.critical(self, "열기 실패", f"파일을 열 수 없습니다:\n{exc}")

    def _clear_recent(self):
        self._recent_files.clear()
        _save_recent_config(self._recent_files)
        self._rebuild_recent_menu()

    def _create_engine(self) -> ProxyEngine:
        """Create the appropriate proxy engine based on current settings."""
        if self._use_real_engine and MitmproxyEngine.AVAILABLE:
            engine = MitmproxyEngine(self)
        else:
            engine = StubProxyEngine(self)
        return engine

    def _start_capture(self):
        self._toolbar.set_capturing(True)
        self._act_capture.setChecked(True)
        self._cap_label.setText(_STATUS_CAPTURE)
        self._cap_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        if self._auto_set_proxy and self._use_real_engine:
            ok = set_system_proxy("127.0.0.1", self._proxy_port)
            if not ok:
                QMessageBox.warning(
                    self, "시스템 프록시",
                    "시스템 프록시 자동 등록에 실패했습니다.\n"
                    "브라우저에서 수동으로 127.0.0.1:"
                    f"{self._proxy_port}로 설정해 주세요.",
                )
        self._engine.start(self._proxy_port)

    def _stop_capture(self):
        self._engine.stop()
        if self._auto_set_proxy and self._use_real_engine:
            clear_system_proxy()
        self._toolbar.set_capturing(False)
        self._act_capture.setChecked(False)
        self._cap_label.setText(_STATUS_IDLE)
        self._cap_label.setStyleSheet("color: #666666;")

    @Slot()
    def _on_start(self):
        self._start_capture()

    @Slot()
    def _on_stop(self):
        self._stop_capture()

    @Slot()
    def _on_clear(self):
        self._session_model.clear()
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText("세션  0")
        self._modified = False
        self._update_title()

    @Slot(int)
    def _on_session_selected(self, row: int):
        session = self._session_model.get_session(row)
        if session:
            self._detail_panel.show_session(session)
            self._right_stack.setCurrentIndex(1)
            self._switch_right_panel(self._inspector_container)

    @Slot(SessionEntry)
    def _on_session_started(self, session: SessionEntry):
        self._session_model.add_session(session)
        self._count_label.setText(f"세션  {self._session_model.rowCount()}")
        if self._auto_scroll:
            self._table_view.scroll_to_bottom()
        self._mark_modified()

    @Slot(int, dict)
    def _on_session_completed(self, session_id: int, fields: dict):
        self._session_model.update_session(session_id, **fields)

    @Slot(str)
    def _on_status_changed(self, status: str):
        pass

    @Slot(str)
    def _on_process_changed(self, text: str):
        label = "전체" if text == "전체 프로세스" else text
        self._process_label.setText(f"프로세스  {label}")

    # ── Edit menu slots ───────────────────────────────────────────────────────

    @Slot()
    def _on_edit_copy_url(self):
        sessions = self._table_view.get_selected_sessions()
        if sessions:
            QApplication.clipboard().setText("\n".join(s.url for s in sessions))

    @Slot()
    def _on_edit_copy_headers(self):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            return
        parts = []
        for s in sessions:
            parts.append(f"=== Session #{s.id} ===")
            parts.append("Request Headers:")
            parts.extend(f"  {k}: {v}" for k, v in s.request_headers.items())
            parts.append("Response Headers:")
            parts.extend(f"  {k}: {v}" for k, v in s.response_headers.items())
        QApplication.clipboard().setText("\n".join(parts))

    @Slot()
    def _on_edit_copy_request(self):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            return
        parts = []
        for s in sessions:
            parts.append(f"{s.method} {s.path} HTTP/1.1")
            parts.extend(f"{k}: {v}" for k, v in s.request_headers.items())
            parts.append("")
            if s.request_body:
                parts.append(s.request_body.decode("utf-8", errors="replace"))
        QApplication.clipboard().setText("\n".join(parts))

    @Slot()
    def _on_edit_copy_response(self):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            return
        parts = []
        for s in sessions:
            parts.append(f"HTTP/1.1 {s.status_code}")
            parts.extend(f"{k}: {v}" for k, v in s.response_headers.items())
            parts.append("")
            if s.response_body:
                parts.append(s.response_body.decode("utf-8", errors="replace"))
        QApplication.clipboard().setText("\n".join(parts))

    @Slot()
    def _on_edit_copy_full(self):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            return
        parts = []
        for s in sessions:
            parts.append(f"=== Session #{s.id}: {s.method} {s.url} ===")
            parts.append(f"Status: {s.status_code}")
            parts.append("")
            parts.append("--- Request Headers ---")
            parts.extend(f"{k}: {v}" for k, v in s.request_headers.items())
            if s.request_body:
                parts.append("")
                parts.append("--- Request Body ---")
                parts.append(s.request_body.decode("utf-8", errors="replace"))
            parts.append("")
            parts.append("--- Response Headers ---")
            parts.extend(f"{k}: {v}" for k, v in s.response_headers.items())
            if s.response_body:
                parts.append("")
                parts.append("--- Response Body ---")
                parts.append(s.response_body.decode("utf-8", errors="replace"))
            parts.append("")
        QApplication.clipboard().setText("\n".join(parts))

    @Slot()
    def _on_edit_remove_selected(self):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            return
        self._session_model.remove_sessions_by_id({s.id for s in sessions})
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText(f"세션  {self._session_model.rowCount()}")
        self._act_undelete.setEnabled(True)
        self._mark_modified()

    @Slot()
    def _on_edit_remove_unselected(self):
        selected = self._table_view.get_selected_sessions()
        if not selected:
            return
        selected_ids = {s.id for s in selected}
        ids_to_remove = {
            s.id for s in self._session_model.get_all_sessions()
            if s.id not in selected_ids
        }
        if ids_to_remove:
            self._session_model.remove_sessions_by_id(ids_to_remove)
            self._right_stack.setCurrentIndex(0)
            self._count_label.setText(f"세션  {self._session_model.rowCount()}")
            self._act_undelete.setEnabled(True)
            self._mark_modified()

    @Slot()
    def _on_edit_remove_all(self):
        all_sessions = self._session_model.get_all_sessions()
        if not all_sessions:
            return
        self._session_model.remove_sessions_by_id({s.id for s in all_sessions})
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText("세션  0")
        self._act_undelete.setEnabled(True)
        self._mark_modified()

    @Slot()
    def _on_edit_select_all(self):
        self._table_view.selectAll()

    @Slot()
    def _on_edit_undelete(self):
        if self._session_model.restore_last_deleted():
            self._count_label.setText(f"세션  {self._session_model.rowCount()}")
            self._mark_modified()
        if not self._session_model.has_undo():
            self._act_undelete.setEnabled(False)

    @Slot()
    def _on_edit_paste_as_sessions(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            QMessageBox.information(self, "붙여넣기", "클립보드에 HTTP 데이터가 없습니다.")
            return
        sessions = self._parse_http_from_clipboard(text)
        if not sessions:
            QMessageBox.warning(
                self, "붙여넣기 실패",
                "클립보드 내용을 HTTP 세션으로 파싱할 수 없습니다.\n\n"
                "형식 예시:\n  GET /path HTTP/1.1\n  Host: example.com\n  ...",
            )
            return
        for s in sessions:
            self._session_model.add_session(s)
        self._count_label.setText(f"세션  {self._session_model.rowCount()}")
        self._table_view.scroll_to_bottom()
        self._mark_modified()

    def _on_edit_mark(self, color: str | None):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            return
        for s in sessions:
            s.mark_color = color
        self._session_model.refresh_all()
        self._mark_modified()

    @Slot()
    def _on_edit_unlock(self):
        sessions = self._table_view.get_selected_sessions()
        if not sessions:
            QMessageBox.information(self, "편집 모드", "편집할 세션을 먼저 선택하세요.")
            return
        from netscope.ui.dialogs.edit_session_dialog import EditSessionDialog
        dlg = EditSessionDialog(sessions[0], self)
        if dlg.exec():
            self._session_model.notify_session_changed(sessions[0].id)
            self._detail_panel.show_session(sessions[0])
            self._mark_modified()

    @Slot()
    def _on_find_sessions(self):
        from netscope.ui.dialogs.find_sessions_dialog import FindSessionsDialog
        dlg = FindSessionsDialog(self._session_model.get_all_sessions(), self)
        dlg.session_selected.connect(self._table_view.select_session_by_id)
        dlg.exec()

    def _parse_http_from_clipboard(self, text: str) -> list[SessionEntry]:
        _METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "CONNECT", "TRACE"}
        lines = text.replace("\r\n", "\n").split("\n")
        if not lines:
            return []
        req_parts = lines[0].strip().split(" ", 2)
        if len(req_parts) < 2 or req_parts[0].upper() not in _METHODS:
            return []
        method = req_parts[0].upper()
        path = req_parts[1]
        headers: dict[str, str] = {}
        body_start = len(lines)
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "":
                body_start = i + 1
                break
            if ": " in line:
                k, _, v = line.partition(": ")
                k = k.strip()
                if k:
                    headers[k] = v.strip()
        body = "\n".join(lines[body_start:]).strip()
        host = headers.get("Host", "")
        scheme = "https" if host.endswith(":443") else "http"
        url = f"{scheme}://{host}{path}" if host else path
        return [SessionEntry(
            id=0,
            method=method,
            scheme=scheme,
            host=host,
            path=path,
            url=url,
            state=SessionState.PENDING,
            request_headers=headers,
            request_body=body.encode("utf-8"),
        )]

    # ── File operations ───────────────────────────────────────────────────────

    @Slot()
    def _on_new(self):
        if not self._confirm_discard():
            return
        if self._engine.is_running():
            self._engine.stop()
            self._toolbar.set_capturing(False)
            self._cap_label.setText(_STATUS_IDLE)
            self._cap_label.setStyleSheet("color: #666666;")
        self._session_model.clear()
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText("세션  0")
        self._current_file = None
        self._modified = False
        self._update_title()

    @Slot()
    def _on_save(self):
        if self._current_file:
            try:
                self._write_file(self._current_file)
            except Exception as exc:
                QMessageBox.critical(self, "저장 실패", f"파일을 저장할 수 없습니다:\n{exc}")
        else:
            self._on_save_as()

    @Slot()
    def _on_save_as(self):
        default = Path(self._current_file).stem if self._current_file else "세션"
        path, _ = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장", default,
            "NetScope 세션 (*.netsession);;모든 파일 (*)",
        )
        if not path:
            return
        if not path.endswith(".netsession"):
            path += ".netsession"
        try:
            self._write_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "저장 실패", f"파일을 저장할 수 없습니다:\n{exc}")

    @Slot()
    def _on_import(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "HAR 가져오기", "",
            "HTTP Archive (*.har);;모든 파일 (*)",
        )
        if not path:
            return
        try:
            self._import_har(path)
        except Exception as exc:
            QMessageBox.critical(self, "가져오기 실패", f"HAR 파일을 가져올 수 없습니다:\n{exc}")

    @Slot()
    def _on_export(self):
        if self._session_model.rowCount() == 0:
            QMessageBox.information(self, "내보내기", "내보낼 세션이 없습니다.")
            return
        default = Path(self._current_file).stem if self._current_file else "세션"
        path, _ = QFileDialog.getSaveFileName(
            self, "HAR 내보내기", default,
            "HTTP Archive (*.har);;모든 파일 (*)",
        )
        if not path:
            return
        if not path.endswith(".har"):
            path += ".har"
        try:
            self._export_har(path)
            QMessageBox.information(self, "내보내기 완료", f"HAR 파일로 저장되었습니다:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "내보내기 실패", f"HAR 파일을 저장할 수 없습니다:\n{exc}")

    # ── File I/O helpers ──────────────────────────────────────────────────────

    def _load_file(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != 1:
            raise ValueError("지원하지 않는 파일 형식입니다.")
        sessions = [_session_from_dict(d) for d in data.get("sessions", [])]
        self._session_model.load_sessions(sessions)
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText(f"세션  {len(sessions)}")
        self._current_file = path
        self._modified = False
        self._update_title()

    def _write_file(self, path: str):
        data = {
            "version": 1,
            "sessions": [_session_to_dict(s) for s in self._session_model.get_all_sessions()],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._current_file = path
        self._modified = False
        self._update_title()
        self._add_to_recent(path)

    def _import_har(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            har = json.load(f)
        entries = har.get("log", {}).get("entries", [])
        sessions: list[SessionEntry] = []
        for i, entry in enumerate(entries, start=1):
            req = entry.get("request", {})
            resp = entry.get("response", {})
            url = req.get("url", "")
            from urllib.parse import urlparse
            parsed = urlparse(url)
            req_headers = {h["name"]: h["value"] for h in req.get("headers", [])}
            resp_headers = {h["name"]: h["value"] for h in resp.get("headers", [])}
            req_body_text = (req.get("postData") or {}).get("text", "")
            resp_body_text = (resp.get("content") or {}).get("text", "")
            body_size = resp.get("bodySize", 0) or 0
            elapsed = entry.get("timings", {}).get("wait", 0) or 0
            status = resp.get("status", 0)
            content_type = resp_headers.get("Content-Type", "")
            s = SessionEntry(
                id=i,
                method=req.get("method", "GET"),
                scheme=parsed.scheme or "https",
                host=parsed.netloc,
                path=parsed.path or "/",
                url=url,
                status_code=status,
                content_type=content_type,
                body_size=body_size,
                elapsed_ms=float(elapsed),
                state=SessionState.COMPLETE if status < 500 else SessionState.ERROR,
                request_headers=req_headers,
                request_body=req_body_text.encode("utf-8", errors="replace"),
                response_headers=resp_headers,
                response_body=resp_body_text.encode("utf-8", errors="replace"),
            )
            sessions.append(s)
        self._session_model.load_sessions(sessions)
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText(f"세션  {len(sessions)}")
        self._current_file = None
        self._modified = False
        self._update_title()

    def _export_har(self, path: str):
        import datetime
        entries = []
        for s in self._session_model.get_all_sessions():
            req_headers = [{"name": k, "value": v} for k, v in s.request_headers.items()]
            resp_headers = [{"name": k, "value": v} for k, v in s.response_headers.items()]
            entries.append({
                "startedDateTime": datetime.datetime.utcnow().isoformat() + "Z",
                "time": s.elapsed_ms,
                "request": {
                    "method": s.method,
                    "url": s.url,
                    "httpVersion": "HTTP/1.1",
                    "headers": req_headers,
                    "queryString": [],
                    "cookies": [],
                    "headersSize": -1,
                    "bodySize": len(s.request_body),
                    "postData": {"mimeType": "", "text": s.request_body.decode("utf-8", errors="replace")} if s.request_body else None,
                },
                "response": {
                    "status": s.status_code,
                    "statusText": "",
                    "httpVersion": "HTTP/1.1",
                    "headers": resp_headers,
                    "cookies": [],
                    "content": {
                        "size": s.body_size,
                        "mimeType": s.content_type,
                        "text": s.response_body.decode("utf-8", errors="replace"),
                    },
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": s.body_size,
                },
                "cache": {},
                "timings": {"send": 0, "wait": s.elapsed_ms, "receive": 0},
            })
        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "NetScope", "version": "1.0"},
                "entries": entries,
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(har, f, ensure_ascii=False, indent=2)

    # ── UI state helpers ──────────────────────────────────────────────────────

    def _mark_modified(self):
        if not self._modified:
            self._modified = True
            self._update_title()

    def _update_title(self):
        name = Path(self._current_file).name if self._current_file else "새 세션"
        suffix = " *" if self._modified else ""
        self.setWindowTitle(f"NetScope — {name}{suffix}")

    def _confirm_discard(self) -> bool:
        if not self._modified:
            return True
        answer = QMessageBox.question(
            self,
            "변경 사항 저장",
            "저장하지 않은 변경 사항이 있습니다.\n저장하시겠습니까?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._modified
        if answer == QMessageBox.StandardButton.Discard:
            return True
        return False

    # ── Tray icon setup ───────────────────────────────────────────────────────

    def _setup_tray(self):
        if not _TRAY_AVAILABLE:
            return
        _icon_path = (
            Path(__file__).parent.parent / "resources" / "icons" / "NetScope_32x32.png"
        )
        icon = QIcon(str(_icon_path)) if _icon_path.exists() else QIcon()
        self._tray_icon = QSystemTrayIcon(icon, self)
        self._tray_icon.setToolTip("NetScope")

        tray_menu = QMenu(self)
        act_restore = QAction("열기 (Restore)", self)
        act_restore.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(act_restore)
        tray_menu.addSeparator()
        act_tray_quit = QAction("종료 (Exit)", self)
        act_tray_quit.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(act_tray_quit)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _restore_from_tray(self):
        if self._tray_icon:
            self._tray_icon.hide()
        self.showNormal()
        self.activateWindow()

    @Slot(object)
    def _on_tray_activated(self, reason):
        if _TRAY_AVAILABLE and reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def changeEvent(self, event):
        if (event.type() == QEvent.Type.WindowStateChange
                and self.isMinimized()
                and self._tray_icon is not None
                and self._act_min_tray.isChecked()):
            event.ignore()
            self.hide()
            self._tray_icon.show()
            return
        super().changeEvent(event)

    # ── View menu slots ───────────────────────────────────────────────────────

    def _apply_layout(self, layout: str):
        if layout == "default":
            self._h_splitter.setOrientation(Qt.Orientation.Horizontal)
            self._h_splitter.setSizes([360, 1040])
            self._h_splitter.setStretchFactor(0, 0)
            self._h_splitter.setStretchFactor(1, 1)
        elif layout == "stacked":
            self._h_splitter.setOrientation(Qt.Orientation.Vertical)
            self._h_splitter.setSizes([260, 560])
            self._h_splitter.setStretchFactor(0, 0)
            self._h_splitter.setStretchFactor(1, 1)
        elif layout == "wide":
            self._h_splitter.setOrientation(Qt.Orientation.Horizontal)
            self._h_splitter.setSizes([200, 1200])
            self._h_splitter.setStretchFactor(0, 0)
            self._h_splitter.setStretchFactor(1, 1)

    def _switch_right_panel(self, widget: QWidget):
        idx = self._right_tabs.indexOf(widget)
        if idx >= 0:
            self._right_tabs.setCurrentIndex(idx)

    def _toggle_right_tab(self, widget: QWidget, title: str, visible: bool):
        idx = self._right_tabs.indexOf(widget)
        if visible and idx == -1:
            # Re-insert at the canonical position
            _order = [self._stats_panel, self._inspector_container, self._composer_panel]
            insert_pos = sum(
                1 for p in _order
                if p is not widget and self._right_tabs.indexOf(p) >= 0
                and _order.index(p) < _order.index(widget)
            )
            self._right_tabs.insertTab(insert_pos, widget, title)
        elif not visible and idx >= 0:
            self._right_tabs.removeTab(idx)

    @Slot(int)
    def _on_right_tab_changed(self, index: int):
        widget = self._right_tabs.widget(index)
        if widget is self._stats_panel:
            self._stats_panel.update_stats(self._session_model.get_all_sessions())

    @Slot(bool)
    def _on_stay_on_top(self, checked: bool):
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    @Slot(bool)
    def _on_squish_sessions(self, checked: bool):
        self._table_view.set_squished(checked)

    @Slot(bool)
    def _on_autoscroll_toggle(self, checked: bool):
        self._auto_scroll = checked

    @Slot()
    def _on_refresh(self):
        self._session_model.refresh_all()
        self._count_label.setText(f"세션  {self._session_model.rowCount()}")
        widget = self._right_tabs.currentWidget()
        if widget is self._stats_panel:
            self._stats_panel.update_stats(self._session_model.get_all_sessions())

    # ── Help handlers ─────────────────────────────────────────────────────────

    @Slot()
    def _on_help_welcome_screen(self):
        """Welcome Screen으로 이동 — Inspector 탭에서 시작 화면을 표시."""
        # Inspectors 탭으로 전환 후 welcome 패널을 전면에 표시
        for i in range(self._right_tabs.count()):
            if self._right_tabs.tabText(i) == "인스펙터":
                self._right_tabs.setCurrentIndex(i)
                break
        self._right_stack.setCurrentWidget(self._welcome_panel)

    @Slot()
    def _on_help_docs(self):
        """도움말/사용 설명서 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("NetScope 도움말")
        dlg.resize(640, 480)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml("""
        <h2>NetScope 도움말</h2>
        <h3>기본 사용법</h3>
        <ul>
            <li><b>F12</b> — 트래픽 캡처 시작/중지</li>
            <li><b>Ctrl+O</b> — 아카이브 파일(.netsession, .saz) 불러오기</li>
            <li><b>Ctrl+S</b> — 현재 세션 저장</li>
            <li><b>Ctrl+F</b> — 세션 검색</li>
            <li><b>Delete</b> — 선택한 세션 삭제</li>
            <li><b>F2</b> — 선택한 세션 편집</li>
            <li><b>F5</b> — 화면 새로 고침</li>
            <li><b>F6</b> — 세션 목록 압축(Squish) 토글</li>
            <li><b>F7</b> — 통계 탭으로 전환</li>
            <li><b>F8</b> — 인스펙터 탭으로 전환</li>
            <li><b>F9</b> — 컴포저 탭으로 전환</li>
        </ul>
        <h3>세션 분석</h3>
        <ul>
            <li>세션을 클릭하면 오른쪽 패널에서 요청/응답 헤더와 본문을 확인할 수 있습니다.</li>
            <li>규칙(Rules) 메뉴에서 필터와 수정 규칙을 설정할 수 있습니다.</li>
            <li>컴포저(Composer) 탭을 사용하여 HTTP 요청을 직접 작성하고 전송할 수 있습니다.</li>
        </ul>
        <h3>파일 형식</h3>
        <ul>
            <li><b>.netsession</b> — NetScope 기본 저장 형식 (JSON)</li>
            <li><b>.saz</b> — Fiddler 아카이브 파일 (읽기 지원)</li>
            <li><b>.har</b> — HTTP Archive 형식 (가져오기/내보내기 지원)</li>
        </ul>
        """)
        layout.addWidget(browser)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_fiddler_book(self):
        """Fiddler 학습 자료 안내 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Fiddler 학습 자료")
        dlg.setFixedSize(440, 200)
        layout = QVBoxLayout(dlg)
        label = QLabel(
            "<b>Fiddler 학습 자료</b>는 외부 링크를 통해 제공됩니다.<br><br>"
            "HTTP 디버깅 및 네트워크 트래픽 분석에 관심이 있으시다면<br>"
            "Telerik Fiddler 공식 문서와 도서를 참고하시기 바랍니다.<br><br>"
            "<i>현재 버전에서는 외부 브라우저 연결 기능이 준비 중입니다.</i>"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_discussions(self):
        """사용자 커뮤니티 안내 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("사용자 커뮤니티")
        dlg.setFixedSize(400, 180)
        layout = QVBoxLayout(dlg)
        label = QLabel(
            "<b>NetScope 사용자 커뮤니티</b><br><br>"
            "질문, 제안, 팁 공유를 위한 토론 공간에 참여하세요.<br><br>"
            "<i>현재 버전에서는 커뮤니티 연결 기능이 준비 중입니다.</i>"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_http_references(self):
        """HTTP 참고 자료 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("HTTP 참고 자료")
        dlg.resize(580, 420)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setHtml("""
        <h2>HTTP 참고 자료</h2>
        <h3>주요 상태 코드</h3>
        <table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
          <tr><th>코드</th><th>설명</th></tr>
          <tr><td>200</td><td>OK — 요청 성공</td></tr>
          <tr><td>201</td><td>Created — 리소스 생성됨</td></tr>
          <tr><td>204</td><td>No Content — 내용 없음</td></tr>
          <tr><td>301</td><td>Moved Permanently — 영구 리다이렉트</td></tr>
          <tr><td>302</td><td>Found — 임시 리다이렉트</td></tr>
          <tr><td>304</td><td>Not Modified — 캐시 유효</td></tr>
          <tr><td>400</td><td>Bad Request — 잘못된 요청</td></tr>
          <tr><td>401</td><td>Unauthorized — 인증 필요</td></tr>
          <tr><td>403</td><td>Forbidden — 접근 거부</td></tr>
          <tr><td>404</td><td>Not Found — 리소스 없음</td></tr>
          <tr><td>500</td><td>Internal Server Error — 서버 오류</td></tr>
          <tr><td>502</td><td>Bad Gateway — 게이트웨이 오류</td></tr>
          <tr><td>503</td><td>Service Unavailable — 서비스 불가</td></tr>
        </table>
        <h3>주요 HTTP 메서드</h3>
        <ul>
          <li><b>GET</b> — 리소스 조회</li>
          <li><b>POST</b> — 데이터 전송/생성</li>
          <li><b>PUT</b> — 리소스 전체 업데이트</li>
          <li><b>PATCH</b> — 리소스 부분 업데이트</li>
          <li><b>DELETE</b> — 리소스 삭제</li>
          <li><b>HEAD</b> — 헤더만 조회</li>
          <li><b>OPTIONS</b> — 허용 메서드 확인</li>
          <li><b>CONNECT</b> — 터널 연결 (HTTPS 프록시)</li>
        </ul>
        """)
        layout.addWidget(browser)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_troubleshoot(self):
        """문제 해결 도구 다이얼로그."""
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QGroupBox, QLabel,
            QPushButton, QTextEdit, QVBoxLayout,
        )
        import sys
        dlg = QDialog(self)
        dlg.setWindowTitle("문제 해결")
        dlg.resize(520, 400)
        layout = QVBoxLayout(dlg)

        info_box = QGroupBox("시스템 정보")
        info_layout = QVBoxLayout(info_box)
        sessions_count = self._session_model.rowCount()
        engine_running = self._engine.is_running()
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setPlainText(
            f"Python 버전: {sys.version}\n"
            f"프록시 포트: {self._proxy_port}\n"
            f"캡처 상태: {'실행 중' if engine_running else '대기 중'}\n"
            f"현재 세션 수: {sessions_count}\n"
            f"현재 파일: {self._current_file or '(없음)'}\n"
            f"자동 스크롤: {'켜짐' if self._auto_scroll else '꺼짐'}\n"
        )
        info_layout.addWidget(info_text)
        layout.addWidget(info_box)

        clear_btn = QPushButton("세션 목록 초기화")
        clear_btn.clicked.connect(lambda: (
            self._session_model.clear(),
            info_text.setPlainText(info_text.toPlainText() + "\n[세션 목록이 초기화되었습니다]"),
        ))
        layout.addWidget(clear_btn)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_support(self):
        """기술 지원 안내 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("기술 지원 받기")
        dlg.setFixedSize(400, 180)
        layout = QVBoxLayout(dlg)
        label = QLabel(
            "<b>기술 지원</b><br><br>"
            "기술 지원이 필요하신 경우 이슈 트래커를 통해 문의하시거나<br>"
            "프로젝트 관리자에게 직접 연락하시기 바랍니다.<br><br>"
            "<i>현재 버전에서는 지원 채널 연결 기능이 준비 중입니다.</i>"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_check_updates(self):
        """업데이트 확인 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("업데이트 확인")
        dlg.setFixedSize(380, 160)
        layout = QVBoxLayout(dlg)
        label = QLabel(
            "<b>업데이트 확인</b><br><br>"
            "현재 설치된 버전이 최신 버전입니다.<br><br>"
            "<i>자동 업데이트 확인 기능이 준비 중입니다.</i>"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_feedback(self):
        """피드백 전송 다이얼로그."""
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QLabel,
            QLineEdit, QTextEdit, QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("의견 보내기")
        dlg.resize(460, 300)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("제목:"))
        subject_edit = QLineEdit()
        subject_edit.setPlaceholderText("피드백 제목을 입력하세요")
        layout.addWidget(subject_edit)

        layout.addWidget(QLabel("내용:"))
        body_edit = QTextEdit()
        body_edit.setPlaceholderText("의견, 버그 보고, 개선 요청 등을 자유롭게 작성해 주세요.")
        layout.addWidget(body_edit)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(lambda: (
            QMessageBox.information(dlg, "전송 완료", "피드백이 접수되었습니다. 감사합니다."),
            dlg.accept(),
        ))
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        dlg.exec()

    @Slot()
    def _on_help_about(self):
        """프로그램 정보 다이얼로그."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("NetScope 정보")
        dlg.setFixedSize(420, 260)
        layout = QVBoxLayout(dlg)
        label = QLabel(
            "<h2>NetScope</h2>"
            "<b>네트워크 트래픽 인스펙터</b><br><br>"
            "버전: 1.0.0<br>"
            "빌드: 2025<br><br>"
            "HTTP/HTTPS 트래픽을 캡처하고 분석하는 네트워크 디버깅 도구입니다.<br>"
            "Fiddler .saz 아카이브 파일 읽기 및 HAR 형식 가져오기/내보내기를 지원합니다.<br><br>"
            "© 2025 NetScope 프로젝트. 모든 권리 보유."
        )
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(label)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

    # ── Style ─────────────────────────────────────────────────────────────────

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #ffffff;
                color: #1e1e1e;
            }
            QMenuBar {
                background-color: #f3f3f3;
                color: #1e1e1e;
                border-bottom: 1px solid #cccccc;
                padding: 2px 4px;
                font-size: 13px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 3px;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            QMenuBar::item:pressed {
                background-color: #007acc;
            }
            QMenu {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                padding: 4px 0;
                font-size: 13px;
            }
            QMenu::item {
                padding: 5px 24px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #aaaaaa;
            }
            QMenu::item:checked {
                color: #0078d4;
                font-weight: bold;
            }
            QMenu::separator {
                height: 1px;
                background: #cccccc;
                margin: 4px 8px;
            }
            QSplitter::handle {
                background-color: #e0e0e0;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
                font-size: 12px;
            }
            QStatusBar QLabel {
                color: white;
                padding: 0 10px;
            }
            QTabWidget::pane {
                border: none;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                color: #666666;
                padding: 7px 18px;
                border: none;
                border-top: 2px solid transparent;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1e1e1e;
                border-top: 2px solid #007acc;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e8e8e8;
                color: #333333;
            }
            QScrollBar:vertical {
                background: #f0f0f0;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #aaaaaa;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def closeEvent(self, event):
        if self._modified and not self._confirm_discard():
            event.ignore()
            return
        if self._engine.is_running():
            self._engine.stop()
        super().closeEvent(event)


# ── Serialization helpers ─────────────────────────────────────────────────────

def _session_to_dict(s: SessionEntry) -> dict:
    return {
        "id": s.id,
        "method": s.method,
        "scheme": s.scheme,
        "host": s.host,
        "path": s.path,
        "url": s.url,
        "status_code": s.status_code,
        "content_type": s.content_type,
        "body_size": s.body_size,
        "elapsed_ms": s.elapsed_ms,
        "state": s.state.value,
        "request_headers": s.request_headers,
        "request_body": base64.b64encode(s.request_body).decode(),
        "response_headers": s.response_headers,
        "response_body": base64.b64encode(s.response_body).decode(),
    }


def _session_from_dict(d: dict) -> SessionEntry:
    return SessionEntry(
        id=d["id"],
        method=d.get("method", "GET"),
        scheme=d.get("scheme", "https"),
        host=d.get("host", ""),
        path=d.get("path", "/"),
        url=d.get("url", ""),
        status_code=d.get("status_code", 0),
        content_type=d.get("content_type", ""),
        body_size=d.get("body_size", 0),
        elapsed_ms=d.get("elapsed_ms", 0.0),
        state=SessionState(d.get("state", "complete")),
        request_headers=d.get("request_headers", {}),
        request_body=base64.b64decode(d.get("request_body", "")),
        response_headers=d.get("response_headers", {}),
        response_body=base64.b64decode(d.get("response_body", "")),
    )


# ── Recent-files config ───────────────────────────────────────────────────────

def _load_recent_config() -> list[str]:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("recent_files", [])
    except Exception:
        return []


def _save_recent_config(recent: list[str]) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"recent_files": recent}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Non-fatal; config write failures are silently ignored


# ── Helpers ───────────────────────────────────────────────────────────────────

def _h_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background-color: #cccccc;")
    return f


def _status_sep(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: rgba(255,255,255,0.85); padding: 0 14px; "
        "border-left: 1px solid rgba(255,255,255,0.2);"
    )
    return lbl
