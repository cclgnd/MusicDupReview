import sys
from pathlib import Path

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from playback_service import PlaybackService
from pyside_app.settings import initial_database_path, load_app_settings, save_app_settings
from pyside_app.views.duplicate_removal import DuplicateRemovalView
from pyside_app.views.file_explorer import FileExplorerView
from pyside_app.views.settings_view import SettingsView
from pyside_app.views.utilities import UtilitiesView


class MainWindow(QMainWindow):
    def __init__(self, db_path=None):
        super().__init__()
        self.settings = load_app_settings()
        self.db_path = db_path or initial_database_path()
        self.playback = PlaybackService()
        self.playing_path = None
        self.setWindowTitle("Music Duplicate Review - PySide6")
        self.resize(1180, 760)

        self.nav = QListWidget()
        self.stack = QStackedWidget()
        self.views = [
            ("Duplicate Removal", DuplicateRemovalView(self.current_db_path)),
            ("File Explorer", FileExplorerView(self.current_db_path)),
            ("Utilities", UtilitiesView(self.current_db_path, self.refresh_data_views)),
            ("Settings", SettingsView(self.current_db_path, self.set_database)),
        ]
        for label, widget in self.views:
            self.nav.addItem(QListWidgetItem(label))
            self.stack.addWidget(widget)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(self.nav, 0)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Open Database", self.open_database)
        file_menu.addAction("Refresh Current View", self.refresh_current_view)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        self.statusBar().showMessage(self.db_path)
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_label = QLabel("No audio")
        self.statusBar().addPermanentWidget(self.play_label, 1)
        self.statusBar().addPermanentWidget(self.play_button)
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_playback)
        self.refresh_current_view()

    def current_db_path(self):
        return self.db_path

    def open_database(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open duplicate database", self.db_path, "SQLite database (*.db *.sqlite);;All files (*.*)"
        )
        if path:
            self.set_database(path)

    def set_database(self, path):
        self.db_path = path
        self.settings = load_app_settings()
        self.settings["db_path"] = path
        save_app_settings(self.settings)
        self.statusBar().showMessage(self.db_path)
        self.refresh_data_views()

    def refresh_current_view(self):
        widget = self.stack.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def refresh_data_views(self):
        for index in range(self.stack.count()):
            widget = self.stack.widget(index)
            if hasattr(widget, "refresh"):
                widget.refresh()

    def toggle_playback(self):
        if self.playing_path:
            self.stop_playback()
            return
        widget = self.stack.currentWidget()
        path = widget.selected_playback_path() if hasattr(widget, "selected_playback_path") else None
        if not path:
            self.play_label.setText("Select an existing playable file")
            return
        if not self.playback.available:
            QMessageBox.warning(self, "Playback", "pygame playback backend is unavailable.")
            return
        try:
            self.playback.play(path)
            self.playing_path = path
            self.play_label.setText(Path(path).name)
            self.play_button.setText("Stop")
        except Exception as exc:
            QMessageBox.critical(self, "Playback", str(exc))
            self.stop_playback()

    def stop_playback(self):
        try:
            self.playback.stop()
        except Exception:
            pass
        self.playing_path = None
        self.play_label.setText("No audio")
        self.play_button.setText("Play")

    def closeEvent(self, event):
        self.stop_playback()
        super().closeEvent(event)


def default_db_arg():
    return initial_database_path(sys.argv[1] if len(sys.argv) > 1 else None)
