from PySide6.QtCore import Qt, Signal, QSortFilterProxyModel
from PySide6.QtWidgets import QHeaderView, QTableView

from netscope.models.session_table_model import SessionTableModel


class SessionFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""
        self._process_filter = ""
        self._rules = None  # RulesEngine reference (optional)

    def set_rules(self, rules):
        self._rules = rules
        self._rules.rules_changed.connect(self.invalidateFilter)

    def set_filter_text(self, text: str):
        self._filter_text = text.lower()
        self.invalidateFilter()

    def set_process_filter(self, text: str):
        self._process_filter = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        session = model.get_session(source_row)
        if session is None:
            return False

        # ── Rules-based filters ───────────────────────────────────────────
        if self._rules:
            if self._rules.hide_image_requests:
                ct = (session.content_type or "").lower()
                if ct.startswith("image/"):
                    return False

            if self._rules.hide_connects and session.method == "CONNECT":
                return False

            if self._rules.hide_304s and session.status_code == 304:
                return False

        # ── Text filter ───────────────────────────────────────────────────
        if self._filter_text:
            searchable = (
                f"{session.scheme} {session.host} {session.path} {session.status_code}"
            ).lower()
            if self._filter_text not in searchable:
                return False

        return True


class SessionTableView(QTableView):
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
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.setColumnWidth(0, 45)
        self.setColumnWidth(1, 55)
        self.setColumnWidth(2, 65)
        self.setColumnWidth(3, 180)

        self.setStyleSheet("""
            QTableView {
                background-color: #ffffff;
                color: #1e1e1e;
                gridline-color: #e0e0e0;
                font-size: 12px;
                border: none;
            }
            QTableView::item {
                padding: 3px 6px;
            }
            QTableView::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTableView::item:alternate {
                background-color: #f5f5f5;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #555555;
                padding: 5px 6px;
                border: none;
                border-right: 1px solid #dddddd;
                border-bottom: 1px solid #dddddd;
                font-size: 11px;
                font-weight: bold;
            }
        """)

        self.selectionModel().currentRowChanged.connect(self._on_row_changed)

    def set_rules(self, rules):
        self._proxy.set_rules(rules)

    def set_filter(self, text: str):
        self._proxy.set_filter_text(text)

    def _on_row_changed(self, current, _previous):
        if current.isValid():
            source_index = self._proxy.mapToSource(current)
            self.session_selected.emit(source_index.row())

    def scroll_to_bottom(self):
        self.scrollToBottom()
