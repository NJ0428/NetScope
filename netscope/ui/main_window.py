from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
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
        self._setup_menu()
        self._connect_signals()
        self._apply_global_style()

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("File")
        file_menu.addAction(QAction("New Session", self, shortcut=QKeySequence.StandardKey.New))
        file_menu.addAction(QAction("Open...", self, shortcut=QKeySequence.StandardKey.Open))
        file_menu.addAction(QAction("Save", self, shortcut=QKeySequence.StandardKey.Save))
        file_menu.addAction(QAction("Save As...", self, shortcut=QKeySequence("Ctrl+Shift+S")))
        file_menu.addSeparator()
        file_menu.addAction(QAction("Import...", self))
        file_menu.addAction(QAction("Export...", self))
        file_menu.addSeparator()
        act_quit = QAction("Quit", self, shortcut=QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Edit
        edit_menu = mb.addMenu("Edit")
        edit_menu.addAction(QAction("Find", self, shortcut=QKeySequence.StandardKey.Find))
        edit_menu.addSeparator()
        edit_menu.addAction(QAction("Copy", self, shortcut=QKeySequence.StandardKey.Copy))
        edit_menu.addAction(QAction("Select All", self, shortcut=QKeySequence.StandardKey.SelectAll))
        edit_menu.addSeparator()
        edit_menu.addAction(QAction("Preferences...", self))

        # Rules
        rules_menu = mb.addMenu("Rules")
        rules_menu.addAction(QAction("Manage Rules...", self))
        rules_menu.addSeparator()
        rules_menu.addAction(QAction("Enable Breakpoints", self))
        rules_menu.addAction(QAction("Automatic Breakpoints", self))
        rules_menu.addSeparator()
        rules_menu.addAction(QAction("Custom Rules...", self))

        # Tools
        tools_menu = mb.addMenu("Tools")
        tools_menu.addAction(QAction("Options...", self))
        tools_menu.addSeparator()
        tools_menu.addAction(QAction("Certificate Manager", self))
        tools_menu.addAction(QAction("Proxy Settings...", self))
        tools_menu.addSeparator()
        tools_menu.addAction(QAction("WinConfig", self))

        # View
        view_menu = mb.addMenu("View")
        act_toolbar = QAction("Toolbar", self, checkable=True, checked=True)
        act_toolbar.triggered.connect(lambda v: self._toolbar.setVisible(v))
        view_menu.addAction(act_toolbar)
        act_status = QAction("Status Bar", self, checkable=True, checked=True)
        act_status.triggered.connect(lambda v: self._status_bar.setVisible(v))
        view_menu.addAction(act_status)
        view_menu.addSeparator()
        view_menu.addAction(QAction("Reset Layout", self))

        # Help
        help_menu = mb.addMenu("Help")
        help_menu.addAction(QAction("Documentation", self))
        help_menu.addAction(QAction("Keyboard Shortcuts", self))
        help_menu.addSeparator()
        help_menu.addAction(QAction("About NetScope", self))

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
        self._cap_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        self._engine.start(self._proxy_port)

    @Slot()
    def _on_stop(self):
        self._engine.stop()
        self._toolbar.set_capturing(False)
        self._cap_label.setText(_STATUS_IDLE)
        self._cap_label.setStyleSheet("color: #666666;")

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
                background-color: #ffffff;
                color: #1e1e1e;
            }
            QMenuBar {
                background-color: #f3f3f3;
                color: #1e1e1e;
                border-bottom: 1px solid #cccccc;
                padding: 2px 4px;
                font-size: 13px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 3px;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            QMenuBar::item:pressed {
                background-color: #007acc;
            }
            QMenu {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
                padding: 4px 0;
                font-size: 13px;
            }
            QMenu::item {
                padding: 5px 24px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #aaaaaa;
            }
            QMenu::separator {
                height: 1px;
                background: #cccccc;
                margin: 4px 8px;
            }
            QSplitter::handle {
                background-color: #e0e0e0;
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
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                color: #666666;
                padding: 7px 18px;
                border: none;
                border-top: 2px solid transparent;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1e1e1e;
                border-top: 2px solid #007acc;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e8e8e8;
                color: #333333;
            }
            QScrollBar:vertical {
                background: #f0f0f0;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #aaaaaa;
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
    f.setStyleSheet("background-color: #cccccc;")
    return f


def _status_sep(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: rgba(255,255,255,0.85); padding: 0 14px; "
        "border-left: 1px solid rgba(255,255,255,0.2);"
    )
    return lbl
