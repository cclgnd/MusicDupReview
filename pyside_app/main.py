import sys

from PySide6.QtWidgets import QApplication

from pyside_app.theme import apply_theme
from pyside_app.window import MainWindow, default_db_arg


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow(default_db_arg())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
