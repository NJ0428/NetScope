"""Read Fiddler SAZ archive files (.saz).

SAZ is a ZIP archive with the following layout::

    raw/
        001_c.txt   — raw client request  (HTTP/1.x text)
        001_s.txt   — raw server response (HTTP/1.x text)
        001_m.xml   — session metadata    (optional)
    _index.htm      — HTML index          (ignored)
"""
import zipfile

from netscope.models.session import SessionEntry, SessionState


def _split_message(data: bytes) -> tuple[bytes, bytes]:
    sep = b"\r\n\r\n"
    idx = data.find(sep)
    if idx == -1:
        return data, b""
    return data[:idx], data[idx + 4:]


def _parse_headers(header_bytes: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in header_bytes.decode("utf-8", errors="replace").splitlines()[1:]:
        if ":" in line:
            k, _, v = line.partition(":")
            headers[k.strip()] = v.strip()
    return headers


def _first_line(header_bytes: bytes) -> str:
    text = header_bytes.decode("utf-8", errors="replace")
    return text.splitlines()[0] if text else ""


def load_saz(path: str) -> list[SessionEntry]:
    """Load all sessions from a Fiddler SAZ file.  Returns a list of SessionEntry."""
    sessions: list[SessionEntry] = []

    with zipfile.ZipFile(path, "r") as zf:
        all_names = set(zf.namelist())
        req_files = sorted(
            n for n in all_names
            if n.startswith("raw/") and n.endswith("_c.txt")
        )

        for i, req_file in enumerate(req_files, start=1):
            prefix = req_file[len("raw/"):-len("_c.txt")]   # e.g. "001"
            resp_file = f"raw/{prefix}_s.txt"

            req_data  = zf.read(req_file)
            resp_data = zf.read(resp_file) if resp_file in all_names else b""

            # ── Request ───────────────────────────────────────────────────
            req_head_bytes, req_body = _split_message(req_data)
            req_first = _first_line(req_head_bytes)
            req_headers = _parse_headers(req_head_bytes)

            parts = req_first.split()
            method = parts[0] if parts else "GET"
            raw_path = parts[1] if len(parts) > 1 else "/"

            host = req_headers.get("Host", "")
            # CONNECT method means HTTPS tunnel
            scheme = "https" if method == "CONNECT" else "http"
            url = f"{scheme}://{host}{raw_path}" if host else raw_path

            # ── Response ──────────────────────────────────────────────────
            resp_head_bytes, resp_body = _split_message(resp_data)
            resp_first = _first_line(resp_head_bytes)
            resp_headers = _parse_headers(resp_head_bytes)

            resp_parts = resp_first.split()
            try:
                status_code = int(resp_parts[1]) if len(resp_parts) > 1 else 0
            except ValueError:
                status_code = 0

            content_type = resp_headers.get("Content-Type", "")

            sessions.append(SessionEntry(
                id=i,
                method=method,
                scheme=scheme,
                host=host,
                path=raw_path,
                url=url,
                status_code=status_code,
                content_type=content_type,
                body_size=len(resp_body),
                elapsed_ms=0.0,
                state=(
                    SessionState.COMPLETE if 0 < status_code < 500
                    else SessionState.ERROR
                ),
                request_headers=req_headers,
                request_body=req_body,
                response_headers=resp_headers,
                response_body=resp_body,
            ))

    return sessions
