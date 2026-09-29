"""Customize Rules dialog — script editor with activate toggle and live error log."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from netscope.rules.rules_engine import RulesEngine

_DEFAULT = """\
# NetScope 사용자 정의 규칙 (Python)
#
# session 객체 속성 (읽기/쓰기):
#   session.method            — HTTP 메서드  (str)
#   session.host              — 호스트명     (str)
#   session.path              — 경로         (str)
#   session.url               — 전체 URL     (str)
#   session.request_headers   — dict  (수정 시 요청에 반영)
#   session.request_body      — bytes (수정 시 요청에 반영)
#   session.status_code       — 상태코드     (on_response 전용)
#   session.response_headers  — dict  (수정 시 응답에 반영)
#   session.response_body     — bytes (수정 시 응답에 반영)
#
# 예시 1: 특정 호스트 요청에 커스텀 헤더 추가
# def on_request(session):
#     if "example.com" in session.host:
#         session.request_headers["X-Debug"] = "NetScope"
#
# 예시 2: 응답 본문 로그 출력 (오류 로그에서 확인)
# def on_response(session):
#     if session.status_code >= 400:
#         raise ValueError(f"오류 응답: {session.status_code} {session.url}")


def on_request(session):
    pass


def on_response(session):
    pass
"""


class CustomizeRulesDialog(QDialog):
    def __init__(self, rules: RulesEngine, parent=None):
        super().__init__(parent)
        self._rules = rules
        self.setWindowTitle("사용자 정의 규칙")
        self.setMinimumSize(720, 620)
        self._setup_ui()
        self._load_state()
        # Live error updates (queued — safe from background thread)
        self._rules.script_error_occurred.connect(
            self._on_live_error, Qt.ConnectionType.QueuedConnection
        )

    # ── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        self._enable_chk = QCheckBox("스크립트 활성화")
        self._enable_chk.setStyleSheet("font-weight: bold; font-size: 13px;")
        toolbar.addWidget(self._enable_chk)
        toolbar.addStretch()

        self._btn_load = QPushButton("파일에서 불러오기...")
        self._btn_load.clicked.connect(self._on_load_file)
        toolbar.addWidget(self._btn_load)

        self._btn_validate = QPushButton("유효성 검사")
        self._btn_validate.clicked.connect(self._on_validate)
        toolbar.addWidget(self._btn_validate)

        root.addLayout(toolbar)

        # ── Splitter: editor / log ────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Code editor
        mono = QFont("Consolas")
        mono.setPointSize(11)

        self._editor = QPlainTextEdit()
        self._editor.setFont(mono)
        self._editor.setStyleSheet(
            "QPlainTextEdit {"
            "  background:#1e1e1e; color:#d4d4d4;"
            "  border:1px solid #444; border-radius:3px;"
            "  selection-background-color:#264f78;"
            "}"
        )
        splitter.addWidget(self._editor)

        # Error log panel
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 4, 0, 0)
        log_layout.setSpacing(4)

        log_hdr = QHBoxLayout()
        log_lbl = QLabel("오류 로그")
        log_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #c0392b;")
        log_hdr.addWidget(log_lbl)
        log_hdr.addStretch()

        btn_refresh = QPushButton("새로 고침")
        btn_refresh.setFixedHeight(24)
        btn_refresh.clicked.connect(self._refresh_log)
        log_hdr.addWidget(btn_refresh)

        btn_clear = QPushButton("지우기")
        btn_clear.setFixedHeight(24)
        btn_clear.clicked.connect(self._on_clear_log)
        log_hdr.addWidget(btn_clear)

        log_layout.addLayout(log_hdr)

        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(mono)
        self._log_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  background:#1a1a1a; color:#e74c3c;"
            "  border:1px solid #333; border-radius:3px;"
            "  font-size:10pt;"
            "}"
        )
        self._log_edit.setPlaceholderText("스크립트 실행 오류가 여기에 표시됩니다.")
        log_layout.addWidget(self._log_edit)

        splitter.addWidget(log_widget)
        splitter.setSizes([400, 180])
        root.addWidget(splitter, stretch=1)

        # ── Button box ────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel,
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ── Load current state ────────────────────────────────────────────────

    def _load_state(self):
        self._editor.setPlainText(self._rules.custom_rules_script or _DEFAULT)
        self._enable_chk.setChecked(self._rules.custom_script_enabled)
        self._refresh_log()

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot()
    def _on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Python 스크립트 불러오기", "",
            "Python 파일 (*.py);;모든 파일 (*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self._editor.setPlainText(f.read())
        except Exception as exc:
            QMessageBox.warning(self, "불러오기 실패", str(exc))

    @Slot()
    def _on_validate(self):
        script = self._editor.toPlainText()
        # Temporarily load into a fresh runner to check for errors
        from netscope.rules.script_runner import ScriptRunner
        tmp = ScriptRunner()
        err = tmp.load(script)
        if err:
            self._append_log(f"[유효성 검사 실패]\n{err}")
            QMessageBox.warning(self, "유효성 검사", f"스크립트 오류:\n\n{err}")
        else:
            self._append_log("[유효성 검사 통과] 문법 오류 없음.")
            QMessageBox.information(self, "유효성 검사", "스크립트 문법 검사 통과.")

    @Slot()
    def _save(self):
        script  = self._editor.toPlainText()
        enabled = self._enable_chk.isChecked()

        # Compile the script; warn on error but allow saving
        err = self._rules.script_runner.load(script)
        if err:
            ans = QMessageBox.question(
                self,
                "스크립트 오류",
                f"스크립트에 오류가 있습니다:\n\n{err}\n\n"
                "오류가 있는 상태로 저장하시겠습니까?\n"
                "(활성화해도 on_request/on_response가 실행되지 않을 수 있습니다.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            enabled = False   # don't activate a broken script

        self._rules.custom_rules_script  = script
        self._rules.custom_script_enabled = enabled
        self._rules.notify()
        self.accept()

    @Slot(str)
    def _on_live_error(self, msg: str):
        """Receives errors emitted from the proxy background thread."""
        self._append_log(msg)

    @Slot()
    def _refresh_log(self):
        errors = self._rules.script_runner.get_errors()
        if errors:
            self._log_edit.setPlainText("\n".join(errors))
            self._scroll_log_to_bottom()
        else:
            self._log_edit.clear()

    @Slot()
    def _on_clear_log(self):
        self._rules.script_runner.clear_errors()
        self._log_edit.clear()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _append_log(self, msg: str):
        self._log_edit.appendPlainText(msg)
        self._scroll_log_to_bottom()

    def _scroll_log_to_bottom(self):
        cursor = self._log_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log_edit.setTextCursor(cursor)
