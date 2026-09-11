from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry


class BreakpointDialog(QDialog):
    """Modal dialog shown when a request breakpoint is hit."""

    def __init__(self, session: SessionEntry, parent=None):
        super().__init__(parent)
        self._session = session
        self._aborted = False
        self.setWindowTitle(
            f"중단점 — #{session.id} {session.method} {session.host}{session.path}"
        )
        self.setMinimumSize(700, 480)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "<b>요청이 중단점에서 일시 중지되었습니다.</b>  "
            "헤더/본문을 확인하거나 수정한 뒤 <b>실행</b>을 누르세요."
        )
        info.setStyleSheet(
            "background:#fff3cd; padding:8px; border-radius:3px; color:#856404;"
        )
        layout.addWidget(info)

        tabs = QTabWidget()

        # ── Request tab ────────────────────────────────────────────────────
        req_w = QWidget()
        rl = QVBoxLayout(req_w)

        lbl_h = QLabel("요청 헤더")
        lbl_h.setStyleSheet("font-weight:bold;")
        rl.addWidget(lbl_h)

        self._req_headers_edit = QPlainTextEdit()
        self._req_headers_edit.setFont(_mono())
        self._req_headers_edit.setPlainText(
            "\n".join(f"{k}: {v}" for k, v in self._session.request_headers.items())
        )
        rl.addWidget(self._req_headers_edit, stretch=2)

        lbl_b = QLabel("요청 본문")
        lbl_b.setStyleSheet("font-weight:bold;")
        rl.addWidget(lbl_b)

        self._req_body_edit = QPlainTextEdit()
        self._req_body_edit.setFont(_mono())
        self._req_body_edit.setPlainText(
            self._session.request_body.decode("utf-8", errors="replace")
        )
        self._req_body_edit.setMaximumHeight(110)
        rl.addWidget(self._req_body_edit)

        tabs.addTab(req_w, "요청")

        # ── Response tab (placeholder) ─────────────────────────────────────
        resp_w = QWidget()
        resp_l = QVBoxLayout(resp_w)
        note = QLabel("응답은 요청 실행 후 세션 목록에서 확인할 수 있습니다.")
        note.setStyleSheet("color:#888; font-size:13px;")
        resp_l.addWidget(note)
        tabs.addTab(resp_w, "응답")

        layout.addWidget(tabs, stretch=1)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_abort = QPushButton("중단 (Abort)")
        btn_abort.setStyleSheet(
            "QPushButton{background:#e74c3c;color:white;padding:6px 18px;"
            "border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#c0392b;}"
        )
        btn_abort.clicked.connect(self._on_abort)

        btn_run = QPushButton("실행 (Run)")
        btn_run.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;padding:6px 18px;"
            "border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#2ecc71;}"
        )
        btn_run.clicked.connect(self._on_run)

        btn_layout.addWidget(btn_abort)
        btn_layout.addWidget(btn_run)
        layout.addLayout(btn_layout)

    def get_modified_headers(self) -> dict:
        headers = {}
        for line in self._req_headers_edit.toPlainText().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip()] = v.strip()
        return headers

    def get_modified_body(self) -> bytes:
        return self._req_body_edit.toPlainText().encode("utf-8")

    def was_aborted(self) -> bool:
        return self._aborted

    def _on_run(self):
        self.accept()

    def _on_abort(self):
        self._aborted = True
        self.reject()


def _mono() -> QFont:
    f = QFont("Consolas")
    f.setPointSize(11)
    return f
