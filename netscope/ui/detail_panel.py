import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry


class DetailPanel(QWidget):
    """Request/Response detail panel with tabs for Headers, Body, JSON, Raw."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Request section
        self._request_tabs = QTabWidget()
        self._req_headers = self._make_text_edit()
        self._req_body = self._make_text_edit()
        self._req_json = self._make_text_edit()
        self._req_raw = self._make_text_edit()

        self._request_tabs.addTab(self._req_headers, "Headers")
        self._request_tabs.addTab(self._req_body, "Body")
        self._request_tabs.addTab(self._req_json, "JSON")
        self._request_tabs.addTab(self._req_raw, "Raw")

        # Response section
        self._response_tabs = QTabWidget()
        self._res_headers = self._make_text_edit()
        self._res_body = self._make_text_edit()
        self._res_json = self._make_text_edit()
        self._res_raw = self._make_text_edit()

        self._response_tabs.addTab(self._res_headers, "Headers")
        self._response_tabs.addTab(self._res_body, "Body")
        self._response_tabs.addTab(self._res_json, "JSON")
        self._response_tabs.addTab(self._res_raw, "Raw")

        self._tabs.addTab(self._request_tabs, "Request")
        self._tabs.addTab(self._response_tabs, "Response")

    def _make_text_edit(self) -> QTextEdit:
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setFont(QFont("Consolas", 10))
        edit.setStyleSheet("QTextEdit { background-color: #ffffff; color: #1e1e1e; }")
        return edit

    def show_session(self, session: SessionEntry):
        # Request headers
        header_lines = [f"{session.method} {session.path} HTTP/1.1"]
        for k, v in session.request_headers.items():
            header_lines.append(f"{k}: {v}")
        self._req_headers.setPlainText("\n".join(header_lines))

        # Request body
        req_body_text = self._decode_body(session.request_body)
        self._req_body.setPlainText(req_body_text or "(empty)")

        # Request JSON
        self._req_json.setPlainText(self._try_format_json(req_body_text))

        # Request raw
        raw_req = "\n".join(header_lines) + "\n\n" + (req_body_text or "")
        self._req_raw.setPlainText(raw_req)

        # Response headers
        res_header_lines = [f"HTTP/1.1 {session.status_code}"]
        for k, v in session.response_headers.items():
            res_header_lines.append(f"{k}: {v}")
        self._res_headers.setPlainText("\n".join(res_header_lines))

        # Response body
        res_body_text = self._decode_body(session.response_body)
        self._res_body.setPlainText(res_body_text or "(empty)")

        # Response JSON
        self._res_json.setPlainText(self._try_format_json(res_body_text))

        # Response raw
        raw_res = "\n".join(res_header_lines) + "\n\n" + (res_body_text or "")
        self._res_raw.setPlainText(raw_res)

    def clear_display(self):
        for edit in (
            self._req_headers, self._req_body, self._req_json, self._req_raw,
            self._res_headers, self._res_body, self._res_json, self._res_raw,
        ):
            edit.clear()

    @staticmethod
    def _decode_body(body: bytes) -> str:
        if not body:
            return ""
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return f"(binary data, {len(body)} bytes)"

    @staticmethod
    def _try_format_json(text: str) -> str:
        if not text:
            return "(no content)"
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            return "(not valid JSON)"
