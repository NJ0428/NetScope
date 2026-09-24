"""
Real proxy engine backed by mitmproxy.

Falls back gracefully when mitmproxy is not installed — import
MitmproxyEngine and check MitmproxyEngine.AVAILABLE before using.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from netscope.models.session import SessionEntry, SessionState
from netscope.proxy.engine import ProxyEngine

if TYPE_CHECKING:
    from netscope.rules.rules_engine import RulesEngine

try:
    from mitmproxy import options
    from mitmproxy.tools.dump import DumpMaster
    from mitmproxy import http as mitm_http
    _MITM_AVAILABLE = True
except ImportError:
    _MITM_AVAILABLE = False


class _NetScopeAddon:
    """mitmproxy addon — bridges flow events to Qt signals."""

    def __init__(self, engine: MitmproxyEngine):
        self._engine = engine
        self._flow_to_sid: dict[str, int] = {}  # flow.id -> SessionEntry.id

    def request(self, flow: mitm_http.HTTPFlow):
        rules: RulesEngine | None = self._engine._rules

        # ── Rule: hide CONNECT tunnels ─────────────────────────────────────
        if rules and rules.hide_connects and flow.request.method == "CONNECT":
            flow.kill()
            return

        # ── Rule: modify request headers ───────────────────────────────────
        if rules:
            if rules.custom_user_agent:
                flow.request.headers["User-Agent"] = rules.custom_user_agent
            if rules.request_japanese:
                flow.request.headers["Accept-Language"] = "ja, ja-JP;q=0.9, en;q=0.5"
            if rules.auto_authenticate:
                flow.request.headers["Authorization"] = "Bearer auto-token"

        # ── Build SessionEntry ─────────────────────────────────────────────
        session = SessionEntry(
            method=flow.request.method,
            scheme=flow.request.scheme,
            host=flow.request.pretty_host,
            path=flow.request.path,
            url=flow.request.url,
            request_headers=dict(flow.request.headers),
            request_body=flow.request.content or b"",
        )

        self._flow_to_sid[flow.id] = session.id
        self._engine._flow_store[session.id] = flow
        self._engine.session_started.emit(session)

        # ── Breakpoint on request ──────────────────────────────────────────
        if rules and rules.breakpoint_requests:
            flow.intercept()
            self._engine._pending[session.id] = session
            self._engine.breakpoint_request.emit(session.id)

    def response(self, flow: mitm_http.HTTPFlow):
        session_id = self._flow_to_sid.get(flow.id)
        if session_id is None:
            return

        rules: RulesEngine | None = self._engine._rules

        # ── Rule: hide 304 Not Modified ────────────────────────────────────
        if rules and rules.hide_304s and flow.response.status_code == 304:
            return

        # ── Elapsed time ───────────────────────────────────────────────────
        elapsed_ms = 0.0
        if (flow.response.timestamp_end is not None
                and flow.request.timestamp_start is not None):
            elapsed_ms = (
                (flow.response.timestamp_end - flow.request.timestamp_start) * 1000
            )

        body = flow.response.content or b""
        content_type = flow.response.headers.get("content-type", "")
        state = (
            SessionState.ERROR
            if flow.response.status_code >= 500
            else SessionState.COMPLETE
        )

        updated = {
            "status_code": flow.response.status_code,
            "content_type": content_type,
            "body_size": len(body),
            "elapsed_ms": elapsed_ms,
            "state": state,
            "response_headers": dict(flow.response.headers),
            "response_body": body,
        }
        self._engine.session_completed.emit(session_id, updated)

        # ── Breakpoint on response ─────────────────────────────────────────
        if rules and rules.breakpoint_responses:
            flow.intercept()
            self._engine._pending[session_id] = self._engine._flow_store.get(session_id)
            self._engine.breakpoint_request.emit(session_id)

    def error(self, flow: mitm_http.HTTPFlow):
        session_id = self._flow_to_sid.get(flow.id)
        if session_id is None:
            return
        msg = str(flow.error) if flow.error else "Unknown error"
        self._engine.session_completed.emit(session_id, {
            "state": SessionState.ERROR,
            "status_code": 0,
            "content_type": "",
            "body_size": 0,
            "elapsed_ms": 0.0,
            "response_headers": {},
            "response_body": msg.encode(),
        })


class MitmproxyEngine(ProxyEngine):
    """
    Real HTTP/HTTPS intercepting proxy engine using mitmproxy.

    Check ``MitmproxyEngine.AVAILABLE`` before instantiating — if mitmproxy
    is not installed this will raise ImportError at runtime.
    """

    AVAILABLE: bool = _MITM_AVAILABLE

    def __init__(self, parent=None):
        if not _MITM_AVAILABLE:
            raise ImportError(
                "mitmproxy가 설치되어 있지 않습니다. "
                "'pip install mitmproxy'를 실행하세요."
            )
        super().__init__(parent)
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._master = None
        self._rules: RulesEngine | None = None

        # session_id -> flow object
        self._flow_store: dict[int, object] = {}
        # session_id -> SessionEntry  (breakpoint waiting for resume)
        self._pending: dict[int, SessionEntry] = {}

        # upstream proxy
        self._upstream_host: str = ""
        self._upstream_port: int = 8080
        self._upstream_user: str = ""
        self._upstream_password: str = ""

    # ── ProxyEngine interface ──────────────────────────────────────────────

    def set_rules(self, rules: RulesEngine):
        self._rules = rules

    def set_upstream_proxy(
        self,
        host: str,
        port: int,
        user: str = "",
        password: str = "",
    ) -> None:
        """Configure an upstream proxy. Call before start()."""
        self._upstream_host = host
        self._upstream_port = port
        self._upstream_user = user
        self._upstream_password = password

    def get_pending_session(self, session_id: int) -> SessionEntry | None:
        return self._pending.get(session_id)

    def start(self, port: int = 8888):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_thread, args=(port,), daemon=True
        )
        self._thread.start()
        self.status_changed.emit(f"Capturing on port {port}")

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._master and self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._master.shutdown)
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self.status_changed.emit("Stopped")

    def is_running(self) -> bool:
        return self._running

    def resume_breakpoint(self, session_id: int,
                          modified_headers: dict | None = None,
                          modified_body: bytes | None = None):
        flow = self._flow_store.get(session_id)
        self._pending.pop(session_id, None)
        if flow is None:
            return

        def _do_resume():
            if modified_headers is not None:
                flow.request.headers.clear()
                flow.request.headers.update(modified_headers)
            if modified_body is not None:
                flow.request.content = modified_body
            flow.resume()

        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(_do_resume)

    # ── Internal ───────────────────────────────────────────────────────────

    def _run_thread(self, port: int):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run(port))
        except Exception as exc:
            self.status_changed.emit(f"프록시 오류: {exc}")
        finally:
            self._loop.close()
            self._loop = None
            self._running = False

    async def _async_run(self, port: int):
        opts_kwargs: dict = dict(
            listen_host="127.0.0.1",
            listen_port=port,
            ssl_insecure=True,
        )
        if self._upstream_host:
            creds = ""
            if self._upstream_user:
                import urllib.parse
                user = urllib.parse.quote(self._upstream_user, safe="")
                pw   = urllib.parse.quote(self._upstream_password, safe="")
                creds = f"{user}:{pw}@"
            opts_kwargs["mode"] = [
                f"upstream:http://{creds}{self._upstream_host}:{self._upstream_port}"
            ]
        opts = options.Options(**opts_kwargs)
        self._master = DumpMaster(opts, with_termlog=False, with_dumper=False)
        self._master.addons.add(_NetScopeAddon(self))
        try:
            await self._master.run()
        except Exception:
            pass
        finally:
            self._master = None
