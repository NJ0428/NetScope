from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QPushButton, QWidget,
)


class Toolbar(QWidget):
    """Toolbar with capture controls, search, and clear."""

    start_clicked = Signal()
    stop_clicked = Signal()
    clear_clicked = Signal()
    search_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._btn_start = QPushButton("▶ Start")
        self._btn_start.setFixedWidth(100)
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; "
            "border: none; padding: 6px 12px; border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2ecc71; }"
        )
        self._btn_start.clicked.connect(self.start_clicked)

        self._btn_stop = QPushButton("■ Stop")
        self._btn_stop.setFixedWidth(100)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; "
            "border: none; padding: 6px 12px; border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #c0392b; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._btn_stop.clicked.connect(self.stop_clicked)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search sessions… (host, path, method)")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self.search_changed)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(80)
        self._btn_clear.setStyleSheet(
            "QPushButton { background-color: #555; color: white; "
            "border: none; padding: 6px 12px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #666; }"
        )
        self._btn_clear.clicked.connect(self.clear_clicked)

        layout.addWidget(self._btn_start)
        layout.addWidget(self._btn_stop)
        layout.addWidget(self._search, stretch=1)
        layout.addWidget(self._btn_clear)

    def set_capturing(self, capturing: bool):
        self._btn_start.setEnabled(not capturing)
        self._btn_stop.setEnabled(capturing)
