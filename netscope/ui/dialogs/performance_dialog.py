from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QLabel, QSpinBox, QVBoxLayout,
)

from netscope.rules.rules_engine import RulesEngine

_PRESETS = [
    ("커스텀", -1, -1, -1),
    ("제한 없음", 0, 0, 0),
    ("LTE (50 Mbps)", 51200, 51200, 20),
    ("4G (20 Mbps)", 20480, 20480, 50),
    ("3G (2 Mbps)", 2048, 2048, 100),
    ("2G (56 Kbps)", 56, 56, 300),
    ("GPRS (10 Kbps)", 10, 10, 500),
    ("1 MB/s", 1024, 1024, 0),
    ("256 KB/s", 256, 256, 0),
    ("ADSL (64 KB/s)", 64, 64, 50),
]


class PerformanceDialog(QDialog):
    def __init__(self, rules: RulesEngine, parent=None):
        super().__init__(parent)
        self._rules = rules
        self.setWindowTitle("성능 시뮬레이션")
        self.setMinimumSize(420, 360)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._preset_combo = QComboBox()
        for name, *_ in _PRESETS:
            self._preset_combo.addItem(name)
        self._preset_combo.currentIndexChanged.connect(self._on_preset)
        form.addRow("프리셋:", self._preset_combo)
        layout.addLayout(form)

        group = QGroupBox("상세 설정")
        gform = QFormLayout(group)

        self._upload_spin = QSpinBox()
        self._upload_spin.setRange(0, 102400)
        self._upload_spin.setSuffix("  KB/s  (0 = 제한 없음)")
        self._upload_spin.setValue(self._rules.upload_kbps)

        self._download_spin = QSpinBox()
        self._download_spin.setRange(0, 102400)
        self._download_spin.setSuffix("  KB/s  (0 = 제한 없음)")
        self._download_spin.setValue(self._rules.download_kbps)

        self._latency_spin = QSpinBox()
        self._latency_spin.setRange(0, 10000)
        self._latency_spin.setSuffix("  ms")
        self._latency_spin.setValue(self._rules.latency_ms)

        gform.addRow("업로드 대역폭:", self._upload_spin)
        gform.addRow("다운로드 대역폭:", self._download_spin)
        gform.addRow("추가 지연 (Latency):", self._latency_spin)
        layout.addWidget(group)

        note = QLabel("※ 스텁 엔진에서는 지연(Latency)만 시뮬레이션됩니다.")
        note.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(note)
        layout.addStretch()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_preset(self, index: int):
        _, upload, download, latency = _PRESETS[index]
        if upload < 0:  # Custom
            return
        self._upload_spin.setValue(upload)
        self._download_spin.setValue(download)
        self._latency_spin.setValue(latency)

    def _apply(self):
        self._rules.upload_kbps = self._upload_spin.value()
        self._rules.download_kbps = self._download_spin.value()
        self._rules.latency_ms = self._latency_spin.value()
        self._rules.notify()
        self.accept()
