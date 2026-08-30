from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget,
)

_BTN = (
    "QPushButton {{ background-color: {bg}; color: white; border: none; "
    "padding: 5px 14px; border-radius: 3px; font-weight: bold; font-size: 12px; }}"
    "QPushButton:hover {{ background-color: {hover}; }}"
    "QPushButton:disabled {{ background-color: #3a3a3a; color: #666; }}"
)


class Toolbar(QWidget):
    start_clicked = Signal()
    stop_clicked = Signal()
    clear_clicked = Signal()
    search_changed = Signal(str)
    process_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._btn_start = QPushButton("▶  Start")
        self._btn_start.setFixedWidth(90)
        self._btn_start.setStyleSheet(_BTN.format(bg="#27ae60", hover="#2ecc71"))
        self._btn_start.clicked.connect(self.start_clicked)

        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.setFixedWidth(90)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(_BTN.format(bg="#e74c3c", hover="#c0392b"))
        self._btn_stop.clicked.connect(self.stop_clicked)

        layout.addWidget(self._btn_start)
        layout.addWidget(self._btn_stop)
        layout.addWidget(_separator())

        # Search
        search_icon = QLabel("🔍")
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter sessions…")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            "QLineEdit { background: #2d2d2d; color: #d4d4d4; border: 1px solid #3e3e3e; "
            "padding: 4px 8px; border-radius: 3px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #007acc; }"
        )
        self._search.textChanged.connect(self.search_changed)

        layout.addWidget(search_icon)
        layout.addWidget(self._search, stretch=1)
        layout.addWidget(_separator())

        # Process filter
        process_label = QLabel("Process:")
        process_label.setStyleSheet("color: #888; font-size: 11px;")
        self._process_combo = QComboBox()
        self._process_combo.addItems(["All Processes", "chrome.exe", "firefox.exe", "python.exe", "node.exe"])
        self._process_combo.setFixedWidth(150)
        self._process_combo.setStyleSheet(
            "QComboBox { background: #2d2d2d; color: #d4d4d4; border: 1px solid #3e3e3e; "
            "padding: 4px 8px; border-radius: 3px; font-size: 12px; }"
            "QComboBox::drop-down { border: none; width: 20px; }"
            "QComboBox QAbstractItemView { background: #2d2d2d; color: #d4d4d4; "
            "selection-background-color: #264f78; border: 1px solid #3e3e3e; }"
        )
        self._process_combo.currentTextChanged.connect(self.process_changed)

        layout.addWidget(process_label)
        layout.addWidget(self._process_combo)
        layout.addWidget(_separator())

        # Decode
        decode_label = QLabel("Decode:")
        decode_label.setStyleSheet("color: #888; font-size: 11px;")
        self._decode_combo = QComboBox()
        self._decode_combo.addItems(["Auto", "UTF-8", "Base64", "Hex", "Raw"])
        self._decode_combo.setFixedWidth(90)
        self._decode_combo.setStyleSheet(self._process_combo.styleSheet())

        layout.addWidget(decode_label)
        layout.addWidget(self._decode_combo)
        layout.addWidget(_separator())

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(70)
        self._btn_clear.setStyleSheet(_BTN.format(bg="#444", hover="#555"))
        self._btn_clear.clicked.connect(self.clear_clicked)
        layout.addWidget(self._btn_clear)

    def set_capturing(self, capturing: bool):
        self._btn_start.setEnabled(not capturing)
        self._btn_stop.setEnabled(capturing)


def _separator() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFixedWidth(1)
    f.setStyleSheet("background-color: #3e3e3e;")
    return f
