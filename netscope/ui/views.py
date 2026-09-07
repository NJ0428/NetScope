"""Individual view widgets used inside DetailPanel tabs."""

import base64
import gzip
import json
import re
import zlib
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QFrame, QHeaderView, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry

MONO_FONT = QFont("Consolas", 10)

_TABLE_STYLE = """
    QTableWidget {
        background-color: #ffffff;
        color: #1e1e1e;
        gridline-color: #e8e8e8;
        border: none;
        alternate-background-color: #f7f7f7;
    }
    QTableWidget::item { padding: 2px 6px; }
    QTableWidget::item:selected {
        background-color: #cce5ff;
        color: #1e1e1e;
    }
    QHeaderView::section {
        background-color: #f0f0f0;
        color: #333333;
        border: none;
        border-right: 1px solid #d0d0d0;
        border-bottom: 1px solid #d0d0d0;
        padding: 4px 8px;
        font-weight: bold;
    }
"""

_EDIT_STYLE = "QTextEdit { background: #ffffff; color: #1e1e1e; border: none; }"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_edit() -> QTextEdit:
    e = QTextEdit()
    e.setReadOnly(True)
    e.setFont(MONO_FONT)
    e.setStyleSheet(_EDIT_STYLE)
    return e


def _h_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background: #e0e0e0;")
    return f


def _charset(headers: dict) -> str:
    for k, v in headers.items():
        if k.lower() == "content-type":
            m = re.search(r"charset=([^\s;\"]+)", v, re.IGNORECASE)
            return m.group(1).strip('"') if m else "utf-8"
    return "utf-8"


def _ct_base(headers: dict) -> str:
    for k, v in headers.items():
        if k.lower() == "content-type":
            return v.split(";")[0].strip().lower()
    return ""


