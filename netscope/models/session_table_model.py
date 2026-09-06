from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex

from netscope.models.session import SessionEntry, SessionState

COLUMNS = ["#", "상태", "프로토콜", "호스트", "URL"]


class SessionTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions: list[SessionEntry] = []
        self._next_id = 1

    def rowCount(self, parent=QModelIndex()):
        return len(self._sessions)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._sessions):
            return None

        session = self._sessions[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            match col:
                case 0: return session.id
                case 1: return session.status_code if session.status_code else "…"
                case 2: return session.scheme.upper()
                case 3: return session.host
                case 4: return session.path

        if role == Qt.ItemDataRole.ForegroundRole:
            from PySide6.QtGui import QColor
            if session.state == SessionState.ERROR or (col == 1 and session.status_code >= 500):
                return QColor("#e74c3c")
            if col == 1 and session.status_code >= 400:
                return QColor("#f39c12")
            if col == 1 and session.status_code >= 300:
                return QColor("#3498db")
            if col == 1 and session.status_code >= 200:
                return QColor("#2ecc71")
            if col == 2 and session.scheme == "https":
                return QColor("#2ecc71")
            if col == 2 and session.scheme == "http":
                return QColor("#f39c12")

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1):
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return None

    def add_session(self, session: SessionEntry) -> int:
        session.id = self._next_id
        self._next_id += 1
        row = len(self._sessions)
        self.beginInsertRows(QModelIndex(), row, row)
        self._sessions.append(session)
        self.endInsertRows()
        return session.id

    def update_session(self, session_id: int, **kwargs):
        for row, s in enumerate(self._sessions):
            if s.id == session_id:
                for k, v in kwargs.items():
                    setattr(s, k, v)
                self.dataChanged.emit(
                    self.index(row, 0),
                    self.index(row, self.columnCount() - 1),
                )
                return

    def get_session(self, row: int) -> SessionEntry | None:
        if 0 <= row < len(self._sessions):
            return self._sessions[row]
        return None

    def clear(self):
        self.beginResetModel()
        self._sessions.clear()
        self._next_id = 1
        self.endResetModel()
