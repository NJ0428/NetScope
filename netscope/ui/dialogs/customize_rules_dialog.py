from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from netscope.rules.rules_engine import RulesEngine

_DEFAULT = """\
# NetScope 사용자 정의 규칙 (Python)
#
# session 객체 속성:
#   session.method          — HTTP 메서드 (GET, POST, ...)
#   session.host            — 호스트명
#   session.path            — 경로
#   session.status_code     — 상태코드
#   session.request_headers — dict (수정 가능)
#   session.response_headers — dict (수정 가능)
#   session.request_body    — bytes
#   session.response_body   — bytes
#
# 예시: 특정 호스트 요청에 커스텀 헤더 추가
# def on_request(session):
#     if "example.com" in session.host:
#         session.request_headers["X-Debug"] = "true"

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
        self.setMinimumSize(660, 520)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        desc = QLabel(
            "Python 스크립트로 트래픽을 커스터마이징합니다. "
            "on_request(session) / on_response(session) 함수를 구현하세요."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#555; font-size:12px; margin-bottom:4px;")
        layout.addWidget(desc)

        self._editor = QPlainTextEdit()
        f = QFont("Consolas")
        f.setPointSize(11)
        self._editor.setFont(f)
        self._editor.setStyleSheet(
            "QPlainTextEdit{background:#1e1e1e;color:#d4d4d4;"
            "border:1px solid #444;border-radius:3px;}"
        )
        self._editor.setPlainText(self._rules.custom_rules_script or _DEFAULT)
        layout.addWidget(self._editor, stretch=1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        self._rules.custom_rules_script = self._editor.toPlainText()
        self._rules.notify()
        self.accept()
