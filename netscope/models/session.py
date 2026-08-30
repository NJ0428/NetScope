from dataclasses import dataclass, field
from enum import Enum


class SessionState(Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class SessionEntry:
    id: int = 0
    method: str = ""
    scheme: str = "https"
    host: str = ""
    path: str = "/"
    url: str = ""
    status_code: int = 0
    content_type: str = ""
    body_size: int = 0
    elapsed_ms: float = 0.0
    state: SessionState = SessionState.PENDING

    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: bytes = b""
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: bytes = b""

    @property
    def size_display(self) -> str:
        if self.body_size == 0:
            return "-"
        if self.body_size < 1024:
            return f"{self.body_size} B"
        if self.body_size < 1024 * 1024:
            return f"{self.body_size / 1024:.1f} KB"
        return f"{self.body_size / (1024 * 1024):.1f} MB"

    @property
    def time_display(self) -> str:
        if self.elapsed_ms == 0:
            return "-"
        if self.elapsed_ms < 1000:
            return f"{self.elapsed_ms:.0f} ms"
        return f"{self.elapsed_ms / 1000:.2f} s"
