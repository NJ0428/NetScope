"""
Executes user-defined Python scripts as traffic hooks.

Designed to run safely in a background (mitmproxy) thread while emitting
results back to the Qt main thread via RulesEngine signals.
"""

from __future__ import annotations

import datetime
import threading


class ScriptContext:
    """
    Mutable session view passed to on_request() / on_response().

    The script reads/writes attributes freely.  After the hook returns,
    call apply_to_flow() to push the changes back into the mitmproxy flow.
    """

    def __init__(
        self,
        *,
        method: str = "",
        host: str = "",
        path: str = "",
        url: str = "",
        request_headers: dict | None = None,
        request_body: bytes = b"",
        status_code: int = 0,
        response_headers: dict | None = None,
        response_body: bytes = b"",
        _flow=None,
        _is_response: bool = False,
    ):
        self.method           = method
        self.host             = host
        self.path             = path
        self.url              = url
        self.request_headers  = dict(request_headers  or {})
        self.request_body     = request_body
        self.status_code      = status_code
        self.response_headers = dict(response_headers or {})
        self.response_body    = response_body
        self._flow       = _flow
        self._is_response = _is_response

    # ── Factory helpers ───────────────────────────────────────────────────────

    @classmethod
    def from_flow_request(cls, flow) -> "ScriptContext":
        return cls(
            method=flow.request.method,
            host=flow.request.pretty_host,
            path=flow.request.path,
            url=flow.request.url,
            request_headers=dict(flow.request.headers),
            request_body=flow.request.content or b"",
            _flow=flow,
            _is_response=False,
        )

    @classmethod
    def from_flow_response(cls, flow) -> "ScriptContext":
        resp = flow.response
        return cls(
            method=flow.request.method,
            host=flow.request.pretty_host,
            path=flow.request.path,
            url=flow.request.url,
            request_headers=dict(flow.request.headers),
            request_body=flow.request.content or b"",
            status_code=resp.status_code if resp else 0,
            response_headers=dict(resp.headers) if resp else {},
            response_body=resp.content if resp else b"",
            _flow=flow,
            _is_response=True,
        )

    # ── Apply back to flow ────────────────────────────────────────────────────

    def apply_to_flow(self) -> None:
        """Write modified headers/body back into the live mitmproxy flow."""
        if self._flow is None:
            return
        # Request
        if dict(self._flow.request.headers) != self.request_headers:
            self._flow.request.headers.clear()
            self._flow.request.headers.update(self.request_headers)
        if (self._flow.request.content or b"") != self.request_body:
            self._flow.request.content = self.request_body
        # Response (only when in response phase)
        if self._is_response and self._flow.response:
            if dict(self._flow.response.headers) != self.response_headers:
                self._flow.response.headers.clear()
                self._flow.response.headers.update(self.response_headers)
            if (self._flow.response.content or b"") != self.response_body:
                self._flow.response.content = self.response_body


class ScriptRunner:
    """
    Thread-safe runner for user-defined Python hook scripts.

    Typical lifecycle:
        runner = ScriptRunner()
        err = runner.load(script_text)   # compile once
        # ... on each request:
        ctx = ScriptContext.from_flow_request(flow)
        err = runner.run_request(ctx)
        if not err:
            ctx.apply_to_flow()
    """

    MAX_ERRORS = 300

    def __init__(self):
        self._lock    = threading.Lock()
        self._globals: dict = {}
        self._errors: list[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, script: str) -> str | None:
        """
        Compile and exec the script into a fresh namespace.
        Returns an error message on failure, None on success.
        """
        try:
            code = compile(script, "<custom_rules>", "exec")
            g: dict = {}
            exec(code, g)  # noqa: S102
            with self._lock:
                self._globals = g
            return None
        except SyntaxError as exc:
            msg = f"문법 오류 (줄 {exc.lineno}): {exc.msg}"
            self._append_error(msg)
            return msg
        except Exception as exc:
            msg = f"로드 오류: {type(exc).__name__}: {exc}"
            self._append_error(msg)
            return msg

    def run_request(self, ctx: ScriptContext) -> str | None:
        """Call on_request(ctx). Returns error string or None."""
        return self._call("on_request", ctx)

    def run_response(self, ctx: ScriptContext) -> str | None:
        """Call on_response(ctx). Returns error string or None."""
        return self._call("on_response", ctx)

    def get_errors(self) -> list[str]:
        with self._lock:
            return list(self._errors)

    def clear_errors(self) -> None:
        with self._lock:
            self._errors.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _call(self, fn_name: str, ctx: ScriptContext) -> str | None:
        with self._lock:
            g = self._globals
        fn = g.get(fn_name)
        if not callable(fn):
            return None
        try:
            fn(ctx)
            return None
        except Exception as exc:
            msg = (
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                f"{fn_name}() — {type(exc).__name__}: {exc}"
            )
            self._append_error(msg)
            return msg

    def _append_error(self, msg: str) -> None:
        with self._lock:
            self._errors.append(msg)
            if len(self._errors) > self.MAX_ERRORS:
                self._errors = self._errors[-self.MAX_ERRORS :]
