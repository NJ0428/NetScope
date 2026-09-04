from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from netscope.models.session import SessionEntry
from netscope.ui.views import (
    AuthView, CachingView, CookiesView, HeadersView, HexViewWidget,
    ImageViewWidget, JSONView, RawView, SyntaxViewWidget, TextViewWidget,
    TransformerView, WebViewWidget, XMLView,
)


class DetailPanel(QWidget):
    """Request / Response inspector with full tab set."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        lay.addWidget(self._tabs)

        self._req = _SidePanel(is_request=True)
        self._res = _SidePanel(is_request=False)
        self._tabs.addTab(self._req, "Request")
        self._tabs.addTab(self._res, "Response")

    def show_session(self, session: SessionEntry):
        self._req.show_session(session)
        self._res.show_session(session)

    def clear_display(self):
        pass


class _SidePanel(QWidget):
    """One side (request or response) with all viewer tabs."""

    _TAB_DEFS = [
        ("Transformer", "transformer"),
        ("Headers",     "headers"),
        ("TextView",    "textview"),
        ("SyntaxView",  "syntaxview"),
        ("ImageView",   "imageview"),
        ("HexView",     "hexview"),
        ("WebView",     "webview"),
        ("Auth",        "auth"),
        ("Caching",     "caching"),
        ("Cookies",     "cookies"),
        ("Raw",         "raw"),
        ("JSON",        "jsonview"),
        ("XML",         "xmlview"),
    ]

    def __init__(self, is_request: bool, parent=None):
        super().__init__(parent)
        self._is_req = is_request

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        lay.addWidget(self._tabs)

        self.transformer = TransformerView()
        self.headers     = HeadersView()
        self.textview    = TextViewWidget()
        self.syntaxview  = SyntaxViewWidget()
        self.imageview   = ImageViewWidget()
        self.hexview     = HexViewWidget()
        self.webview     = WebViewWidget()
        self.auth        = AuthView()
        self.caching     = CachingView()
        self.cookies     = CookiesView()
        self.raw         = RawView()
        self.jsonview    = JSONView()
        self.xmlview     = XMLView()

        for label, attr in self._TAB_DEFS:
            self._tabs.addTab(getattr(self, attr), label)

    def show_session(self, session: SessionEntry):
        if self._is_req:
            hdrs  = session.request_headers
            body  = session.request_body
            first = f"{session.method} {session.path} HTTP/1.1"
        else:
            hdrs  = session.response_headers
            body  = session.response_body
            first = f"HTTP/1.1 {session.status_code}"

        self.transformer.show_data(hdrs, body)
        self.headers    .show_headers(first, hdrs)
        self.textview   .show_body(body, hdrs)
        self.syntaxview .show_body(body, hdrs)
        self.imageview  .show_body(body, hdrs)
        self.hexview    .show_body(body)
        self.webview    .show_body(body, hdrs)
        self.auth       .show_data(hdrs, self._is_req)
        self.caching    .show_data(hdrs)
        self.cookies    .show_data(hdrs, self._is_req)
        self.raw        .show_raw(first, hdrs, body)
        self.jsonview   .show_body(body, hdrs)
        self.xmlview    .show_body(body, hdrs)
