from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QLabel, QMainWindow, QSplitter, QStackedWidget,
    QStatusBar, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry
from netscope.models.session_table_model import SessionTableModel
from netscope.proxy.engine import ProxyEngine, StubProxyEngine
from netscope.ui.detail_panel import DetailPanel
from netscope.ui.session_table import SessionTableView
from netscope.ui.toolbar import Toolbar
from netscope.ui.welcome_panel import WelcomePanel

_STATUS_IDLE    = "● Idle"
_STATUS_CAPTURE = "● Capturing"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetScope — Network Traffic Inspector")
        self.setMinimumSize(1024, 640)
        self.resize(1400, 860)

        self._proxy_port = 8888
        self._session_model = SessionTableModel(self)
        self._engine: ProxyEngine = StubProxyEngine(self)

        self._setup_ui()
        self._connect_signals()
        self._apply_global_style()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ① Toolbar
        self._toolbar = Toolbar()
        root_layout.addWidget(self._toolbar)

        root_layout.addWidget(_h_line())

        # ② Horizontal splitter: sidebar (left) | content (right)
        self._h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter.setHandleWidth(2)

        # Left — session list
        self._table_view = SessionTableView(self._session_model)
        self._h_splitter.addWidget(self._table_view)

        # Right — stacked: welcome (0) | inspector (1)
        self._right_stack = QStackedWidget()

        self._welcome_panel = WelcomePanel()
        self._detail_panel  = DetailPanel()

        self._right_stack.addWidget(self._welcome_panel)   # index 0
        self._right_stack.addWidget(self._detail_panel)    # index 1
        self._right_stack.setCurrentIndex(0)

        self._h_splitter.addWidget(self._right_stack)
        self._h_splitter.setSizes([360, 1040])
        self._h_splitter.setStretchFactor(0, 0)
        self._h_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._h_splitter, stretch=1)

        # ⑤ Status bar
        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self._status_bar)

        self._cap_label      = QLabel(_STATUS_IDLE)
        self._port_label     = _status_sep(f"Port  {self._proxy_port}")
        self._process_label  = _status_sep("Process  All")
        self._count_label    = _status_sep("Sessions  0")

        self._status_bar.addWidget(self._cap_label, stretch=1)
        self._status_bar.addPermanentWidget(self._process_label)
        self._status_bar.addPermanentWidget(self._port_label)
        self._status_bar.addPermanentWidget(self._count_label)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        self._toolbar.start_clicked.connect(self._on_start)
        self._toolbar.stop_clicked.connect(self._on_stop)
        self._toolbar.clear_clicked.connect(self._on_clear)
        self._toolbar.search_changed.connect(self._table_view.set_filter)
        self._toolbar.process_changed.connect(self._on_process_changed)

        self._table_view.session_selected.connect(self._on_session_selected)

        self._engine.session_started.connect(
            self._on_session_started, Qt.ConnectionType.QueuedConnection)
        self._engine.session_completed.connect(
            self._on_session_completed, Qt.ConnectionType.QueuedConnection)
        self._engine.status_changed.connect(
            self._on_status_changed, Qt.ConnectionType.QueuedConnection)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_start(self):
        self._toolbar.set_capturing(True)
        self._cap_label.setText(_STATUS_CAPTURE)
        self._cap_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        self._engine.start(self._proxy_port)

    @Slot()
    def _on_stop(self):
        self._engine.stop()
        self._toolbar.set_capturing(False)
        self._cap_label.setText(_STATUS_IDLE)
        self._cap_label.setStyleSheet("color: #888;")

    @Slot()
    def _on_clear(self):
        self._session_model.clear()
        self._right_stack.setCurrentIndex(0)
        self._count_label.setText("Sessions  0")

    @Slot(int)
    def _on_session_selected(self, row: int):
        session = self._session_model.get_session(row)
        if session:
            self._detail_panel.show_session(session)
            self._right_stack.setCurrentIndex(1)

    @Slot(SessionEntry)
    def _on_session_started(self, session: SessionEntry):
        self._session_model.add_session(session)
        self._count_label.setText(f"Sessions  {self._session_model.rowCount()}")
        self._table_view.scroll_to_bottom()

    @Slot(int, dict)
    def _on_session_completed(self, session_id: int, fields: dict):
        self._session_model.update_session(session_id, **fields)

    @Slot(str)
    def _on_status_changed(self, status: str):
        pass  # status managed by _on_start / _on_stop

    @Slot(str)
    def _on_process_changed(self, text: str):
        label = "All" if text == "All Processes" else text
        self._process_label.setText(f"Process  {label}")

    # ── Style ─────────────────────────────────────────────────────────────────

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QSplitter::handle {
                background-color: #2d2d2d;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
                font-size: 12px;
            }
            QStatusBar QLabel {
                color: white;
                padding: 0 10px;
            }
            QTabWidget::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #252526;
                color: #888;
                padding: 7px 18px;
                border: none;
                border-top: 2px solid transparent;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border-top: 2px solid #007acc;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2a2a2a;
                color: #bbb;
            }
            QScrollBar:vertical {
                background: #1e1e1e;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def closeEvent(self, event):
        if self._engine.is_running():
            self._engine.stop()
        super().closeEvent(event)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _h_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background-color: #333;")
    return f


def _status_sep(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: rgba(255,255,255,0.85); padding: 0 14px; "
        "border-left: 1px solid rgba(255,255,255,0.2);"
    )
    return lbl
