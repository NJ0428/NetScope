import base64
import json
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QLabel, QMainWindow, QMenu, QMessageBox,
    QSplitter, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry, SessionState
from netscope.models.session_table_model import SessionTableModel
from netscope.proxy.engine import ProxyEngine, StubProxyEngine
from netscope.rules.rules_engine import RulesEngine
from netscope.ui.detail_panel import DetailPanel
from netscope.ui.dialogs.breakpoint_dialog import BreakpointDialog
from netscope.ui.dialogs.customize_rules_dialog import CustomizeRulesDialog
from netscope.ui.dialogs.performance_dialog import PerformanceDialog
from netscope.ui.dialogs.rules_manager_dialog import RulesManagerDialog
from netscope.ui.dialogs.user_agent_dialog import UserAgentDialog
from netscope.ui.session_table import SessionTableView
from netscope.ui.toolbar import Toolbar
from netscope.ui.welcome_panel import WelcomePanel

_STATUS_IDLE    = "● 대기 중"
_STATUS_CAPTURE = "● 캡처 중"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetScope — Network Traffic Inspector")
        self.setMinimumSize(1024, 640)
        self.resize(1400, 860)

        self._proxy_port = 8888
        self._rules = RulesEngine(self)
        self._session_model = SessionTableModel(self)
        self._engine: ProxyEngine = StubProxyEngine(self)
        self._engine.set_rules(self._rules)
        self._current_file: str | None = None
        self._modified = False

        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._apply_global_style()

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()

        # 파일
        file_menu = mb.addMenu("파일")
        act_new = QAction("새 세션", self, shortcut=QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._on_new)
        file_menu.addAction(act_new)

        act_open = QAction("열기...", self, shortcut=QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._on_open)
        file_menu.addAction(act_open)

        self._act_save = QAction("저장", self, shortcut=QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._on_save)
        file_menu.addAction(self._act_save)

        act_save_as = QAction("다른 이름으로 저장...", self, shortcut=QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_import = QAction("가져오기...", self)
        act_import.triggered.connect(self._on_import)
        file_menu.addAction(act_import)

        act_export = QAction("내보내기...", self)
        act_export.triggered.connect(self._on_export)
        file_menu.addAction(act_export)

        file_menu.addSeparator()
        act_quit = QAction("종료", self, shortcut=QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 편집
        edit_menu = mb.addMenu("편집")
        act_find = QAction("찾기", self, shortcut=QKeySequence.StandardKey.Find)
        act_find.triggered.connect(self._on_find)
        edit_menu.addAction(act_find)
        edit_menu.addSeparator()
        edit_menu.addAction(QAction("복사", self, shortcut=QKeySequence.StandardKey.Copy))
        edit_menu.addAction(QAction("전체 선택", self, shortcut=QKeySequence.StandardKey.SelectAll))
        edit_menu.addSeparator()
        edit_menu.addAction(QAction("환경설정...", self))

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
        tools_menu.addAction(QAction("인증서 관리자", self))
        tools_menu.addAction(QAction("프록시 설정...", self))
        tools_menu.addSeparator()
        tools_menu.addAction(QAction("WinConfig", self))

        # 보기
        view_menu = mb.addMenu("보기")
        act_toolbar = QAction("툴바", self, checkable=True, checked=True)
        act_toolbar.triggered.connect(lambda v: self._toolbar.setVisible(v))
        view_menu.addAction(act_toolbar)
        act_status = QAction("상태 표시줄", self, checkable=True, checked=True)
        act_status.triggered.connect(lambda v: self._status_bar.setVisible(v))
        view_menu.addAction(act_status)
        view_menu.addSeparator()
        view_menu.addAction(QAction("레이아웃 초기화", self))

        # 도움말
        help_menu = mb.addMenu("도움말")
        help_menu.addAction(QAction("문서", self))
        help_menu.addAction(QAction("단축키", self))
        help_menu.addSeparator()
        help_menu.addAction(QAction("NetScope 정보", self))

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

        self._right_stack = QStackedWidget()
        self._welcome_panel = WelcomePanel()
        self._detail_panel  = DetailPanel()
        self._right_stack.addWidget(self._welcome_panel)
        self._right_stack.addWidget(self._detail_panel)
        self._right_stack.setCurrentIndex(0)

        self._h_splitter.addWidget(self._right_stack)
        self._h_splitter.setSizes([360, 1040])
        self._h_splitter.setStretchFactor(0, 0)
        self._h_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._h_splitter, stretch=1)

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
    def _on_start(self):
        self._toolbar.set_capturing(True)
        self._cap_label.setText(_STATUS_CAPTURE)
        self._cap_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        self._engine.start(self._proxy_port)

    @Slot()
    def _on_stop(self):
        self._engine.stop()
        self._toolbar.set_capturing(False)
        self._cap_label.setText(_STATUS_IDLE)
        self._cap_label.setStyleSheet("color: #666666;")

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

    @Slot(SessionEntry)
    def _on_session_started(self, session: SessionEntry):
        self._session_model.add_session(session)
        self._count_label.setText(f"세션  {self._session_model.rowCount()}")
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

    @Slot()
    def _on_find(self):
        self._toolbar.focus_search()

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
    def _on_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "세션 열기", "",
            "NetScope 세션 (*.netsession);;모든 파일 (*)",
        )
        if not path:
            return
        try:
            self._load_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "열기 실패", f"파일을 열 수 없습니다:\n{exc}")

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
