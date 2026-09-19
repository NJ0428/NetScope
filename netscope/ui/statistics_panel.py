from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout,
)

from netscope.models.session import SessionEntry, SessionState


class StatisticsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("트래픽 통계")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e1e1e;")
        layout.addWidget(title)

        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; }"
        )
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)

        def _row(label_text: str) -> QLabel:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #555555; font-size: 13px;")
            val = QLabel("—")
            val.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e1e1e;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return lbl, val

        rows = [
            ("total",      "전체 세션"),
            ("complete",   "완료"),
            ("error",      "오류"),
            ("pending",    "대기"),
            None,
            ("2xx",        "2xx  성공"),
            ("3xx",        "3xx  리다이렉트"),
            ("4xx",        "4xx  클라이언트 오류"),
            ("5xx",        "5xx  서버 오류"),
            None,
            ("avg_time",   "평균 응답 시간"),
            ("total_size", "전체 응답 크기"),
        ]

        self._vals: dict[str, QLabel] = {}
        row_idx = 0
        for item in rows:
            if item is None:
                spacer = QFrame()
                spacer.setFixedHeight(6)
                grid.addWidget(spacer, row_idx, 0, 1, 2)
            else:
                key, text = item
                lbl, val = _row(text)
                grid.addWidget(lbl, row_idx, 0)
                grid.addWidget(val, row_idx, 1)
                self._vals[key] = val
            row_idx += 1

        layout.addWidget(card)
        layout.addStretch()

    def update_stats(self, sessions: list[SessionEntry]):
        total    = len(sessions)
        complete = sum(1 for s in sessions if s.state == SessionState.COMPLETE)
        error    = sum(1 for s in sessions if s.state == SessionState.ERROR)
        pending  = sum(1 for s in sessions if s.state == SessionState.PENDING)

        s2xx = sum(1 for s in sessions if 200 <= s.status_code < 300)
        s3xx = sum(1 for s in sessions if 300 <= s.status_code < 400)
        s4xx = sum(1 for s in sessions if 400 <= s.status_code < 500)
        s5xx = sum(1 for s in sessions if 500 <= s.status_code < 600)

        times = [s.elapsed_ms for s in sessions if s.elapsed_ms > 0]
        avg_ms = sum(times) / len(times) if times else 0.0

        total_bytes = sum(s.body_size for s in sessions)
        if total_bytes < 1024:
            size_str = f"{total_bytes} B"
        elif total_bytes < 1024 * 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes / (1024 * 1024):.1f} MB"

        self._vals["total"].setText(str(total))
        self._vals["complete"].setText(str(complete))
        self._vals["error"].setText(str(error))
        self._vals["pending"].setText(str(pending))
        self._vals["2xx"].setText(str(s2xx))
        self._vals["3xx"].setText(str(s3xx))
        self._vals["4xx"].setText(str(s4xx))
        self._vals["5xx"].setText(str(s5xx))
        self._vals["avg_time"].setText(f"{avg_ms:.1f} ms")
        self._vals["total_size"].setText(size_str)
