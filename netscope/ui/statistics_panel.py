from __future__ import annotations

import collections

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)
from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView,
    QHorizontalBarSeries, QLineSeries, QPieSeries, QValueAxis,
)

from netscope.models.session import SessionEntry, SessionState


class StatisticsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    # ── UI construction ────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("트래픽 통계")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e1e1e;")
        layout.addWidget(title)

        # ── Summary card ───────────────────────────────────────────────────
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; }"
        )
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)

        def _row(label_text: str):
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

        # ── 2×2 chart grid ─────────────────────────────────────────────────
        charts_grid = QGridLayout()
        charts_grid.setSpacing(16)
        charts_grid.setColumnStretch(0, 1)
        charts_grid.setColumnStretch(1, 1)

        self._pie_view   = self._make_chart_view(280)
        self._rt_view    = self._make_chart_view(280)
        self._trend_view = self._make_chart_view(260)
        self._host_view  = self._make_chart_view(320)

        charts_grid.addWidget(
            self._card("상태코드 분포", self._pie_view), 0, 0)
        charts_grid.addWidget(
            self._card("응답 시간 히스토그램", self._rt_view), 0, 1)
        charts_grid.addWidget(
            self._card("트래픽 크기 추이", self._trend_view), 1, 0)
        charts_grid.addWidget(
            self._card("호스트별 요청 수 순위", self._host_view), 1, 1)

        layout.addLayout(charts_grid)
        layout.addStretch()

    def _make_chart_view(self, min_height: int = 260) -> QChartView:
        view = QChartView()
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(min_height)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        chart = QChart()
        chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        chart.setBackgroundBrush(QColor("#ffffff"))
        chart.setDropShadowEnabled(False)
        chart.setMargins(chart.margins().__class__(8, 8, 8, 8))
        view.setChart(chart)
        return view

    def _card(self, title_text: str, chart_view: QChartView) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e0e0e0; border-radius: 6px; }"
        )
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(14, 12, 14, 14)
        vbox.setSpacing(4)
        lbl = QLabel(title_text)
        lbl.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #333333; border: none;"
        )
        vbox.addWidget(lbl)
        vbox.addWidget(chart_view)
        return card

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_chart(chart: QChart, message: str = "데이터 없음") -> None:
        """Clear chart and show a placeholder message via title."""
        chart.removeAllSeries()
        for ax in chart.axes():
            chart.removeAxis(ax)
        chart.setTitle(f"<span style='color:#aaaaaa;font-size:12px'>{message}</span>")
        chart.legend().setVisible(False)

    @staticmethod
    def _axis_font() -> QFont:
        f = QFont()
        f.setPointSize(9)
        return f

    # ── Public API ─────────────────────────────────────────────────────────

    def update_stats(self, sessions: list[SessionEntry]):
        self._update_summary(sessions)
        self._update_pie(sessions)
        self._update_rt_histogram(sessions)
        self._update_trend(sessions)
        self._update_host_ranking(sessions)

    # ── Summary numbers ────────────────────────────────────────────────────

    def _update_summary(self, sessions: list[SessionEntry]):
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

    # ── Chart 1: Status-code pie (donut) ───────────────────────────────────

    def _update_pie(self, sessions: list[SessionEntry]):
        chart = self._pie_view.chart()
        chart.removeAllSeries()
        for ax in chart.axes():
            chart.removeAxis(ax)
        chart.setTitle("")

        buckets = [
            ("2xx 성공",        QColor("#4caf50"), lambda s: 200 <= s.status_code < 300),
            ("3xx 리다이렉트",  QColor("#2196f3"), lambda s: 300 <= s.status_code < 400),
            ("4xx 클라이언트",  QColor("#ff9800"), lambda s: 400 <= s.status_code < 500),
            ("5xx 서버",        QColor("#f44336"), lambda s: 500 <= s.status_code < 600),
            ("기타",            QColor("#9e9e9e"), lambda s: not (200 <= s.status_code < 600)),
        ]

        series = QPieSeries()
        series.setHoleSize(0.38)
        series.setPieSize(0.72)
        has_data = False
        for label, color, pred in buckets:
            count = sum(1 for s in sessions if pred(s))
            if count == 0:
                continue
            has_data = True
            slc = series.append(f"{label}  {count}", count)
            slc.setBrush(color)
            slc.setBorderColor(QColor("#ffffff"))
            slc.setLabelVisible(True)
            slc.setLabelColor(QColor("#444444"))
            lf = slc.labelFont()
            lf.setPointSize(9)
            slc.setLabelFont(lf)

        if not has_data:
            self._empty_chart(chart)
            return

        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.legend().setVisible(True)
        lf = chart.legend().font()
        lf.setPointSize(9)
        chart.legend().setFont(lf)

    # ── Chart 2: Response-time histogram ───────────────────────────────────

    def _update_rt_histogram(self, sessions: list[SessionEntry]):
        chart = self._rt_view.chart()
        chart.removeAllSeries()
        for ax in chart.axes():
            chart.removeAxis(ax)
        chart.setTitle("")

        times = [s.elapsed_ms for s in sessions if s.elapsed_ms > 0]
        if not times:
            self._empty_chart(chart)
            return

        buckets = [
            ("0–50ms",    0,    50),
            ("50–200ms",  50,   200),
            ("200–500ms", 200,  500),
            ("0.5–1s",    500,  1000),
            ("1–3s",      1000, 3000),
            ("3s+",       3000, float("inf")),
        ]

        bar_set = QBarSet("요청 수")
        bar_set.setColor(QColor("#2196f3"))
        bar_set.setBorderColor(QColor("#1565c0"))
        categories: list[str] = []
        for label, lo, hi in buckets:
            count = sum(1 for t in times if lo <= t < hi)
            bar_set.append(count)
            categories.append(label)

        series = QBarSeries()
        series.append(bar_set)
        series.setBarWidth(0.65)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsFont(self._axis_font())
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        max_count = max(bar_set.at(i) for i in range(bar_set.count()))
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        axis_y.setTitleText("요청 수")
        axis_y.setTitleFont(self._axis_font())
        axis_y.setLabelsFont(self._axis_font())
        axis_y.setRange(0, max(1, max_count + 1))
        axis_y.setTickCount(min(6, max_count + 2))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)

    # ── Chart 3: Traffic-size trend (line chart) ───────────────────────────

    def _update_trend(self, sessions: list[SessionEntry]):
        chart = self._trend_view.chart()
        chart.removeAllSeries()
        for ax in chart.axes():
            chart.removeAxis(ax)
        chart.setTitle("")

        completed = [s for s in sessions if s.state == SessionState.COMPLETE]
        if not completed:
            self._empty_chart(chart)
            return

        # Per-session size (KB)
        series = QLineSeries()
        pen = series.pen()
        pen.setColor(QColor("#4caf50"))
        pen.setWidth(2)
        series.setPen(pen)
        series.setName("응답 크기")

        max_kb = 0.0
        for i, s in enumerate(completed):
            kb = s.body_size / 1024
            series.append(float(i + 1), kb)
            if kb > max_kb:
                max_kb = kb

        chart.addSeries(series)

        axis_x = QValueAxis()
        axis_x.setLabelFormat("%d")
        axis_x.setTitleText("세션 순서")
        axis_x.setTitleFont(self._axis_font())
        axis_x.setLabelsFont(self._axis_font())
        axis_x.setRange(1, len(completed))
        axis_x.setTickCount(min(6, len(completed) + 1))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.1f")
        axis_y.setTitleText("크기 (KB)")
        axis_y.setTitleFont(self._axis_font())
        axis_y.setLabelsFont(self._axis_font())
        axis_y.setRange(0, max(1.0, max_kb * 1.1))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)

    # ── Chart 4: Top-hosts horizontal bar chart ────────────────────────────

    def _update_host_ranking(self, sessions: list[SessionEntry]):
        chart = self._host_view.chart()
        chart.removeAllSeries()
        for ax in chart.axes():
            chart.removeAxis(ax)
        chart.setTitle("")

        counter = collections.Counter(s.host for s in sessions if s.host)
        top = counter.most_common(8)

        if not top:
            self._empty_chart(chart)
            return

        # Reverse so highest count is at the top visually
        top_rev = list(reversed(top))
        hosts  = [h for h, _ in top_rev]
        counts = [c for _, c in top_rev]

        # Truncate long hostnames for display
        display_hosts = [h if len(h) <= 30 else h[:27] + "…" for h in hosts]

        bar_set = QBarSet("요청 수")
        bar_set.setColor(QColor("#9c27b0"))
        bar_set.setBorderColor(QColor("#6a0080"))
        for c in counts:
            bar_set.append(c)

        series = QHorizontalBarSeries()
        series.append(bar_set)
        series.setBarWidth(0.6)
        chart.addSeries(series)

        axis_y = QBarCategoryAxis()
        axis_y.append(display_hosts)
        axis_y.setLabelsFont(self._axis_font())
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        max_count = max(counts)
        axis_x = QValueAxis()
        axis_x.setLabelFormat("%d")
        axis_x.setTitleText("요청 수")
        axis_x.setTitleFont(self._axis_font())
        axis_x.setLabelsFont(self._axis_font())
        axis_x.setRange(0, max(1, max_count + 1))
        axis_x.setTickCount(min(6, max_count + 2))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        chart.legend().setVisible(False)
