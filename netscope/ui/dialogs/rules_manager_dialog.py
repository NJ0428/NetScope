from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGroupBox,
    QScrollArea, QVBoxLayout, QWidget,
)

from netscope.rules.rules_engine import RulesEngine


class RulesManagerDialog(QDialog):
    def __init__(self, rules: RulesEngine, parent=None):
        super().__init__(parent)
        self._rules = rules
        self.setWindowTitle("규칙 관리")
        self.setMinimumSize(480, 540)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setSpacing(10)

        # Filter rules
        fg = _group("필터 규칙")
        self._chk_images = _chk("이미지 요청 숨기기 (Hide Image Requests)", self._rules.hide_image_requests)
        self._chk_connects = _chk("CONNECT 요청 숨기기 (Hide CONNECTs)", self._rules.hide_connects)
        self._chk_304s = _chk("304 응답 숨기기 (Hide 304s)", self._rules.hide_304s)
        for w in [self._chk_images, self._chk_connects, self._chk_304s]:
            fg.layout().addWidget(w)
        cl.addWidget(fg)

        # Breakpoints
        bg = _group("자동 중단점 (Automatic Breakpoints)")
        self._chk_bp_req = _chk("요청에서 중단 (Before Request)", self._rules.breakpoint_requests)
        self._chk_bp_resp = _chk("응답에서 중단 (Before Response)", self._rules.breakpoint_responses)
        for w in [self._chk_bp_req, self._chk_bp_resp]:
            bg.layout().addWidget(w)
        cl.addWidget(bg)

        # Modification
        mg = _group("요청/응답 수정")
        self._chk_gzip = _chk("응답에 GZIP 인코딩 적용 (Apply GZIP Encoding)", self._rules.apply_gzip)
        self._chk_enc = _chk("모든 인코딩 제거 (Remove All Encodings)", self._rules.remove_encodings)
        self._chk_ja = _chk("일본어 콘텐츠 요청 (Request Japanese Content)", self._rules.request_japanese)
        self._chk_auth = _chk("자동 인증 (Automatically Authenticate)", self._rules.auto_authenticate)
        self._chk_proxy = _chk("프록시 인증 요구 (Require Proxy Authentication)", self._rules.require_proxy_auth)
        for w in [self._chk_gzip, self._chk_enc, self._chk_ja, self._chk_auth, self._chk_proxy]:
            mg.layout().addWidget(w)
        cl.addWidget(mg)

        cl.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _apply(self):
        self._rules.hide_image_requests = self._chk_images.isChecked()
        self._rules.hide_connects = self._chk_connects.isChecked()
        self._rules.hide_304s = self._chk_304s.isChecked()
        self._rules.breakpoint_requests = self._chk_bp_req.isChecked()
        self._rules.breakpoint_responses = self._chk_bp_resp.isChecked()
        self._rules.apply_gzip = self._chk_gzip.isChecked()
        self._rules.remove_encodings = self._chk_enc.isChecked()
        self._rules.request_japanese = self._chk_ja.isChecked()
        self._rules.auto_authenticate = self._chk_auth.isChecked()
        self._rules.require_proxy_auth = self._chk_proxy.isChecked()
        self._rules.notify()
        self.accept()


def _group(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setLayout(QVBoxLayout())
    return g


def _chk(label: str, checked: bool) -> QCheckBox:
    cb = QCheckBox(label)
    cb.setChecked(checked)
    return cb
