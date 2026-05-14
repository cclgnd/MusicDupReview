import sys
from ctypes import windll
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pyside_app.theme import apply_theme
from pyside_app.window import MainWindow, default_db_arg

APP_USER_MODEL_ID = "MusicDupReview.Desktop.App"


def set_windows_app_id():
    if sys.platform != "win32":
        return
    try:
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def main():
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Music Duplicate Review")
    app.setOrganizationName("MusicDupReview")
    app.setDesktopFileName(APP_USER_MODEL_ID)
    icon_path = Path(__file__).resolve().parents[1] / "MusicDupReview_round.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app)
    window = MainWindow(default_db_arg())
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
