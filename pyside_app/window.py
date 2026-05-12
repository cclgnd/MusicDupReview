import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
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
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from playback_service import PlaybackService
from pyside_app.settings import initial_database_path, load_app_settings, save_app_settings
from pyside_app.theme import ACCENT_AMBER, BG_DEEP, FG_HINT, FG_TEXT
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
        self.playback_duration = 0.0
        self.playback_seek_offset = 0.0
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

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.nav, 0)
        content_layout.addWidget(self.stack, 1)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(content, 1)
        layout.addWidget(self.create_player_bar())
        self.setCentralWidget(root)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Open Database", self.open_database)
        file_menu.addAction("Refresh Current View", self.refresh_current_view)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        self.statusBar().showMessage(self.db_path)
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(250)
        self.playback_timer.timeout.connect(self.update_playback_progress)
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

    def create_player_bar(self):
        bar = QWidget()
        bar.setObjectName("PlayerBar")
        bar.setStyleSheet(f"""
            QWidget#PlayerBar {{
                background: {BG_DEEP};
                border-top: 1px solid #1e1e28;
            }}
            QLabel#PlayerTitle {{
                color: {FG_TEXT};
                font-weight: bold;
            }}
            QLabel#PlayerMeta {{
                color: {FG_HINT};
                font-family: Consolas;
            }}
            QPushButton#PlayerButton {{
                color: {FG_TEXT};
                font-weight: bold;
                min-width: 72px;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 7, 12, 7)
        self.play_file_label = QLabel("No audio")
        self.play_file_label.setObjectName("PlayerTitle")
        self.play_file_label.setMinimumWidth(170)
        self.play_info_label = QLabel("00:00 / 00:00")
        self.play_info_label.setObjectName("PlayerMeta")
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("PlayerButton")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_slider = QSlider(Qt.Horizontal)
        self.play_slider.setRange(0, 1000)
        self.play_slider.setValue(0)
        self.play_slider.sliderReleased.connect(self.seek_playback_from_slider)
        layout.addWidget(self.play_file_label)
        layout.addWidget(self.play_button)
        layout.addWidget(self.play_info_label)
        layout.addWidget(self.play_slider, 1)
        return bar

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
            self.playback_duration = self.playback.duration(path)
            self.playback.play(path)
            self.playing_path = path
            self.playback_seek_offset = 0.0
            self.play_file_label.setText(Path(path).name)
            self.play_button.setText("Stop")
            self.play_button.setStyleSheet(f"color: {ACCENT_AMBER};")
            self.playback_timer.start()
            self.update_playback_progress()
        except Exception as exc:
            QMessageBox.critical(self, "Playback", str(exc))
            self.stop_playback()

    def update_playback_progress(self):
        if not self.playing_path:
            return
        position = max(0.0, self.playback.position_seconds())
        elapsed = self.playback_seek_offset + position
        if self.playback_duration > 0:
            elapsed = min(elapsed, self.playback_duration)
            self.play_slider.setValue(int((elapsed / self.playback_duration) * 1000))
        self.play_info_label.setText(f"{self.format_time(elapsed)} / {self.format_time(self.playback_duration)}")
        if self.playback.available and not self.playback.is_busy() and elapsed > 0:
            self.stop_playback()

    def seek_playback_from_slider(self):
        if not self.playing_path or self.playback_duration <= 0:
            return
        seconds = (self.play_slider.value() / 1000) * self.playback_duration
        self.playback.seek(seconds)
        self.playback_seek_offset = seconds
        self.update_playback_progress()

    def format_time(self, seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def stop_playback(self):
        try:
            self.playback.release()
        except Exception:
            pass
        self.playback_timer.stop()
        self.playing_path = None
        self.playback_duration = 0.0
        self.playback_seek_offset = 0.0
        self.play_file_label.setText("No audio")
        self.play_info_label.setText("00:00 / 00:00")
        self.play_slider.setValue(0)
        self.play_button.setText("Play")
        self.play_button.setStyleSheet("")

    def closeEvent(self, event):
        self.stop_playback()
        super().closeEvent(event)


def default_db_arg():
    return initial_database_path(sys.argv[1] if len(sys.argv) > 1 else None)
