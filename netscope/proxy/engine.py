"""
Proxy engine interface — stub implementation.

This module defines the interface that a real proxy engine must implement.
The StubProxyEngine generates fake traffic for UI development and testing.
"""

import random
import threading
import time

from PySide6.QtCore import QObject, Signal

from netscope.models.session import SessionEntry, SessionState


class ProxyEngine(QObject):
    """Base interface for proxy engines."""

    session_started = Signal(SessionEntry)
    session_completed = Signal(int, dict)  # session_id, updated_fields
    status_changed = Signal(str)  # status message

    def start(self, port: int = 8888):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def is_running(self) -> bool:
        raise NotImplementedError


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
]

SAMPLE_METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]


class StubProxyEngine(ProxyEngine):
    """Generates fake HTTP sessions for UI testing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: threading.Thread | None = None
        self._port = 8888

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
            time.sleep(random.uniform(0.3, 1.5))
            if not self._running:
                break

            method = random.choice(SAMPLE_METHODS)
            host = random.choice(SAMPLE_HOSTS)
            path = random.choice(SAMPLE_PATHS)

            session = SessionEntry(
                method=method,
                scheme=random.choice(["https", "http"]),
                host=host,
                path=path,
                url=f"https://{host}{path}",
                request_headers={
                    "Host": host,
                    "User-Agent": "NetScope/1.0",
                    "Accept": "application/json, text/html, */*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                },
                request_body=b'{"query": "test"}' if method == "POST" else b"",
            )

            self.session_started.emit(session)

            time.sleep(random.uniform(0.05, 0.5))
            if not self._running:
                break

            status = random.choices(
                [200, 201, 204, 301, 304, 400, 401, 403, 404, 500],
                weights=[50, 10, 5, 5, 5, 5, 3, 3, 10, 4],
            )[0]
            content_type = random.choice(SAMPLE_CONTENT_TYPES)
            body_size = random.randint(128, 524288)
            elapsed = random.uniform(10, 2000)

            response_body = b'{"status": "ok", "data": [1, 2, 3]}'

            self.session_completed.emit(session.id, {
                "status_code": status,
                "content_type": content_type,
                "body_size": body_size,
                "elapsed_ms": elapsed,
                "state": SessionState.COMPLETE if status < 500 else SessionState.ERROR,
                "response_headers": {
                    "Content-Type": content_type,
                    "Content-Length": str(body_size),
                    "Server": "nginx/1.24.0",
                    "X-Request-Id": f"{random.randint(100000, 999999)}",
                    "Cache-Control": "no-cache",
                },
                "response_body": response_body,
            })
