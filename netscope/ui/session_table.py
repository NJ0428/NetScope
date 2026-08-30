from PySide6.QtCore import Qt, Signal, QSortFilterProxyModel
from PySide6.QtWidgets import QHeaderView, QTableView

from netscope.models.session_table_model import SessionTableModel


class SessionFilterProxy(QSortFilterProxyModel):
    """Filters sessions by search text across host, path, and method."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""

    def set_filter_text(self, text: str):
        self._filter_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._filter_text:
            return True
        model = self.sourceModel()
        session = model.get_session(source_row)
        if session is None:
            return False
        searchable = f"{session.method} {session.host} {session.path} {session.status_code}".lower()
        return self._filter_text in searchable


class SessionTableView(QTableView):
    """Table view for captured sessions."""

    session_selected = Signal(int)  # row in source model

    def __init__(self, model: SessionTableModel, parent=None):
        super().__init__(parent)
        self._source_model = model

        self._proxy = SessionFilterProxy(self)
        self._proxy.setSourceModel(model)
        self.setModel(self._proxy)

        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setSortingEnabled(True)

        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 50)   # #
        self.setColumnWidth(1, 70)   # Method
        self.setColumnWidth(2, 60)   # Status
        self.setColumnWidth(3, 180)  # Host
        self.setColumnWidth(5, 160)  # Content-Type
        self.setColumnWidth(6, 80)   # Size
        self.setColumnWidth(7, 80)   # Time

        self.setStyleSheet("""
            QTableView {
                background-color: #1e1e1e;
                color: #d4d4d4;
                gridline-color: #333;
                font-size: 12px;
            }
            QTableView::item:selected {
                background-color: #264f78;
            }
            QTableView::item:alternate {
                background-color: #252526;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 4px;
                border: 1px solid #3e3e3e;
                font-weight: bold;
            }
        """)

        self.selectionModel().currentRowChanged.connect(self._on_row_changed)

    def set_filter(self, text: str):
        self._proxy.set_filter_text(text)

    def _on_row_changed(self, current, _previous):
        if current.isValid():
            source_index = self._proxy.mapToSource(current)
            self.session_selected.emit(source_index.row())

    def scroll_to_bottom(self):
        self.scrollToBottom()
