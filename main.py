import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from netscope.ui.main_window import MainWindow

_ICONS_DIR = Path(__file__).parent / "netscope" / "resources" / "icons"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NetScope")
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(_ICONS_DIR / "NetScope.ico")))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
