"""
Proxy engine interface — stub implementation.

This module defines the interface that a real proxy engine must implement.
The StubProxyEngine generates fake traffic for UI development and testing.
"""

import gzip
import random
import threading
import time

from PySide6.QtCore import QObject, Signal

from netscope.models.session import SessionEntry, SessionState


class ProxyEngine(QObject):
    """Base interface for proxy engines."""

    session_started = Signal(SessionEntry)
    session_completed = Signal(int, dict)  # session_id, updated_fields
    status_changed = Signal(str)
    breakpoint_request = Signal(int)  # session_id — emitted when breakpoint is hit

    def start(self, port: int = 8888):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def is_running(self) -> bool:
        raise NotImplementedError

    def resume_breakpoint(self, session_id: int,
                          modified_headers: dict | None = None,
                          modified_body: bytes | None = None):
        """Resume a paused breakpoint session. Default: no-op."""


SAMPLE_HOSTS = [
    "api.github.com", "www.google.com", "cdn.jsdelivr.net",
    "api.openai.com", "registry.npmjs.org", "httpbin.org",
    "jsonplaceholder.typicode.com", "example.com",
]

SAMPLE_PATHS = [
    "/api/v1/users", "/api/v2/search?q=test", "/index.html",
    "/static/js/bundle.min.js", "/api/repos/list", "/favicon.ico",
    "/graphql", "/health", "/api/auth/token", "/v1/completions",
    "/assets/style.css", "/api/data/export.json",
]

SAMPLE_CONTENT_TYPES = [
    "application/json", "text/html; charset=utf-8",
    "application/javascript", "text/css", "image/png",
    "image/jpeg", "image/svg+xml",
]

SAMPLE_METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]

SAMPLE_STATUSES = [200, 201, 204, 301, 304, 400, 401, 403, 404, 500]
SAMPLE_WEIGHTS  = [ 50,  10,   5,   5,   5,   5,   3,   3,  10,   4]


def _make_response(rules=None):
    status = random.choices(SAMPLE_STATUSES, weights=SAMPLE_WEIGHTS)[0]
    content_type = random.choice(SAMPLE_CONTENT_TYPES)
    elapsed = random.uniform(10, 2000)
    body = b'{"status": "ok", "data": [1, 2, 3]}'
    headers = {
        "Content-Type": content_type,
        "Server": "nginx/1.24.0",
        "X-Request-Id": str(random.randint(100000, 999999)),
        "Cache-Control": "no-cache",
    }

    if rules:
        if rules.require_proxy_auth and random.random() < 0.1:
            status = 407
            headers["Proxy-Authenticate"] = 'Basic realm="NetScope Proxy"'

        if rules.apply_gzip and not rules.remove_encodings:
            body = gzip.compress(body)
            headers["Content-Encoding"] = "gzip"
        elif rules.remove_encodings:
            headers.pop("Content-Encoding", None)

        if rules.latency_ms > 0:
            elapsed += rules.latency_ms

    headers["Content-Length"] = str(len(body))

    return {
        "status_code": status,
        "content_type": content_type,
        "body_size": len(body),
        "elapsed_ms": elapsed,
        "state": SessionState.COMPLETE if status < 500 else SessionState.ERROR,
        "response_headers": headers,
        "response_body": body,
    }


class StubProxyEngine(ProxyEngine):
    """Generates fake HTTP sessions for UI testing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: threading.Thread | None = None
        self._port = 8888
        self._rules = None  # set via set_rules()
        # Sessions waiting for user to resume breakpoint
        self._pending: dict[int, SessionEntry] = {}

    def set_rules(self, rules):
        """Attach a RulesEngine so the stub applies active rules."""
        self._rules = rules

    def get_pending_session(self, session_id: int) -> SessionEntry | None:
        return self._pending.get(session_id)

    def resume_breakpoint(self, session_id: int,
                          modified_headers: dict | None = None,
                          modified_body: bytes | None = None):
        """Called from the UI thread to let a breakpoint session proceed."""
        session = self._pending.pop(session_id, None)
        if session is None:
            return
        if modified_headers is not None:
            session.request_headers = modified_headers
        if modified_body is not None:
            session.request_body = modified_body
        resp = _make_response(self._rules)
        self.session_completed.emit(session_id, resp)

    def start(self, port: int = 8888):
        if self._running:
            return
        self._port = port
        self._running = True
        self._thread = threading.Thread(target=self._generate_traffic, daemon=True)
        self._thread.start()
        self.status_changed.emit(f"Capturing on port {port}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.status_changed.emit("Stopped")

    def is_running(self) -> bool:
        return self._running

    def _generate_traffic(self):
        while self._running:
            # Base interval + optional latency
            latency_extra = (self._rules.latency_ms / 1000.0) if self._rules else 0
            time.sleep(random.uniform(0.3, 1.5) + latency_extra)
            if not self._running:
                break

            method = random.choice(SAMPLE_METHODS)
            host   = random.choice(SAMPLE_HOSTS)
            path   = random.choice(SAMPLE_PATHS)

            # Build request headers, applying active rules
            req_headers: dict[str, str] = {
                "Host": host,
                "User-Agent": "NetScope/1.0",
                "Accept": "application/json, text/html, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
            if self._rules:
                if self._rules.custom_user_agent:
                    req_headers["User-Agent"] = self._rules.custom_user_agent
                if self._rules.request_japanese:
                    req_headers["Accept-Language"] = "ja, ja-JP;q=0.9, en;q=0.5"
                if self._rules.auto_authenticate:
                    req_headers["Authorization"] = "Bearer auto-token-stub"
                if self._rules.require_proxy_auth:
                    req_headers["Proxy-Authorization"] = "Basic dXNlcjpwYXNz"

            session = SessionEntry(
                method=method,
                scheme=random.choice(["https", "http"]),
                host=host,
                path=path,
                url=f"https://{host}{path}",
                request_headers=req_headers,
                request_body=b'{"query": "test"}' if method == "POST" else b"",
            )

            # Emit session to UI (shows in table as PENDING)
            self.session_started.emit(session)

            if self._rules and self._rules.breakpoint_requests:
                # Store for resume; emit breakpoint signal; do NOT complete yet
                self._pending[session.id] = session
                self.breakpoint_request.emit(session.id)
                # session_completed will be emitted when user clicks Run
            else:
                # Normal flow: wait a bit then complete
                time.sleep(random.uniform(0.05, 0.5))
                if not self._running:
                    break
                resp = _make_response(self._rules)
                self.session_completed.emit(session.id, resp)
