from PySide6.QtCore import QObject, Signal


class RulesEngine(QObject):
    """Central state manager for all active traffic rules."""

    rules_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Filter rules
        self.hide_image_requests: bool = False
        self.hide_connects: bool = False
        self.hide_304s: bool = False
        # Breakpoints
        self.breakpoint_requests: bool = False
        self.breakpoint_responses: bool = False
        # Request/Response modification
        self.require_proxy_auth: bool = False
        self.apply_gzip: bool = False
        self.remove_encodings: bool = False
        self.request_japanese: bool = False
        self.auto_authenticate: bool = False
        # User-Agent override (None = no override)
        self.custom_user_agent: str | None = None
        # Performance simulation
        self.upload_kbps: int = 0
        self.download_kbps: int = 0
        self.latency_ms: int = 0
        # Custom script
        self.custom_rules_script: str = ""

    def notify(self):
        self.rules_changed.emit()
