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


def _v_sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFixedWidth(1)
    f.setStyleSheet("background: #d0d0d0;")
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
    """Renders HTML/text in QWebEngineView with live preview, resource-block,
    and mobile/desktop viewport switching.

    Toolbar (left → right):
    - 외부 리소스 차단 checkbox   – blocks external HTTP/HTTPS via URL interceptor
    - ↺ 새로고침 button           – re-renders current body
    - | separator |
    - 🖥 데스크톱 / 📱 모바일     – viewport preset toggle (exclusive button group)
    - stretch
    - status label

    Mobile preset  : UA = iPhone 17, viewport width = 390 px
    Desktop preset : UA = Chrome/Windows, viewport width = 1280 px
    Falls back to plain-text if PySide6-WebEngine is not installed.
    """

    _MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )
    _DESKTOP_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    _MOBILE_W  = 390
    _DESKTOP_W = 1280

    # ── segmented-button style ──────────────────────────────────────────────
    _SEG_L = (
        "QPushButton { font-size:11px; padding:0 10px; height:22px;"
        " border:1px solid #bbb; border-right:none;"
        " border-radius:3px 0 0 3px; background:#fff; color:#333; }"
        "QPushButton:hover:!checked { background:#f0f0f0; }"
        "QPushButton:checked { background:#0078d4; color:#fff; border-color:#0060b0; }"
    )
    _SEG_R = (
        "QPushButton { font-size:11px; padding:0 10px; height:22px;"
        " border:1px solid #bbb;"
        " border-radius:0 3px 3px 0; background:#fff; color:#333; }"
        "QPushButton:hover:!checked { background:#f0f0f0; }"
        "QPushButton:checked { background:#0078d4; color:#fff; border-color:#0060b0; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._body: bytes = b""
        self._headers: dict = {}
        self._block_chk  = None   # set only in web mode
        self._mobile_btn = None
        self._view_grp   = None
        self._is_mobile  = False

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
            from PySide6.QtWebEngineCore import (  # type: ignore
                QWebEnginePage, QWebEngineProfile,
                QWebEngineUrlRequestInterceptor,
            )
            from PySide6.QtWidgets import (
                QButtonGroup, QCheckBox, QHBoxLayout, QPushButton,
            )

            # ── URL interceptor ───────────────────────────────────────────
            class _Interceptor(QWebEngineUrlRequestInterceptor):
                def __init__(self2, parent=None):
                    super().__init__(parent)
                    self2._block = False

                def set_block(self2, v: bool):
                    self2._block = v

                def interceptRequest(self2, info):
                    if not self2._block:
                        return
                    scheme = info.requestUrl().scheme()
                    if scheme not in ("data", "about", "blob", "qrc", ""):
                        info.block(True)

            # ── Toolbar ───────────────────────────────────────────────────
            bar = QWidget()
            bar.setFixedHeight(32)
            bar.setStyleSheet(
                "QWidget { background:#f5f5f5; border-bottom:1px solid #e0e0e0; }"
            )
            h = QHBoxLayout(bar)
            h.setContentsMargins(8, 0, 8, 0)
            h.setSpacing(6)

            # Block checkbox
            self._block_chk = QCheckBox("외부 리소스 차단")
            self._block_chk.setToolTip(
                "외부 도메인의 CSS, JS, 이미지 등 모든 리소스 로드를 차단합니다"
            )
            self._block_chk.setStyleSheet("font-size:11px;")
            h.addWidget(self._block_chk)

            # Reload button
            reload_btn = QPushButton("↺  새로고침")
            reload_btn.setFixedHeight(22)
            reload_btn.setStyleSheet(
                "QPushButton { font-size:11px; padding:0 10px; border:1px solid #ccc;"
                " border-radius:3px; background:#fff; color:#333; }"
                "QPushButton:hover { background:#e8e8e8; }"
                "QPushButton:pressed { background:#d0d0d0; }"
            )
            reload_btn.clicked.connect(self._reload)
            h.addWidget(reload_btn)

            # Separator
            h.addWidget(_v_sep())
            h.setSpacing(0)

            # Viewport toggle — Desktop (left) / Mobile (right)
            desktop_btn = QPushButton("🖥  데스크톱")
            desktop_btn.setCheckable(True)
            desktop_btn.setChecked(True)
            desktop_btn.setStyleSheet(self._SEG_L)

            self._mobile_btn = QPushButton("📱  모바일")
            self._mobile_btn.setCheckable(True)
            self._mobile_btn.setStyleSheet(self._SEG_R)

            self._view_grp = QButtonGroup(self)
            self._view_grp.setExclusive(True)
            self._view_grp.addButton(desktop_btn, 0)   # id 0 = desktop
            self._view_grp.addButton(self._mobile_btn, 1)  # id 1 = mobile
            self._view_grp.idToggled.connect(self._on_viewport_toggled)

            h.addWidget(desktop_btn)
            h.addWidget(self._mobile_btn)

            h.addStretch()
            h.setSpacing(6)

            self._status_lbl = QLabel()
            self._status_lbl.setStyleSheet("color:#888; font-size:10px;")
            h.addWidget(self._status_lbl)

            lay.addWidget(bar)

            # ── Profile + interceptor ─────────────────────────────────────
            self._profile = QWebEngineProfile()   # off-the-record (no disk cache)
            self._interceptor = _Interceptor(self._profile)
            self._profile.setUrlRequestInterceptor(self._interceptor)
            self._profile.setHttpUserAgent(self._DESKTOP_UA)

            self._page = QWebEnginePage(self._profile, self)
            self._web = QWebEngineView()
            self._web.setPage(self._page)
            self._page.loadFinished.connect(self._on_load_finished)

            self._block_chk.toggled.connect(self._on_block_toggled)

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

    # ── static helper ─────────────────────────────────────────────────────────

    @staticmethod
    def _set_viewport(html: str, width: int) -> str:
        """Insert or replace <meta name="viewport"> with the given pixel width."""
        tag = f'<meta name="viewport" content="width={width}, initial-scale=1">'
        # Replace an existing viewport meta
        replaced, n = re.subn(
            r'<meta\s[^>]*name=["\']viewport["\'][^>]*/?>',
            tag, html, flags=re.IGNORECASE,
        )
        if n:
            return replaced
        # Inject right after <head …>
        m = re.search(r'<head[^>]*>', html, re.IGNORECASE)
        if m:
            return html[:m.end()] + "\n" + tag + html[m.end():]
        # No <head> — prepend
        return tag + "\n" + html

    # ── private slots ─────────────────────────────────────────────────────────

    def _on_block_toggled(self, checked: bool):
        self._interceptor.set_block(checked)
        self._reload()

    def _on_viewport_toggled(self, btn_id: int, checked: bool):
        if not checked:
            return
        self._is_mobile = (btn_id == 1)
        ua = self._MOBILE_UA if self._is_mobile else self._DESKTOP_UA
        self._profile.setHttpUserAgent(ua)
        self._reload()

    def _reload(self):
        if self._mode == "web" and self._web is not None:
            self._render(self._body, self._headers)

    def _render(self, body: bytes, headers: dict):
        ct   = _ct_base(headers)
        text = _decode_body(body, headers)
        vp_w = self._MOBILE_W if self._is_mobile else self._DESKTOP_W

        if "html" in ct or (text or "").lstrip().startswith("<"):
            html = self._set_viewport(text or "", vp_w)
            self._web.setHtml(html)
        else:
            self._web.setContent(body or b"", ct or "text/plain")

        vp_label = f"📱 {vp_w}px" if self._is_mobile else f"🖥 {vp_w}px"
        self._status_lbl.setText(f"렌더링 중…  {vp_label}  ({len(body):,} bytes)")

    def _on_load_finished(self, ok: bool):
        ct      = _ct_base(self._headers)
        blocked = "  ·  차단 중" if (
            self._block_chk and self._block_chk.isChecked()
        ) else ""
        vp_label = f"📱 {self._MOBILE_W}px" if self._is_mobile else f"🖥 {self._DESKTOP_W}px"
        icon = "✓" if ok else "✗"
        self._status_lbl.setText(
            f"{icon}  {ct or 'text/html'}  ·  {vp_label}"
            f"  ·  {len(self._body):,} bytes{blocked}"
        )

    # ── public ────────────────────────────────────────────────────────────────

    def show_body(self, body: bytes, headers: dict):
        self._body    = body    or b""
        self._headers = headers or {}
        if self._mode == "web" and self._web is not None:
            self._render(self._body, self._headers)
        else:
            self._edit.setPlainText(_decode_body(body, headers) or "(비어 있음)")


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
