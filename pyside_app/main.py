import sys

from PySide6.QtWidgets import QApplication

from pyside_app.window import MainWindow, default_db_arg


def main():
    app = QApplication(sys.argv)
    window = MainWindow(default_db_arg())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
