"""
세션 비교 (Diff) 다이얼로그.

두 SessionEntry를 나란히 보여주며 헤더/바디의 변경점을 줄 단위로 하이라이트한다.
탭 구성: [요청]  — 요청 헤더 + 요청 바디
         [응답]  — 응답 헤더 + 응답 바디
"""
from __future__ import annotations

import difflib
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QSizePolicy, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry

# ── Color palette ──────────────────────────────────────────────────────────────
_C_ADD   = "#e6ffec"   # 추가된 줄 (B에만 있음)
_C_DEL   = "#ffebe9"   # 삭제된 줄 (A에만 있음)
_C_CHG_A = "#fff0b3"   # 변경 전 (A쪽)
_C_CHG_B = "#ddf4ff"   # 변경 후 (B쪽)
_C_EQL   = "#ffffff"   # 동일
_C_BLANK = "#f6f8fa"   # 빈 줄 패딩

_MAX_BODY_CHARS = 200_000


# ── Text helpers ───────────────────────────────────────────────────────────────

def _headers_text(headers: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in sorted(headers.items()))


def _body_text(body: bytes, headers: dict) -> str:
    if not body:
        return ""
    ct = (headers.get("content-type") or headers.get("Content-Type") or "").lower()
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return f"<binary {len(body):,} bytes>"
    if "json" in ct:
        try:
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except Exception:
            pass
    if len(text) > _MAX_BODY_CHARS:
        text = text[:_MAX_BODY_CHARS] + f"\n… (표시 생략, 전체 {len(text):,} 자)"
    return text


# ── Diff engine ────────────────────────────────────────────────────────────────

def _compute_rows(
    lines_a: list[str],
    lines_b: list[str],
) -> list[tuple[str, str, str]]:
    """
    Returns [(left_text, right_text, tag), ...]
    tag: 'equal' | 'replace_a|replace_b' | 'replace_a|blank' |
         'blank|replace_b' | 'delete' | 'insert'
    Blank padding lines are inserted so both sides have the same row count.
    """
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    rows: list[tuple[str, str, str]] = []

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for line in lines_a[i1:i2]:
                rows.append((line, line, "equal"))
        elif op == "replace":
            la, lb = lines_a[i1:i2], lines_b[j1:j2]
            for k in range(max(len(la), len(lb))):
                l = la[k] if k < len(la) else ""
                r = lb[k] if k < len(lb) else ""
                lt = "replace_a" if k < len(la) else "blank"
                rt = "replace_b" if k < len(lb) else "blank"
                rows.append((l, r, f"{lt}|{rt}"))
        elif op == "delete":
            for line in lines_a[i1:i2]:
                rows.append((line, "", "delete"))
        elif op == "insert":
            for line in lines_b[j1:j2]:
                rows.append(("", line, "insert"))

    return rows


def _row_colors(tag: str) -> tuple[str, str]:
    """Returns (left_color, right_color) for a diff row tag."""
    if tag == "equal":
        return _C_EQL, _C_EQL
    if tag == "delete":
        return _C_DEL, _C_BLANK
    if tag == "insert":
        return _C_BLANK, _C_ADD
    # replace_a|replace_b  /  replace_a|blank  /  blank|replace_b
    lt, rt = tag.split("|")
    lc = {"replace_a": _C_CHG_A, "blank": _C_BLANK}[lt]
    rc = {"replace_b": _C_CHG_B, "blank": _C_BLANK}[rt]
    return lc, rc


def _stats(rows: list[tuple[str, str, str]]) -> tuple[int, int, int]:
    """(added, removed, changed)"""
    a = r = c = 0
    for _, _, tag in rows:
        if tag == "insert":
            a += 1
        elif tag == "delete":
            r += 1
        elif "|" in tag:
            c += 1
    return a, r, c


def _stat_badge(added: int, removed: int, changed: int) -> str:
    parts: list[str] = []
    if added:
        parts.append(f"<span style='color:#27ae60'>+{added}</span>")
    if removed:
        parts.append(f"<span style='color:#c0392b'>−{removed}</span>")
    if changed:
        parts.append(f"<span style='color:#e67e22'>~{changed}</span>")
    return "  " + "  ".join(parts) if parts else ""


# ── _SideEdit ──────────────────────────────────────────────────────────────────

