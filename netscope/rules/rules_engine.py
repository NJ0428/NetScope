from PySide6.QtCore import QObject, Signal

from netscope.rules.script_runner import ScriptRunner


class RulesEngine(QObject):
    """Central state manager for all active traffic rules."""

    rules_changed         = Signal()
    script_error_occurred = Signal(str)   # emitted from any thread → use QueuedConnection

    def __init__(self, parent=None):
        super().__init__(parent)
        # Filter rules
        self.hide_image_requests: bool = False
        self.hide_connects: bool       = False
        self.hide_304s: bool           = False
        # Breakpoints
        self.breakpoint_requests: bool  = False
        self.breakpoint_responses: bool = False
        # Request/Response modification
        self.require_proxy_auth: bool  = False
        self.apply_gzip: bool          = False
        self.remove_encodings: bool    = False
        self.request_japanese: bool    = False
        self.auto_authenticate: bool   = False
        # User-Agent override (None = no override)
        self.custom_user_agent: str | None = None
        # Performance simulation
        self.upload_kbps: int   = 0
        self.download_kbps: int = 0
        self.latency_ms: int    = 0
        # Custom script
        self.custom_rules_script: str  = ""
        self.custom_script_enabled: bool = False
        self.script_runner: ScriptRunner = ScriptRunner()

    # ── Script helpers ────────────────────────────────────────────────────────

    def load_script(self) -> str | None:
        """
        Compile and load custom_rules_script into the runner.
        Returns error message on failure, None on success.
        """
        if not self.custom_rules_script.strip():
            return None
        return self.script_runner.load(self.custom_rules_script)

    def add_script_error(self, msg: str) -> None:
        """Called from the proxy thread; safely forwards to the Qt main thread."""
        self.script_error_occurred.emit(msg)

    def notify(self):
        self.rules_changed.emit()