def _decode_body(body: bytes, headers: dict) -> str:
    if not body:
        return ""
    cs = _charset(headers)
    try:
        return body.decode(cs, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


# ─── Shared widgets ───────────────────────────────────────────────────────────

class _TwoColTable(QTableWidget):
    """Read-only Name | Value table."""

    def __init__(self, col0="Name", col1="Value", parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels([col0, col1])
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setFont(MONO_FONT)
        self.setStyleSheet(_TABLE_STYLE)

    def load(self, rows: list[tuple[str, str]]):
        self.setRowCount(len(rows))
        for i, (name, value) in enumerate(rows):
            self.setItem(i, 0, QTableWidgetItem(name))
            self.setItem(i, 1, QTableWidgetItem(value))
        self.resizeRowsToContents()


# ─── Syntax Highlighters ──────────────────────────────────────────────────────

class _JsonHL(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        kf = QTextCharFormat(); kf.setForeground(QColor("#0451a5"))  # key
        sf = QTextCharFormat(); sf.setForeground(QColor("#a31515"))  # string
        nf = QTextCharFormat(); nf.setForeground(QColor("#098658"))  # number
        bf = QTextCharFormat(); bf.setForeground(QColor("#0000ff")); bf.setFontWeight(700)  # bool/null
        pf = QTextCharFormat(); pf.setForeground(QColor("#777777"))  # punctuation
        self._rules = [
            (re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"\s*(?=:)'), kf),
            (re.compile(r'(?<=[:,\[\{])\s*"[^"\\]*(?:\\.[^"\\]*)*"'), sf),
            (re.compile(r'\b-?\d+\.?\d*([eE][+-]?\d+)?\b'), nf),
            (re.compile(r'\b(true|false|null)\b'), bf),
            (re.compile(r'[{}\[\],:]'), pf),
        ]

    def highlightBlock(self, text: str):
        for pat, fmt in self._rules:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class _XmlHL(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        tag = QTextCharFormat(); tag.setForeground(QColor("#800000"))
        atn = QTextCharFormat(); atn.setForeground(QColor("#e50000"))
        atv = QTextCharFormat(); atv.setForeground(QColor("#0000ff"))
        cmt = QTextCharFormat(); cmt.setForeground(QColor("#008000")); cmt.setFontItalic(True)
        cdt = QTextCharFormat(); cdt.setForeground(QColor("#888888"))
        self._rules = [
            (re.compile(r'<!--.*?-->', re.DOTALL), cmt),
            (re.compile(r'<!\[CDATA\[.*?\]\]>', re.DOTALL), cdt),
            (re.compile(r'</?[\w:.-]+'), tag),
            (re.compile(r'\b[\w:.-]+='), atn),
            (re.compile(r'"[^"]*"'), atv),
            (re.compile(r'>|/>'), tag),
        ]

    def highlightBlock(self, text: str):
        for pat, fmt in self._rules:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ─── View Widgets ─────────────────────────────────────────────────────────────

class TransformerView(QWidget):
    """Shows Content-Encoding, Transfer-Encoding, and decoded body preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._table = _TwoColTable("속성", "값")
        self._table.setFixedHeight(150)
        lay.addWidget(self._table)
        lay.addWidget(_h_line())

        self._edit = _make_edit()
        lay.addWidget(self._edit)

    def show_data(self, headers: dict, body: bytes):
        enc  = _hval(headers, "content-encoding") or "identity"
        xfer = _hval(headers, "transfer-encoding") or "-"
        orig = len(body)

        decoded, method = self._decompress(body, enc)
        dec_size = len(decoded) if decoded is not None else orig

        self._table.load([
            ("Content-Encoding",   enc),
            ("Transfer-Encoding",  xfer),
            ("원본 크기",           f"{orig:,} bytes"),
            ("디코딩 크기",         f"{dec_size:,} bytes"),
            ("디코딩 방식",         method),
        ])

        display = decoded if decoded is not None else body
        if display:
            self._edit.setPlainText(display.decode("utf-8", errors="replace"))
        else:
            self._edit.setPlainText("(비어 있음)")

    @staticmethod
    def _decompress(body: bytes, enc: str) -> tuple[Optional[bytes], str]:
        if not body:
            return None, "없음"
        e = enc.lower()
        try:
            if "gzip" in e:
                return gzip.decompress(body), "gzip → 압축 해제됨"
            if "deflate" in e:
                try:
                    return zlib.decompress(body), "deflate (zlib) → 압축 해제됨"
                except zlib.error:
                    return zlib.decompress(body, -zlib.MAX_WBITS), "deflate (raw) → 압축 해제됨"
            if "br" in e:
                try:
                    import brotli  # type: ignore
                    return brotli.decompress(body), "brotli → 압축 해제됨"
                except ImportError:
                    return None, "brotli (pip install brotli 필요)"
            if "base64" in e:
                return base64.b64decode(body), "base64 → 디코딩됨"
        except Exception as ex:
            return None, f"실패: {ex}"
        return None, "identity (변환 없음)"


class HeadersView(QWidget):
    """HTTP headers in a two-column table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._table = _TwoColTable("헤더", "값")
        lay.addWidget(self._table)

    def show_headers(self, first_line: str, headers: dict):
        rows = [("", first_line)] + list(headers.items())
        self._table.load(rows)
        # Bold the first-line row
        for col in range(2):
            item = self._table.item(0, col)
            if item:
                f = item.font(); f.setBold(True); item.setFont(f)


class TextViewWidget(QWidget):
    """Body decoded to plain text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = _make_edit()
        lay.addWidget(self._edit)

    def show_body(self, body: bytes, headers: dict):
        self._edit.setPlainText(_decode_body(body, headers) or "(비어 있음)")


class SyntaxViewWidget(QWidget):
    """Body with automatic syntax highlighting (JSON / XML / HTML)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = _make_edit()
        self._hl = None
        lay.addWidget(self._edit)

    def show_body(self, body: bytes, headers: dict):
        ct = _ct_base(headers)
        text = _decode_body(body, headers)

        self._hl = None
        doc = self._edit.document()

        if "json" in ct:
            try:
                text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except Exception:
                pass
            self._hl = _JsonHL(doc)
        elif any(x in ct for x in ("xml", "html", "svg", "xhtml")):
            self._hl = _XmlHL(doc)
        elif not ct:
            # heuristic detection
            stripped = text.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                    self._hl = _JsonHL(doc)
                except Exception:
                    pass
            elif stripped.startswith("<"):
                self._hl = _XmlHL(doc)

        self._edit.setPlainText(text or "(비어 있음)")


class ImageViewWidget(QWidget):
    """Renders image body (PNG, JPEG, GIF, BMP, WebP, ICO)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: #e8e8e8; }")

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent;")
        self._scroll.setWidget(self._label)
        lay.addWidget(self._scroll)

        self._info = QLabel()
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info.setStyleSheet("color: #666; font-size: 11px;")
        lay.addWidget(self._info)

    def show_body(self, body: bytes, headers: dict):
        ct = _ct_base(headers)
        is_image = "image/" in ct or any(
            ct.endswith(x) for x in ("png", "jpeg", "jpg", "gif", "bmp", "webp", "ico", "svg")
        )
        if not body:
            self._label.setText("(비어 있음)")
            self._info.setText("")
            return
        if not is_image:
            self._label.setText(f"이미지가 아닙니다\nContent-Type: {ct or '알 수 없음'}")
            self._info.setText("")
            return

        pix = QPixmap()
        if pix.loadFromData(body):
            avail_w = max(self._scroll.width() - 20, 200)
            avail_h = max(self._scroll.height() - 20, 200)
            scaled = pix.scaled(
                avail_w, avail_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._label.setPixmap(scaled)
            self._info.setText(
                f"{pix.width()} × {pix.height()} px  ·  {len(body):,} bytes"
            )
        else:
            self._label.setText("(이미지를 디코딩할 수 없습니다)")
            self._info.setText("")


class HexViewWidget(QWidget):
    """Hex dump: OFFSET  HH HH ...  ASCII"""

    COLS = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = _make_edit()
        lay.addWidget(self._edit)

    def show_body(self, body: bytes):
        if not body:
            self._edit.setPlainText("(비어 있음)")
            return
        n = self.COLS
        lines = []
        for i in range(0, len(body), n):
            chunk = body[i : i + n]
            off   = f"{i:08x}"
            hex_  = " ".join(f"{b:02x}" for b in chunk).ljust(n * 3 - 1)
            asc   = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{off}  {hex_}  {asc}")
        self._edit.setPlainText("\n".join(lines))


class WebViewWidget(QWidget):
    """Renders HTML/text in QWebEngineView; falls back to source view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
            self._web = QWebEngineView()
            lay.addWidget(self._web)
            self._mode = "web"
        except ImportError:
            self._web = None
            note = QLabel("  ⚠  PySide6-WebEngine 미설치 — HTML 소스로 표시합니다")
            note.setStyleSheet(
                "background:#fff3cd; color:#856404; font-size:11px; padding:4px 8px;"
            )
            lay.addWidget(note)
            self._edit = _make_edit()
            lay.addWidget(self._edit)
            self._mode = "text"

    def show_body(self, body: bytes, headers: dict):
        ct  = _ct_base(headers)
        text = _decode_body(body, headers)
        if self._mode == "web" and self._web is not None:
            if "html" in ct or (text or "").lstrip().startswith("<"):
                self._web.setHtml(text or "")
            else:
                self._web.setContent(body or b"", ct or "text/plain")
        else:
            self._edit.setPlainText(text or "(비어 있음)")


class AuthView(QWidget):
    """Parses Authorization / WWW-Authenticate / API-Key headers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self._table = _TwoColTable("항목", "값")
        lay.addWidget(self._table)
        lay.addWidget(_h_line())

        detail_lbl = QLabel("디코딩 상세 정보")
        detail_lbl.setStyleSheet("color:#555; font-size:11px; font-weight:bold;")
        lay.addWidget(detail_lbl)

        self._detail = _make_edit()
        self._detail.setMaximumHeight(180)
        lay.addWidget(self._detail)

    def show_data(self, headers: dict, is_request: bool):
        rows: list[tuple[str, str]] = []
        details: list[str] = []

        if is_request:
            auth = _hval(headers, "authorization")
            if auth:
                scheme, _, cred = auth.partition(" ")
                rows.append(("인증 방식", scheme.strip()))
                sl = scheme.strip().lower()
                if sl == "basic":
                    try:
                        decoded = base64.b64decode(cred.strip()).decode("utf-8", errors="replace")
                        user, _, pwd = decoded.partition(":")
                        rows += [("사용자명", user), ("비밀번호", "●" * len(pwd))]
                        details.append(f"[Basic 인증]\n사용자명: {user}\n비밀번호: {pwd}")
                    except Exception:
                        rows.append(("자격 증명", cred[:80]))
                elif sl == "bearer":
                    rows.append(("토큰 (미리보기)", cred[:40] + ("…" if len(cred) > 40 else "")))
                    details.append(f"[Bearer 토큰]\n{cred}")
                    # Try JWT payload decode
                    parts = cred.split(".")
                    if len(parts) == 3:
                        try:
                            pad = parts[1] + "=" * (4 - len(parts[1]) % 4)
                            payload = json.loads(base64.urlsafe_b64decode(pad))
                            details.append(
                                "\n[JWT 페이로드]\n"
                                + json.dumps(payload, indent=2, ensure_ascii=False)
                            )
                        except Exception:
                            pass
                elif sl == "digest":
                    rows.append(("Digest 파라미터", cred[:120]))
                elif sl == "oauth":
                    rows.append(("OAuth 토큰", cred[:80]))
                else:
                    rows.append(("자격 증명", cred[:80]))

            proxy = _hval(headers, "proxy-authorization")
            if proxy:
                rows.append(("Proxy-Authorization", proxy[:80]))

            for key_header in ("x-api-key", "api-key", "x-auth-token", "x-access-token"):
                val = _hval(headers, key_header)
                if val:
                    rows.append((key_header, val[:60] + ("…" if len(val) > 60 else "")))
        else:
            for h in ("www-authenticate", "proxy-authenticate"):
                val = _hval(headers, h)
                if val:
                    rows.append((h.title().replace("-", "-"), val))

        if not rows:
            rows = [("(인증 헤더 없음)", "")]

        self._table.load(rows)
        self._detail.setPlainText("\n".join(details) if details else "")


class CachingView(QWidget):
    """Parses Cache-Control, ETag, Last-Modified, Expires, Age, Vary, etc."""

    _HEADERS = [
        "cache-control", "etag", "last-modified", "expires",
        "age", "vary", "pragma", "date", "if-none-match",
        "if-modified-since", "if-match", "if-unmodified-since",
        "surrogate-control", "cdn-cache-control",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._table = _TwoColTable("헤더 / 지시어", "값")
        lay.addWidget(self._table)

    def show_data(self, headers: dict):
        lower = {k.lower(): v for k, v in headers.items()}
        rows: list[tuple[str, str]] = []

        for h in self._HEADERS:
            v = lower.get(h, "")
            if not v:
                continue
            label = h.title().replace("-", "-")
            rows.append((label, v))
            if h == "cache-control":
                for directive in (d.strip() for d in v.split(",")):
                    if "=" in directive:
                        dk, _, dv = directive.partition("=")
                        rows.append((f"  ╰ {dk.strip()}", dv.strip()))
                    elif directive:
                        rows.append((f"  ╰ {directive}", "✓"))

        if not rows:
            rows = [("(캐시 관련 헤더 없음)", "")]
        self._table.load(rows)


class CookiesView(QWidget):
    """Parses Cookie (request) and Set-Cookie (response) headers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._table = _TwoColTable("이름", "값")
        lay.addWidget(self._table)

    def show_data(self, headers: dict, is_request: bool):
        rows: list[tuple[str, str]] = []

        if is_request:
            cookie_str = _hval(headers, "cookie") or ""
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    rows.append((k.strip(), v.strip()))
                elif pair:
                    rows.append((pair, ""))
        else:
            for k, v in headers.items():
                if k.lower() != "set-cookie":
                    continue
                parts = [p.strip() for p in v.split(";")]
                if not parts:
                    continue
                # first part is name=value
                nv = parts[0]
                cn, _, cv = nv.partition("=")
                rows.append((cn.strip(), cv.strip()))
                for attr in parts[1:]:
                    if attr:
                        ak, _, av = attr.partition("=")
                        rows.append((f"  ╰ {ak.strip()}", av.strip()))
                rows.append(("", ""))  # separator

        if not rows or all(r == ("", "") for r in rows):
            rows = [("(쿠키 헤더 없음)", "")]
        self._table.load(rows)


class RawView(QWidget):
    """Full raw HTTP message (request line/status line + headers + body)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = _make_edit()
        lay.addWidget(self._edit)

    def show_raw(self, first_line: str, headers: dict, body: bytes):
        lines = [first_line]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        lines.append("")
        if body:
            lines.append(body.decode("utf-8", errors="replace"))
        self._edit.setPlainText("\n".join(lines))


class JSONView(QWidget):
    """Pretty-printed, syntax-highlighted JSON."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = _make_edit()
        self._hl = _JsonHL(self._edit.document())
        lay.addWidget(self._edit)

    def show_body(self, body: bytes, headers: dict):
        text = _decode_body(body, headers)
        if not text:
            self._edit.setPlainText("(비어 있음)")
            return
        try:
            self._edit.setPlainText(
                json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            )
        except (json.JSONDecodeError, ValueError):
            self._edit.setPlainText("(유효한 JSON이 아닙니다)\n\n" + text)


class XMLView(QWidget):
    """Pretty-printed, syntax-highlighted XML."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = _make_edit()
        self._hl = _XmlHL(self._edit.document())
        lay.addWidget(self._edit)

    def show_body(self, body: bytes, headers: dict):
        text = _decode_body(body, headers)
        if not text:
            self._edit.setPlainText("(비어 있음)")
            return
        try:
            import xml.dom.minidom
            dom = xml.dom.minidom.parseString(body)
            self._edit.setPlainText(dom.toprettyxml(indent="  "))
        except Exception:
            self._edit.setPlainText("(유효한 XML이 아닙니다)\n\n" + text)


# ─── Utility ──────────────────────────────────────────────────────────────────

def _hval(headers: dict, key_lower: str) -> str:
    """Case-insensitive header value lookup."""
    for k, v in headers.items():
        if k.lower() == key_lower:
            return v
    return ""
