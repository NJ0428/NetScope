from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry


class EditSessionDialog(QDialog):
    """Allows in-place editing of a session's headers and body."""

    def __init__(self, session: SessionEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"세션 편집 — #{session.id}  {session.method} {session.url}")
        self.setMinimumSize(720, 540)
        self._session = session
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>{self._session.method}</b>&nbsp;&nbsp;"
            f"<span style='color:#0078d4'>{self._session.url}</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        tabs = QTabWidget()

        # Request headers
        req_h_widget = QWidget()
        req_h_layout = QVBoxLayout(req_h_widget)
        req_h_layout.setContentsMargins(4, 4, 4, 4)
        self._req_headers_edit = QPlainTextEdit()
        self._req_headers_edit.setPlaceholderText("Header-Name: value")
        self._req_headers_edit.setPlainText(
            "\n".join(f"{k}: {v}" for k, v in self._session.request_headers.items())
        )
        req_h_layout.addWidget(self._req_headers_edit)
        tabs.addTab(req_h_widget, "Request Headers")

        # Request body
        req_b_widget = QWidget()
        req_b_layout = QVBoxLayout(req_b_widget)
        req_b_layout.setContentsMargins(4, 4, 4, 4)
        self._req_body_edit = QPlainTextEdit()
        self._req_body_edit.setPlainText(
            self._session.request_body.decode("utf-8", errors="replace")
        )
        req_b_layout.addWidget(self._req_body_edit)
        tabs.addTab(req_b_widget, "Request Body")

        # Response headers
        resp_h_widget = QWidget()
        resp_h_layout = QVBoxLayout(resp_h_widget)
        resp_h_layout.setContentsMargins(4, 4, 4, 4)
        self._resp_headers_edit = QPlainTextEdit()
        self._resp_headers_edit.setPlaceholderText("Header-Name: value")
        self._resp_headers_edit.setPlainText(
            "\n".join(f"{k}: {v}" for k, v in self._session.response_headers.items())
        )
        resp_h_layout.addWidget(self._resp_headers_edit)
        tabs.addTab(resp_h_widget, "Response Headers")

        # Response body
        resp_b_widget = QWidget()
        resp_b_layout = QVBoxLayout(resp_b_widget)
        resp_b_layout.setContentsMargins(4, 4, 4, 4)
        self._resp_body_edit = QPlainTextEdit()
        self._resp_body_edit.setPlainText(
            self._session.response_body.decode("utf-8", errors="replace")
        )
        resp_b_layout.addWidget(self._resp_body_edit)
        tabs.addTab(resp_b_widget, "Response Body")

        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("적용")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._apply)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _apply(self):
        self._session.request_headers = self._parse_headers(
            self._req_headers_edit.toPlainText()
        )
        self._session.request_body = (
            self._req_body_edit.toPlainText().encode("utf-8")
        )
        self._session.response_headers = self._parse_headers(
            self._resp_headers_edit.toPlainText()
        )
        self._session.response_body = (
            self._resp_body_edit.toPlainText().encode("utf-8")
        )
        self.accept()

    @staticmethod
    def _parse_headers(text: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in text.splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                k = k.strip()
                if k:
                    headers[k] = v.strip()
        return headers
