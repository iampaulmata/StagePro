from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication
from stagepro.ui_main import StageProWindow

def main():
    base_dir = Path(__file__).resolve().parent
    app = QApplication(sys.argv)
    w = StageProWindow(base_dir)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
