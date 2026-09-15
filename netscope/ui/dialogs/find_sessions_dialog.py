from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from netscope.models.session import SessionEntry


class FindSessionsDialog(QDialog):
    session_selected = Signal(int)  # session id

    def __init__(self, sessions: list[SessionEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("세션 찾기 (Find Sessions)")
        self.setMinimumSize(720, 500)
        self._sessions = sessions
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Search bar
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("검색어를 입력하세요...")
        self._search_input.returnPressed.connect(self._do_search)
        search_row.addWidget(self._search_input)
        btn_search = QPushButton("찾기")
        btn_search.setFixedWidth(72)
        btn_search.clicked.connect(self._do_search)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        # Scope checkboxes
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("검색 범위:"))
        self._chk_url = QCheckBox("URL / Path")
        self._chk_url.setChecked(True)
        self._chk_host = QCheckBox("Host")
        self._chk_host.setChecked(True)
        self._chk_headers = QCheckBox("Headers")
        self._chk_headers.setChecked(True)
        self._chk_body = QCheckBox("Body")
        self._chk_body.setChecked(False)
        for w in (self._chk_url, self._chk_host, self._chk_headers, self._chk_body):
            scope_row.addWidget(w)
        scope_row.addStretch()
        layout.addLayout(scope_row)

        # Results table
        self._result_table = QTableWidget(0, 5)
        self._result_table.setHorizontalHeaderLabels(["#", "상태", "메서드", "호스트", "URL"])
        self._result_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self._result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._result_table.verticalHeader().setVisible(False)
        self._result_table.setShowGrid(False)
        self._result_table.setAlternatingRowColors(True)
        self._result_table.doubleClicked.connect(self._on_double_click)
        self._result_table.setColumnWidth(0, 42)
        self._result_table.setColumnWidth(1, 52)
        self._result_table.setColumnWidth(2, 62)
        self._result_table.setColumnWidth(3, 200)
        self._result_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                font-size: 12px;
                border: 1px solid #cccccc;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px 6px;
                border: none;
                border-right: 1px solid #dddddd;
                border-bottom: 1px solid #dddddd;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self._result_table)

        self._status_label = QLabel("세션을 선택하고 찾기를 눌러주세요. 더블클릭으로 세션으로 이동합니다.")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _do_search(self):
        query = self._search_input.text().lower().strip()
        if not query:
            return

        results = []
        for s in self._sessions:
            haystack = ""
            if self._chk_url.isChecked():
                haystack += s.url + " " + s.path + " "
            if self._chk_host.isChecked():
                haystack += s.host + " "
            if self._chk_headers.isChecked():
                haystack += " ".join(
                    f"{k}: {v}" for k, v in s.request_headers.items()
                ) + " "
                haystack += " ".join(
                    f"{k}: {v}" for k, v in s.response_headers.items()
                ) + " "
            if self._chk_body.isChecked():
                haystack += s.request_body.decode("utf-8", errors="replace") + " "
                haystack += s.response_body.decode("utf-8", errors="replace") + " "
            if query in haystack.lower():
                results.append(s)

        self._result_table.setRowCount(0)
        for s in results:
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            cells = [str(s.id), str(s.status_code or "…"), s.method, s.host, s.path]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, s.id)
                self._result_table.setItem(row, col, item)

        count = len(results)
        if count:
            self._status_label.setText(
                f"{count}개 세션이 검색되었습니다. 더블클릭으로 세션으로 이동합니다."
            )
        else:
            self._status_label.setText("검색 결과가 없습니다.")

    def _on_double_click(self, index):
        item = self._result_table.item(index.row(), 0)
        if item:
            session_id = item.data(Qt.ItemDataRole.UserRole)
            self.session_selected.emit(session_id)
