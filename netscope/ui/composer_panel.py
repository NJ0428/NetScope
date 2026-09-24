import threading
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)


class ComposerPanel(QWidget):
    _response_ready = Signal(int, str, str)   # status_code, headers_text, body_text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[dict] = []   # [{method, url, headers, body, status}]
        self._pending_method = ""
        self._pending_url = ""
        self._pending_headers = ""
        self._pending_body = ""
        self._response_ready.connect(self._on_response_ready)
        self._setup_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def load_from_session(self, session) -> None:
        """Populate composer fields from a SessionEntry (replay)."""
        self._method_combo.setCurrentText(session.method)
        self._url_edit.setText(session.url)
        headers_text = "\n".join(
            f"{k}: {v}" for k, v in session.request_headers.items()
        )
        self._req_headers_edit.setPlainText(headers_text)
        body_text = ""
        if session.request_body:
            body_text = session.request_body.decode("utf-8", errors="replace")
        self._req_body_edit.setPlainText(body_text)
        self._resp_body_edit.clear()
        self._resp_headers_edit.clear()
        self._status_lbl.setText("")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_split = QSplitter(Qt.Orientation.Horizontal)

        # ── History sidebar ───────────────────────────────────────────────
        hist_widget = QWidget()
        hist_layout = QVBoxLayout(hist_widget)
        hist_layout.setContentsMargins(8, 8, 4, 8)
        hist_layout.setSpacing(4)

        hist_lbl = QLabel("히스토리")
        hist_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #555;")
        hist_layout.addWidget(hist_lbl)

        self._history_list = QListWidget()
        self._history_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                font-size: 11px;
                background: #fafafa;
            }
            QListWidget::item { padding: 4px 6px; }
            QListWidget::item:selected { background: #0078d4; color: white; }
        """)
        self._history_list.itemClicked.connect(self._on_history_clicked)
        hist_layout.addWidget(self._history_list)

        clear_btn = QPushButton("지우기")
        clear_btn.setFixedHeight(24)
        clear_btn.clicked.connect(self._on_clear_history)
        hist_layout.addWidget(clear_btn)

        main_split.addWidget(hist_widget)

        # ── Request + Response ─────────────────────────────────────────────
        rr_widget = QWidget()
        rr_layout = QVBoxLayout(rr_widget)
        rr_layout.setContentsMargins(0, 0, 0, 0)
        rr_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Request panel
        req_widget = QWidget()
        req_layout = QVBoxLayout(req_widget)
        req_layout.setContentsMargins(12, 10, 12, 8)
        req_layout.setSpacing(8)

        url_row = QHBoxLayout()
        self._method_combo = QComboBox()
        self._method_combo.addItems(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
        self._method_combo.setFixedWidth(95)
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://example.com/api/endpoint")
        self._send_btn = QPushButton("전송")
        self._send_btn.setFixedWidth(64)
        self._send_btn.clicked.connect(self._on_send)
        url_row.addWidget(self._method_combo)
        url_row.addWidget(self._url_edit, stretch=1)
        url_row.addWidget(self._send_btn)
        req_layout.addLayout(url_row)

        req_tabs = QTabWidget()
        self._req_headers_edit = QTextEdit()
        self._req_headers_edit.setPlaceholderText(
            "Content-Type: application/json\nAuthorization: Bearer <token>"
        )
        req_tabs.addTab(self._req_headers_edit, "헤더")
        self._req_body_edit = QTextEdit()
        self._req_body_edit.setPlaceholderText('{"key": "value"}')
        req_tabs.addTab(self._req_body_edit, "본문")
        req_layout.addWidget(req_tabs)
        splitter.addWidget(req_widget)

        # Response panel
        resp_widget = QWidget()
        resp_layout = QVBoxLayout(resp_widget)
        resp_layout.setContentsMargins(12, 8, 12, 12)
        resp_layout.setSpacing(6)

        resp_hdr_row = QHBoxLayout()
        resp_lbl = QLabel("응답")
        resp_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size: 12px; color: #666666;")
        resp_hdr_row.addWidget(resp_lbl)
        resp_hdr_row.addSpacing(8)
        resp_hdr_row.addWidget(self._status_lbl)
        resp_hdr_row.addStretch()
        resp_layout.addLayout(resp_hdr_row)

        resp_tabs = QTabWidget()
        self._resp_body_edit = QTextEdit()
        self._resp_body_edit.setReadOnly(True)
        resp_tabs.addTab(self._resp_body_edit, "본문")
        self._resp_headers_edit = QTextEdit()
        self._resp_headers_edit.setReadOnly(True)
        resp_tabs.addTab(self._resp_headers_edit, "헤더")
        resp_layout.addWidget(resp_tabs)
        splitter.addWidget(resp_widget)
        splitter.setSizes([280, 280])

        rr_layout.addWidget(splitter)
        main_split.addWidget(rr_widget)

        main_split.setSizes([180, 620])
        main_split.setStretchFactor(0, 0)
        main_split.setStretchFactor(1, 1)

        outer.addWidget(main_split)
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                background: white;
            }
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                background: white;
            }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover  { background-color: #005a9e; }
            QPushButton:pressed { background-color: #004080; }
            QPushButton:disabled { background-color: #aaaaaa; }
            QTextEdit {
                border: 1px solid #e0e0e0;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                background: #fafafa;
            }
        """)

    # ── History ───────────────────────────────────────────────────────────────

    def _add_to_history(self, method: str, url: str, headers: str, body: str, status: int):
        entry = {"method": method, "url": url, "headers": headers, "body": body, "status": status}
        self._history.insert(0, entry)

        status_str = str(status) if status else "오류"
        short_url = url[:36] + "…" if len(url) > 36 else url
        label = f"{method}  {short_url}  [{status_str}]"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, 0)
        self._history_list.insertItem(0, item)
        # keep UserRole indices in sync
        for i in range(self._history_list.count()):
            self._history_list.item(i).setData(Qt.ItemDataRole.UserRole, i)

    @Slot(QListWidgetItem)
    def _on_history_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None and 0 <= idx < len(self._history):
            e = self._history[idx]
            self._method_combo.setCurrentText(e["method"])
            self._url_edit.setText(e["url"])
            self._req_headers_edit.setPlainText(e["headers"])
            self._req_body_edit.setPlainText(e["body"])

    @Slot()
    def _on_clear_history(self):
        self._history.clear()
        self._history_list.clear()

    # ── Send logic ────────────────────────────────────────────────────────────

    @Slot()
    def _on_send(self):
        url = self._url_edit.text().strip()
        if not url:
            return
        method       = self._method_combo.currentText()
        headers_text = self._req_headers_edit.toPlainText()
        headers      = self._parse_headers(headers_text)
        body         = self._req_body_edit.toPlainText().strip()
        data         = body.encode("utf-8") if body else None

        self._pending_method  = method
        self._pending_url     = url
        self._pending_headers = headers_text
        self._pending_body    = body

        self._send_btn.setEnabled(False)
        self._status_lbl.setText("전송 중...")
        self._resp_body_edit.clear()
        self._resp_headers_edit.clear()

        def _worker():
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status    = resp.status
                    hdr_text  = "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
                    body_text = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                status    = exc.code
                hdr_text  = "\n".join(f"{k}: {v}" for k, v in exc.headers.items())
                try:
                    body_text = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body_text = str(exc)
            except Exception as exc:
                status    = 0
                hdr_text  = ""
                body_text = f"오류: {exc}"
            self._response_ready.emit(status, hdr_text, body_text)

        threading.Thread(target=_worker, daemon=True).start()

    @Slot(int, str, str)
    def _on_response_ready(self, status: int, headers: str, body: str):
        self._send_btn.setEnabled(True)
        if status:
            color = "#27ae60" if status < 300 else ("#e67e22" if status < 500 else "#e74c3c")
            self._status_lbl.setText(
                f"<span style='color:{color};font-weight:bold'>{status}</span>"
            )
        else:
            self._status_lbl.setText("")
        self._resp_body_edit.setPlainText(body)
        self._resp_headers_edit.setPlainText(headers)
        self._add_to_history(
            self._pending_method, self._pending_url,
            self._pending_headers, self._pending_body, status,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_headers(text: str) -> dict[str, str]:
        result = {}
        for line in text.strip().splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                k = k.strip()
                if k:
                    result[k] = v.strip()
        return result
