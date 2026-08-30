from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QSplitter, QStatusBar, QVBoxLayout, QWidget,
)

from netscope.models.session import SessionEntry
from netscope.models.session_table_model import SessionTableModel
from netscope.proxy.engine import ProxyEngine, StubProxyEngine
from netscope.ui.detail_panel import DetailPanel
from netscope.ui.session_table import SessionTableView
from netscope.ui.toolbar import Toolbar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetScope — Network Traffic Inspector")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._proxy_port = 8888
        self._session_model = SessionTableModel(self)
        self._engine: ProxyEngine = StubProxyEngine(self)

        self._setup_ui()
        self._connect_signals()
        self._apply_global_style()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        self._toolbar = Toolbar()
        main_layout.addWidget(self._toolbar)

        # Splitter: session table (top) + detail panel (bottom)
        self._splitter = QSplitter(Qt.Orientation.Vertical)

        self._table_view = SessionTableView(self._session_model)
        self._splitter.addWidget(self._table_view)

        self._detail_panel = DetailPanel()
        self._splitter.addWidget(self._detail_panel)

        self._splitter.setSizes([400, 300])
        self._splitter.setHandleWidth(3)
        main_layout.addWidget(self._splitter, stretch=1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_label = QLabel("Ready")
        self._proxy_label = QLabel(f"Proxy: stopped | Port: {self._proxy_port}")
        self._session_count_label = QLabel("Sessions: 0")

        self._status_bar.addWidget(self._status_label, stretch=1)
        self._status_bar.addPermanentWidget(self._session_count_label)
        self._status_bar.addPermanentWidget(self._proxy_label)

    def _connect_signals(self):
        self._toolbar.start_clicked.connect(self._on_start)
        self._toolbar.stop_clicked.connect(self._on_stop)
        self._toolbar.clear_clicked.connect(self._on_clear)
        self._toolbar.search_changed.connect(self._table_view.set_filter)

        self._table_view.session_selected.connect(self._on_session_selected)

        self._engine.session_started.connect(self._on_session_started, Qt.ConnectionType.QueuedConnection)
        self._engine.session_completed.connect(self._on_session_completed, Qt.ConnectionType.QueuedConnection)
        self._engine.status_changed.connect(self._on_status_changed, Qt.ConnectionType.QueuedConnection)

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QSplitter::handle {
                background-color: #3e3e3e;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
            }
            QStatusBar QLabel {
                color: white;
                padding: 0 8px;
            }
            QTabWidget::pane {
                border: 1px solid #3e3e3e;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 6px 16px;
                border: 1px solid #3e3e3e;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab:hover {
                background-color: #333;
            }
            QLineEdit {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 6px;
                border-radius: 3px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
        """)

    @Slot()
    def _on_start(self):
        self._toolbar.set_capturing(True)
        self._engine.start(self._proxy_port)

    @Slot()
    def _on_stop(self):
        self._engine.stop()
        self._toolbar.set_capturing(False)

    @Slot()
    def _on_clear(self):
        self._session_model.clear()
        self._detail_panel.clear_display()
        self._session_count_label.setText("Sessions: 0")

    @Slot(int)
    def _on_session_selected(self, row: int):
        session = self._session_model.get_session(row)
        if session:
            self._detail_panel.show_session(session)

    @Slot(SessionEntry)
    def _on_session_started(self, session: SessionEntry):
        self._session_model.add_session(session)
        self._session_count_label.setText(f"Sessions: {self._session_model.rowCount()}")
        self._table_view.scroll_to_bottom()

    @Slot(int, dict)
    def _on_session_completed(self, session_id: int, fields: dict):
        self._session_model.update_session(session_id, **fields)

    @Slot(str)
    def _on_status_changed(self, status: str):
        self._status_label.setText(status)
        if "Capturing" in status:
            self._proxy_label.setText(f"Proxy: running | Port: {self._proxy_port}")
        else:
            self._proxy_label.setText(f"Proxy: stopped | Port: {self._proxy_port}")

    def closeEvent(self, event):
        if self._engine.is_running():
            self._engine.stop()
        super().closeEvent(event)
