from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class WelcomePanel(QWidget):
    """Shown on the right side when no session is selected."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🔭")
        icon.setFont(QFont("Segoe UI Emoji", 48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("NetScope")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #007acc;")

        subtitle = QLabel("네트워크 트래픽 인스펙터")
        subtitle.setFont(QFont("Segoe UI", 13))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666666;")

        hint = QLabel(
            "▶ 시작  버튼을 눌러 트래픽 캡처를 시작하세요.\n"
            "목록에서 세션을 선택하면 상세 내용을 확인할 수 있습니다."
        )
        hint.setFont(QFont("Segoe UI", 11))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #444444; margin-top: 24px; line-height: 1.8;")

        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(hint)
        layout.addStretch()
