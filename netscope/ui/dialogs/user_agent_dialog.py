from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QVBoxLayout,
)

from netscope.rules.rules_engine import RulesEngine

_PRESETS = [
    ("기본값 (NetScope/1.0)", "NetScope/1.0"),
    ("Chrome 120 (Windows)", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    ("Firefox 120 (Windows)", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"),
    ("Safari 17 (macOS)", "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"),
    ("Edge 120 (Windows)", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"),
    ("iPhone (iOS 17)", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    ("Android Chrome", "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36"),
    ("iPad (iOS 17)", "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    ("Googlebot", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
    ("curl/8.4.0", "curl/8.4.0"),
    ("python-requests/2.31.0", "python-requests/2.31.0"),
]


class UserAgentDialog(QDialog):
    def __init__(self, rules: RulesEngine, parent=None):
        super().__init__(parent)
        self._rules = rules
        self.setWindowTitle("User-Agent 변경")
        self.setMinimumSize(600, 420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("프리셋 선택:"))

        self._list = QListWidget()
        for name, ua in _PRESETS:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, ua)
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_preset)
        layout.addWidget(self._list)

        layout.addWidget(QLabel("User-Agent 값:"))
        self._ua_edit = QLineEdit()
        self._ua_edit.setPlaceholderText("직접 입력하거나 위에서 프리셋을 선택하세요")
        current = self._rules.custom_user_agent or "NetScope/1.0"
        self._ua_edit.setText(current)
        layout.addWidget(self._ua_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        for i, (_, ua) in enumerate(_PRESETS):
            if ua == current:
                self._list.setCurrentRow(i)
                break

    def _on_preset(self, row: int):
        if row >= 0:
            self._ua_edit.setText(self._list.item(row).data(Qt.ItemDataRole.UserRole))

    def _apply(self):
        ua = self._ua_edit.text().strip()
        self._rules.custom_user_agent = ua if ua else None
        self._rules.notify()
        self.accept()
