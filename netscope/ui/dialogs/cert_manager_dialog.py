"""CA certificate manager dialog."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout,
)

from netscope.utils.system_proxy import (
    export_ca_cert,
    generate_ca_cert,
    get_ca_cert_info,
    get_ca_cert_path,
    install_ca_cert_windows,
    remove_ca_cert_windows,
    renew_ca_cert,
)

_WARN_DAYS = 30   # show warning when cert expires within this many days


class CertManagerDialog(QDialog):
    """
    Full CA certificate management:
      - View cert status, issuer, validity dates, days remaining
      - Generate CA cert (first run)
      - Install into Windows/macOS system trust store
      - Remove from trust store
      - Export PEM to arbitrary location
      - Renew (delete + regenerate)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CA 인증서 관리자")
        self.setMinimumWidth(500)
        self._setup_ui()
        self._refresh()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── Status group ───────────────────────────────────────────────────
        status_group = QGroupBox("인증서 상태")
        sform = QFormLayout(status_group)
        sform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._lbl_status    = QLabel()
        self._lbl_path      = QLabel()
        self._lbl_path.setWordWrap(True)
        self._lbl_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._lbl_subject   = QLabel()
        self._lbl_issued    = QLabel()
        self._lbl_expires   = QLabel()
        self._lbl_days      = QLabel()

        sform.addRow("상태:",      self._lbl_status)
        sform.addRow("위치:",      self._lbl_path)
        sform.addRow("발급 대상:", self._lbl_subject)
        sform.addRow("발급일:",    self._lbl_issued)
        sform.addRow("만료일:",    self._lbl_expires)
        sform.addRow("남은 기간:", self._lbl_days)

        layout.addWidget(status_group)

        # ── Actions group ──────────────────────────────────────────────────
        act_group = QGroupBox("작업")
        act_layout = QVBoxLayout(act_group)

        # Row 1: generate / renew
        row1 = QHBoxLayout()
        self._btn_generate = QPushButton("CA 인증서 생성")
        self._btn_generate.setToolTip("mitmproxy CA 인증서를 새로 생성합니다.")
        self._btn_generate.clicked.connect(self._on_generate)
        row1.addWidget(self._btn_generate)

        self._btn_renew = QPushButton("인증서 갱신 (재생성)")
        self._btn_renew.setToolTip("기존 인증서를 삭제하고 새로 생성합니다.")
        self._btn_renew.clicked.connect(self._on_renew)
        row1.addWidget(self._btn_renew)
        act_layout.addLayout(row1)

        # Row 2: install / remove (platform-specific)
        row2 = QHBoxLayout()
        if sys.platform == "win32":
            self._btn_install = QPushButton("시스템 신뢰 저장소에 설치")
            self._btn_install.setToolTip("Windows 사용자 Root 저장소에 CA 인증서를 추가합니다.")
            self._btn_install.clicked.connect(self._on_install)
            row2.addWidget(self._btn_install)

            self._btn_remove = QPushButton("신뢰 저장소에서 제거")
            self._btn_remove.setToolTip("Windows 신뢰 저장소에서 mitmproxy CA를 제거합니다.")
            self._btn_remove.clicked.connect(self._on_remove)
            row2.addWidget(self._btn_remove)
        else:
            note = QLabel("시스템 저장소 설치: Windows에서만 지원됩니다.")
            note.setStyleSheet("color:#888; font-size:11px;")
            row2.addWidget(note)
        act_layout.addLayout(row2)

        # Row 3: export
        row3 = QHBoxLayout()
        self._btn_export = QPushButton("인증서 내보내기 (PEM)...")
        self._btn_export.setToolTip("CA 인증서를 선택한 위치에 복사합니다.")
        self._btn_export.clicked.connect(self._on_export)
        row3.addWidget(self._btn_export)
        row3.addStretch()
        act_layout.addLayout(row3)

        layout.addWidget(act_group)

        # ── Note ───────────────────────────────────────────────────────────
        note = QLabel(
            "인증서를 신뢰 저장소에 설치하면 브라우저가 HTTPS 트래픽을 "
            "경고 없이 표시합니다.\n"
            "인증서 갱신 후에는 시스템 저장소를 다시 업데이트해야 합니다."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(note)

        # ── Close button ───────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ── Refresh ────────────────────────────────────────────────────────────

    def _refresh(self):
        cert_path = get_ca_cert_path()
        info = get_ca_cert_info()

        if cert_path is None:
            self._lbl_status.setText(
                "<span style='color:#c0392b;font-weight:bold'>✗  인증서 없음</span>"
            )
            self._lbl_path.setText("—")
            self._lbl_subject.setText("—")
            self._lbl_issued.setText("—")
            self._lbl_expires.setText("—")
            self._lbl_days.setText("—")
            has_cert = False
        else:
            self._lbl_status.setText(
                "<span style='color:#27ae60;font-weight:bold'>✔  인증서 존재</span>"
            )
            self._lbl_path.setText(str(cert_path))
            has_cert = True

            if info:
                self._lbl_subject.setText(info.get("subject", "—"))
                nb = info.get("not_before")
                na = info.get("not_after")
                dl = info.get("days_left")
                self._lbl_issued.setText(
                    nb.strftime("%Y-%m-%d %H:%M UTC") if nb else "—"
                )
                if na:
                    self._lbl_expires.setText(na.strftime("%Y-%m-%d %H:%M UTC"))
                else:
                    self._lbl_expires.setText("—")
                if dl is not None:
                    if dl < 0:
                        days_html = (
                            f"<span style='color:#e74c3c;font-weight:bold'>"
                            f"만료됨 ({-dl}일 경과)</span>"
                        )
                    elif dl <= _WARN_DAYS:
                        days_html = (
                            f"<span style='color:#e67e22;font-weight:bold'>"
                            f"{dl}일 남음 — 갱신을 권장합니다</span>"
                        )
                    else:
                        days_html = (
                            f"<span style='color:#27ae60'>{dl}일 남음</span>"
                        )
                    self._lbl_days.setText(days_html)
                else:
                    self._lbl_days.setText("—")
            else:
                for lbl in (self._lbl_subject, self._lbl_issued,
                            self._lbl_expires, self._lbl_days):
                    lbl.setText("읽기 실패")

        self._btn_renew.setEnabled(has_cert)
        self._btn_export.setEnabled(has_cert)
        if sys.platform == "win32":
            self._btn_install.setEnabled(has_cert)

    # ── Slots ──────────────────────────────────────────────────────────────

    @Slot()
    def _on_generate(self):
        if get_ca_cert_path():
            ans = QMessageBox.question(
                self, "인증서 생성",
                "이미 인증서가 존재합니다.\n덮어쓰지 않고 기존 인증서를 유지합니다.\n"
                "강제로 재생성하려면 '인증서 갱신'을 사용하세요.",
                QMessageBox.StandardButton.Ok,
            )
            return
        ok, msg = generate_ca_cert()
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "인증서 생성", msg, parent=self).exec()
        self._refresh()

    @Slot()
    def _on_renew(self):
        ans = QMessageBox.question(
            self, "인증서 갱신",
            "기존 CA 인증서를 삭제하고 새로 생성합니다.\n"
            "갱신 후에는 시스템 신뢰 저장소를 다시 업데이트해야 합니다.\n\n"
            "계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        ok, msg = renew_ca_cert()
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "인증서 갱신", msg, parent=self).exec()
        self._refresh()

    @Slot()
    def _on_install(self):
        ok, msg = install_ca_cert_windows()
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "신뢰 저장소 설치", msg, parent=self).exec()

    @Slot()
    def _on_remove(self):
        ans = QMessageBox.question(
            self, "신뢰 저장소에서 제거",
            "mitmproxy CA 인증서를 Windows 신뢰 저장소에서 제거합니다.\n계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        ok, msg = remove_ca_cert_windows()
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "신뢰 저장소 제거", msg, parent=self).exec()

    @Slot()
    def _on_export(self):
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "인증서 내보내기",
            "mitmproxy-ca-cert.pem",
            "PEM 인증서 (*.pem *.crt *.cer);;모든 파일 (*)",
        )
        if not dest:
            return
        ok, msg = export_ca_cert(dest)
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        QMessageBox(icon, "인증서 내보내기", msg, parent=self).exec()
