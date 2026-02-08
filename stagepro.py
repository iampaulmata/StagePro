import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from stagepro.ui_main import StageProWindow
from stagepro.config import APP_NAME  # APP_NAME = "stagepro"

def main():
    # Human-facing identity
    QCoreApplication.setOrganizationName("StagePro")
    QCoreApplication.setApplicationName("StagePro")

    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    app = QApplication(sys.argv)

    base_dir = Path(__file__).resolve().parent
    window = StageProWindow(base_dir)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
