"""Proxy settings dialog — port, engine type, upstream proxy, system-proxy toggle."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout,
)

from netscope.utils.system_proxy import get_ca_cert_path, install_ca_cert_windows


class ProxySettingsDialog(QDialog):
    """
    Lets the user configure:
      - Listening port
      - Whether to auto-register system proxy on capture
      - Engine type (Real / Stub)
      - Upstream proxy (host, port, auth)
      - CA certificate installation
    """

    def __init__(
        self,
        port: int,
        auto_proxy: bool,
        use_real_engine: bool,
        mitm_available: bool,
        upstream_enabled: bool = False,
        upstream_host: str = "",
        upstream_port: int = 8080,
        upstream_auth_enabled: bool = False,
        upstream_user: str = "",
        upstream_password: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("프록시 설정")
        self.setMinimumWidth(460)

        self._port = port
        self._auto_proxy = auto_proxy
        self._use_real = use_real_engine
        self._mitm_available = mitm_available
        self._upstream_enabled = upstream_enabled
        self._upstream_host = upstream_host
        self._upstream_port = upstream_port
        self._upstream_auth_enabled = upstream_auth_enabled
        self._upstream_user = upstream_user
        self._upstream_password = upstream_password

        self._setup_ui()

    # ── Public results ─────────────────────────────────────────────────────

    def get_port(self) -> int:
        return self._port_spin.value()

    def get_auto_proxy(self) -> bool:
        return self._auto_proxy_chk.isChecked()

    def get_use_real_engine(self) -> bool:
        return self._real_chk.isChecked()

    def get_upstream_enabled(self) -> bool:
        return self._upstream_chk.isChecked()

    def get_upstream_host(self) -> str:
        return self._upstream_host_edit.text().strip()

    def get_upstream_port(self) -> int:
        return self._upstream_port_spin.value()

    def get_upstream_auth_enabled(self) -> bool:
        return self._upstream_auth_chk.isChecked()

    def get_upstream_user(self) -> str:
        return self._upstream_user_edit.text().strip()

    def get_upstream_password(self) -> str:
        return self._upstream_pass_edit.text()

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

        # ── 업스트림 프록시 ────────────────────────────────────────────────
        upstream_group = QGroupBox("업스트림 프록시")
        uform = QFormLayout(upstream_group)

        self._upstream_chk = QCheckBox("업스트림 프록시 사용")
        self._upstream_chk.setChecked(self._upstream_enabled)
        self._upstream_chk.toggled.connect(self._on_upstream_toggled)
        uform.addRow("", self._upstream_chk)

        self._upstream_host_edit = QLineEdit()
        self._upstream_host_edit.setPlaceholderText("예: 192.168.1.1")
        self._upstream_host_edit.setText(self._upstream_host)
        uform.addRow("호스트:", self._upstream_host_edit)

        self._upstream_port_spin = QSpinBox()
        self._upstream_port_spin.setRange(1, 65535)
        self._upstream_port_spin.setValue(self._upstream_port)
        uform.addRow("포트:", self._upstream_port_spin)

        self._upstream_auth_chk = QCheckBox("프록시 인증 사용")
        self._upstream_auth_chk.setChecked(self._upstream_auth_enabled)
        self._upstream_auth_chk.toggled.connect(self._on_auth_toggled)
        uform.addRow("", self._upstream_auth_chk)

        self._upstream_user_edit = QLineEdit()
        self._upstream_user_edit.setPlaceholderText("사용자명")
        self._upstream_user_edit.setText(self._upstream_user)
        uform.addRow("사용자명:", self._upstream_user_edit)

        self._upstream_pass_edit = QLineEdit()
        self._upstream_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._upstream_pass_edit.setPlaceholderText("비밀번호")
        self._upstream_pass_edit.setText(self._upstream_password)
        uform.addRow("비밀번호:", self._upstream_pass_edit)

        layout.addWidget(upstream_group)
        self._on_upstream_toggled(self._upstream_enabled)

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

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_upstream_toggled(self, enabled: bool):
        self._upstream_host_edit.setEnabled(enabled)
        self._upstream_port_spin.setEnabled(enabled)
        self._upstream_auth_chk.setEnabled(enabled)
        self._on_auth_toggled(self._upstream_auth_chk.isChecked() if enabled else False)

    def _on_auth_toggled(self, enabled: bool):
        upstream_on = self._upstream_chk.isChecked()
        self._upstream_user_edit.setEnabled(enabled and upstream_on)
        self._upstream_pass_edit.setEnabled(enabled and upstream_on)

    def _install_cert(self):
        ok, msg = install_ca_cert_windows()
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "인증서 설치", msg, parent=self).exec()