class _SideEdit(QPlainTextEdit):
    """Read-only monospace editor with per-line background colour support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        f = QFont("Courier New", 10)
        f.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(f)
        self.setStyleSheet(
            "QPlainTextEdit { border: none; border-top: 1px solid #e0e0e0; }"
        )

    def load(self, lines: list[tuple[str, str]]):
        """lines: [(text, hex_color), ...]"""
        self.clear()
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        for i, (text, color) in enumerate(lines):
            if i:
                cur.insertBlock()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(color))
            cur.setBlockCharFormat(fmt)
            cur.insertText(text, fmt)
        cur.endEditBlock()
        self.moveCursor(QTextCursor.MoveOperation.Start)


# ── _DiffPane  (헤더 OR 바디 — one section) ────────────────────────────────────

class _DiffPane(QWidget):
    """
    Section widget: title bar  +  side-by-side diff (left | right).
    Vertical scrollbars on left/right are kept in sync.
    """

    def __init__(self, section_title: str, label_a: str, label_b: str, parent=None):
        super().__init__(parent)
        self._base_title = section_title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── section title bar ─────────────────────────────────────────────
        self._title_lbl = QLabel()
        self._title_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._title_lbl.setStyleSheet(
            "padding: 4px 10px;"
            "background: #f0f4f8;"
            "border-top: 1px solid #d0d8e0;"
            "border-bottom: 1px solid #d0d8e0;"
            "font-size: 12px; font-weight: bold; color: #333;"
        )
        layout.addWidget(self._title_lbl)

        # ── column label row ──────────────────────────────────────────────
        col_bar = QWidget()
        col_bar.setStyleSheet("background: #fafafa; border-bottom: 1px solid #e8e8e8;")
        col_layout = QHBoxLayout(col_bar)
        col_layout.setContentsMargins(6, 3, 6, 3)
        col_layout.setSpacing(4)

        self._lbl_a = QLabel(label_a)
        self._lbl_a.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #c0392b;"
            " background: #ffebe9; padding: 2px 8px; border-radius: 3px;"
        )
        self._lbl_b = QLabel(label_b)
        self._lbl_b.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #27ae60;"
            " background: #e6ffec; padding: 2px 8px; border-radius: 3px;"
        )
        col_layout.addWidget(self._lbl_a)
        col_layout.addWidget(self._lbl_b)
        layout.addWidget(col_bar)

        # ── side-by-side editors ──────────────────────────────────────────
        self._h_split = QSplitter(Qt.Orientation.Horizontal)
        self._left  = _SideEdit()
        self._right = _SideEdit()
        self._h_split.addWidget(self._left)
        self._h_split.addWidget(self._right)
        layout.addWidget(self._h_split, stretch=1)

        # sync vertical scroll
        self._syncing = False
        self._left.verticalScrollBar().valueChanged.connect(self._sync_l2r)
        self._right.verticalScrollBar().valueChanged.connect(self._sync_r2l)

    # ── scroll sync ────────────────────────────────────────────────────────

    def _sync_l2r(self, v: int):
        if self._syncing:
            return
        self._syncing = True
        self._right.verticalScrollBar().setValue(v)
        self._syncing = False

    def _sync_r2l(self, v: int):
        if self._syncing:
            return
        self._syncing = True
        self._left.verticalScrollBar().setValue(v)
        self._syncing = False

    # ── public API ─────────────────────────────────────────────────────────

    def set_texts(self, text_a: str, text_b: str) -> tuple[int, int, int]:
        rows = _compute_rows(text_a.splitlines(), text_b.splitlines())
        left_lines:  list[tuple[str, str]] = []
        right_lines: list[tuple[str, str]] = []
        for l_txt, r_txt, tag in rows:
            lc, rc = _row_colors(tag)
            left_lines.append((l_txt, lc))
            right_lines.append((r_txt, rc))
        self._left.load(left_lines)
        self._right.load(right_lines)

        added, removed, changed = _stats(rows)
        badge = _stat_badge(added, removed, changed)
        self._title_lbl.setText(f"{self._base_title}{badge}")
        return added, removed, changed

    def splitter(self) -> QSplitter:
        return self._h_split


# ── _SideBySideTab  (요청 OR 응답 — one full tab) ─────────────────────────────

class _SideBySideTab(QWidget):
    """
    A complete tab view: headers pane (top) + body pane (bottom),
    separated by a vertical QSplitter.
    The two horizontal splitters are kept in sync so columns stay aligned.
    """

    def __init__(self, label_a: str, label_b: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setHandleWidth(6)

        self._hdr_pane  = _DiffPane("헤더",  label_a, label_b)
        self._body_pane = _DiffPane("바디",  label_a, label_b)

        v_split.addWidget(self._hdr_pane)
        v_split.addWidget(self._body_pane)
        v_split.setSizes([220, 480])
        layout.addWidget(v_split)

        # Keep the two horizontal splitters in sync so columns align
        self._h_syncing = False
        self._hdr_pane.splitter().splitterMoved.connect(self._sync_h_from_hdr)
        self._body_pane.splitter().splitterMoved.connect(self._sync_h_from_body)

    def _sync_h_from_hdr(self, pos: int, idx: int):
        if self._h_syncing:
            return
        self._h_syncing = True
        self._body_pane.splitter().moveSplitter(pos, idx)
        self._h_syncing = False

    def _sync_h_from_body(self, pos: int, idx: int):
        if self._h_syncing:
            return
        self._h_syncing = True
        self._hdr_pane.splitter().moveSplitter(pos, idx)
        self._h_syncing = False

    def set_data(
        self,
        hdr_a: str, hdr_b: str,
        body_a: str, body_b: str,
    ) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        hdr_stats  = self._hdr_pane.set_texts(hdr_a, hdr_b)
        body_stats = self._body_pane.set_texts(body_a, body_b)
        return hdr_stats, body_stats


# ── Summary / helpers ──────────────────────────────────────────────────────────

def _session_badge(s: SessionEntry, color: str) -> QLabel:
    status = f"  →  {s.status_code}" if s.status_code else ""
    lbl = QLabel(
        f"<b style='color:{color}'>#{s.id}</b> &nbsp;"
        f"<b>{s.method}</b> &nbsp;"
        f"<span style='color:#444'>{s.url}{status}</span>"
    )
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setWordWrap(True)
    return lbl


def _tab_title(base: str, hdr_stats: tuple, body_stats: tuple) -> str:
    a = hdr_stats[0] + body_stats[0]
    r = hdr_stats[1] + body_stats[1]
    c = hdr_stats[2] + body_stats[2]
    parts: list[str] = []
    if a:
        parts.append(f"+{a}")
    if r:
        parts.append(f"−{r}")
    if c:
        parts.append(f"~{c}")
    suffix = f"  ({', '.join(parts)})" if parts else ""
    return f"{base}{suffix}"


# ── DiffDialog ─────────────────────────────────────────────────────────────────

class DiffDialog(QDialog):
    """세션 나란히 비교 — 요청 탭 / 응답 탭 각각 헤더+바디 diff 표시."""

    def __init__(
        self,
        session_a: SessionEntry,
        session_b: SessionEntry,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"세션 비교  —  #{session_a.id}  vs  #{session_b.id}")
        self.setMinimumSize(1100, 680)
        self.resize(1300, 780)
        self._setup_ui(session_a, session_b)

    def _setup_ui(self, a: SessionEntry, b: SessionEntry):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Summary bar ────────────────────────────────────────────────────
        summary = QFrame()
        summary.setStyleSheet(
            "QFrame { background: #f8f9fa; border: 1px solid #e0e0e0;"
            " border-radius: 6px; }"
        )
        s_lay = QHBoxLayout(summary)
        s_lay.setContentsMargins(12, 8, 12, 8)
        s_lay.addWidget(_session_badge(a, "#c0392b"), stretch=1)
        vs = QLabel("vs")
        vs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vs.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #aaa; min-width: 30px;"
        )
        s_lay.addWidget(vs)
        s_lay.addWidget(_session_badge(b, "#27ae60"), stretch=1)
        layout.addWidget(summary)

        label_a = f"#{a.id}  {a.method}  {a.host or a.url[:40]}"
        label_b = f"#{b.id}  {b.method}  {b.host or b.url[:40]}"

        # ── Tabs ───────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, stretch=1)

        # 요청 탭
        req_tab = _SideBySideTab(label_a, label_b)
        req_hdr_stats, req_body_stats = req_tab.set_data(
            _headers_text(a.request_headers),
            _headers_text(b.request_headers),
            _body_text(a.request_body,  a.request_headers),
            _body_text(b.request_body,  b.request_headers),
        )
        tabs.addTab(req_tab, _tab_title("요청", req_hdr_stats, req_body_stats))

        # 응답 탭
        res_tab = _SideBySideTab(label_a, label_b)
        res_hdr_stats, res_body_stats = res_tab.set_data(
            _headers_text(a.response_headers),
            _headers_text(b.response_headers),
            _body_text(a.response_body, a.response_headers),
            _body_text(b.response_body, b.response_headers),
        )
        tabs.addTab(res_tab, _tab_title("응답", res_hdr_stats, res_body_stats))

        # ── Close button ───────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
