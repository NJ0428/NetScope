"""Proxy settings dialog — port, engine type, system-proxy toggle."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout,
)

from netscope.utils.system_proxy import get_ca_cert_path, install_ca_cert_windows


class ProxySettingsDialog(QDialog):
    """
    Lets the user configure:
      - Listening port
      - Whether to auto-register system proxy on capture
      - Engine type (Real / Stub)
      - CA certificate installation
    """

    def __init__(self, port: int, auto_proxy: bool, use_real_engine: bool,
                 mitm_available: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("프록시 설정")
        self.setMinimumWidth(440)

        self._port = port
        self._auto_proxy = auto_proxy
        self._use_real = use_real_engine
        self._mitm_available = mitm_available

        self._setup_ui()

    # ── Public results ─────────────────────────────────────────────────────

    def get_port(self) -> int:
        return self._port_spin.value()

    def get_auto_proxy(self) -> bool:
        return self._auto_proxy_chk.isChecked()

    def get_use_real_engine(self) -> bool:
        return self._real_chk.isChecked()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── 기본 설정 ──────────────────────────────────────────────────────
        basic_group = QGroupBox("기본 설정")
        form = QFormLayout(basic_group)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(self._port)
        form.addRow("리스닝 포트:", self._port_spin)

        self._auto_proxy_chk = QCheckBox("캡처 시작 시 시스템 프록시 자동 등록")
        self._auto_proxy_chk.setChecked(self._auto_proxy)
        form.addRow("", self._auto_proxy_chk)

        layout.addWidget(basic_group)

        # ── 엔진 선택 ──────────────────────────────────────────────────────
        engine_group = QGroupBox("프록시 엔진")
        eform = QFormLayout(engine_group)

        self._real_chk = QCheckBox("실제 프록시 엔진 사용 (mitmproxy)")
        self._real_chk.setChecked(self._use_real and self._mitm_available)
        self._real_chk.setEnabled(self._mitm_available)
        eform.addRow("", self._real_chk)

        if not self._mitm_available:
            warn = QLabel(
                "⚠  mitmproxy가 설치되어 있지 않습니다.\n"
                "    pip install mitmproxy  를 실행하세요."
            )
            warn.setStyleSheet("color:#c0392b; font-size:11px;")
            eform.addRow("", warn)
        else:
            ok_label = QLabel("✔  mitmproxy 설치 확인됨")
            ok_label.setStyleSheet("color:#27ae60; font-size:11px;")
            eform.addRow("", ok_label)

        layout.addWidget(engine_group)

        # ── HTTPS 인터셉트 ─────────────────────────────────────────────────
        cert_group = QGroupBox("HTTPS 인터셉트 (CA 인증서)")
        clayout = QVBoxLayout(cert_group)

        cert_path = get_ca_cert_path()
        if cert_path:
            cert_status = QLabel(f"✔  인증서 파일: {cert_path}")
            cert_status.setStyleSheet("color:#27ae60; font-size:11px;")
        else:
            cert_status = QLabel("⚠  인증서 없음 — 캡처를 한 번 실행하면 자동 생성됩니다.")
            cert_status.setStyleSheet("color:#888; font-size:11px;")
        clayout.addWidget(cert_status)

        if sys.platform == "win32":
            btn_row = QHBoxLayout()
            install_btn = QPushButton("Windows 신뢰 저장소에 설치")
            install_btn.clicked.connect(self._install_cert)
            btn_row.addWidget(install_btn)
            btn_row.addStretch()
            clayout.addLayout(btn_row)

        layout.addWidget(cert_group)

        layout.addStretch()

        # ── 버튼 ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _install_cert(self):
        ok, msg = install_ca_cert_windows()
        icon = (
            QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        )
        QMessageBox(icon, "인증서 설치", msg, parent=self).exec()
