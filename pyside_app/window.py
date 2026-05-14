import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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


class PlayerWidthHandle(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.start_x = 0
        self.start_width = 0
        self.setObjectName("PlayerWidthHandle")
        self.setCursor(Qt.SizeHorCursor)
        self.setFixedWidth(7)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_x = event.globalPosition().x()
            self.start_width = self.window.player_cluster_width
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.LeftButton:
            return
        delta = int(event.globalPosition().x() - self.start_x)
        self.window.set_player_cluster_width(self.start_width + (delta * 2))


class MainWindow(QMainWindow):
    def __init__(self, db_path=None):
        super().__init__()
        self.settings = load_app_settings()
        self.db_path = db_path or initial_database_path()
        self.playback = PlaybackService()
        self.loaded_path = None
        self.playing_path = None
        self.paused_path = None
        self.playback_duration = 0.0
        self.playback_seek_offset = 0.0
        self.paused_elapsed = 0.0
        self.player_cluster_width = int(self.settings.get("player_cluster_width") or 980)
        self.setWindowTitle("Music Duplicate Review - PySide6")
        self.setMinimumSize(720, 420)
        width = int(self.settings.get("window_width") or 1500)
        height = int(self.settings.get("window_height") or 900)
        self.resize(max(720, width), max(420, height))

        self.stack = QStackedWidget()
        self.duplicate_view = DuplicateRemovalView(self.current_db_path)
        self.file_explorer_view = FileExplorerView(self.current_db_path)
        self.utilities_view = UtilitiesView(self.current_db_path, self.refresh_data_views, self.set_database)
        self.settings_view = SettingsView(self.current_db_path, self.set_database)
        self.duplicate_view.new_search_requested.connect(self.open_new_search)
        self.duplicate_view.release_playback_requested.connect(self.release_playback_for_path)
        self.duplicate_view.loading_finished.connect(self.hide_loading_message)
        self.views = [
            ("Duplicate Removal", self.duplicate_view),
            ("File Explorer", self.file_explorer_view),
            ("Utilities", self.utilities_view),
            ("Settings", self.settings_view),
        ]
        for label, widget in self.views:
            self.stack.addWidget(widget)
        self.stack.setCurrentIndex(0)

        self.root = QWidget()
        self.root.installEventFilter(self)
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.create_player_bar())
        self.setCentralWidget(self.root)
        self.loading_overlay = self.create_loading_overlay()
        self.show_loading_message()

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Open Database", self.open_database)
        file_menu.addAction("Refresh Current View", self.refresh_current_view)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        view_menu = self.menuBar().addMenu("View")
        for index, (label, _widget) in enumerate(self.views):
            view_menu.addAction(label, lambda _checked=False, row=index: self.stack.setCurrentIndex(row))

        self.statusBar().showMessage(self.db_path)
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(250)
        self.playback_timer.timeout.connect(self.update_playback_progress)
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_playback)
        if self.settings.get("window_maximized"):
            self.showMaximized()
        self.refresh_current_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_responsive_layout()

    def current_db_path(self):
        return self.db_path

    def create_loading_overlay(self):
        overlay = QFrame(self.root)
        overlay.setObjectName("StartupLoadingOverlay")
        overlay.setStyleSheet(f"""
            QFrame#StartupLoadingOverlay {{
                background: rgba(10, 10, 16, 220);
            }}
            QFrame#StartupLoadingCard {{
                background: #171722;
                border: 1px solid #343448;
                border-radius: 8px;
            }}
            QLabel#StartupLoadingTitle {{
                color: {FG_TEXT};
                font-size: 18pt;
                font-weight: 800;
            }}
            QLabel#StartupLoadingDb {{
                color: {ACCENT_AMBER};
                font-size: 11pt;
                font-weight: 700;
            }}
        """)
        layout = QVBoxLayout(overlay)
        layout.setAlignment(Qt.AlignCenter)
        card = QFrame()
        card.setObjectName("StartupLoadingCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 22, 28, 22)
        card_layout.setSpacing(8)
        self.loading_title = QLabel("Loading database...")
        self.loading_title.setObjectName("StartupLoadingTitle")
        self.loading_db = QLabel("")
        self.loading_db.setObjectName("StartupLoadingDb")
        self.loading_db.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.loading_title, 0, Qt.AlignCenter)
        card_layout.addWidget(self.loading_db, 0, Qt.AlignCenter)
        layout.addWidget(card)
        overlay.hide()
        return overlay

    def show_loading_message(self):
        self.loading_db.setText(Path(self.db_path).name or self.db_path)
        self.loading_overlay.setGeometry(self.root.rect())
        self.loading_overlay.raise_()
        self.loading_overlay.show()

    def hide_loading_message(self):
        self.loading_overlay.hide()

    def eventFilter(self, watched, event):
        if watched is self.root and event.type() == QEvent.Resize and hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.root.rect())
        return super().eventFilter(watched, event)

    def open_database(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open duplicate database", self.db_path, "SQLite database (*.db *.sqlite);;All files (*.*)"
        )
        if path:
            self.set_database(path)

    def open_new_search(self):
        self.stack.setCurrentWidget(self.utilities_view)
        self.utilities_view.scan_folder()

    def set_database(self, path):
        self.db_path = path
        self.settings = load_app_settings()
        self.settings["db_path"] = path
        save_app_settings(self.settings)
        self.statusBar().showMessage(self.db_path)
        self.show_loading_message()
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
                color: {ACCENT_AMBER};
                font-weight: bold;
                min-width: 72px;
            }}
            QWidget#PlayerCluster {{
                background: #111118;
                border: 1px solid #252530;
                border-radius: 6px;
            }}
            QFrame#PlayerWidthHandle {{
                background: #252530;
                border-radius: 2px;
                min-height: 18px;
                max-height: 18px;
            }}
            QFrame#PlayerWidthHandle:hover {{
                background: {ACCENT_AMBER};
            }}
            QWidget#ShortcutCluster {{
                background: transparent;
            }}
            QLabel#ShortcutBadge {{
                background: #111118;
                color: {FG_HINT};
                border: 1px solid #252530;
                border-radius: 6px;
                padding: 2px 6px;
                font-family: Consolas;
                font-weight: 700;
            }}
            QPushButton#KeybindButton {{
                background: #111118;
                color: {FG_HINT};
                border: 1px solid #252530;
                border-radius: 6px;
                min-width: 44px;
                max-width: 44px;
                min-height: 24px;
                max-height: 24px;
                font-weight: 900;
            }}
            QPushButton#KeybindButton:hover {{
                color: {FG_TEXT};
                border-color: {ACCENT_AMBER};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(8)
        self.player_cluster = QWidget()
        self.player_cluster.setObjectName("PlayerCluster")
        self.set_player_cluster_width(self.player_cluster_width, save=False)
        cluster_layout = QHBoxLayout(self.player_cluster)
        cluster_layout.setContentsMargins(10, 3, 10, 3)
        cluster_layout.setSpacing(8)
        self.play_file_label = QLabel("No audio")
        self.play_file_label.setObjectName("PlayerTitle")
        self.play_file_label.setMinimumWidth(70)
        self.play_file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.play_info_label = QLabel("00:00 / 00:00")
        self.play_info_label.setObjectName("PlayerMeta")
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("PlayerButton")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_slider = QSlider(Qt.Horizontal)
        self.play_slider.setRange(0, 1000)
        self.play_slider.setValue(0)
        self.play_slider.sliderReleased.connect(self.seek_playback_from_slider)
        cluster_layout.addWidget(PlayerWidthHandle(self))
        cluster_layout.addWidget(self.play_file_label)
        cluster_layout.addWidget(self.play_button)
        cluster_layout.addWidget(self.play_info_label)
        cluster_layout.addWidget(self.play_slider, 1)
        cluster_layout.addWidget(PlayerWidthHandle(self))

        shortcuts = QWidget()
        shortcuts.setObjectName("ShortcutCluster")
        shortcuts.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.shortcut_cluster = shortcuts
        shortcut_layout = QHBoxLayout(shortcuts)
        shortcut_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_layout.setSpacing(5)
        shortcut_layout.setDirection(QHBoxLayout.RightToLeft)
        self.shortcut_badges = []
        for full_text, short_text in (
            ("Ctrl+Z Undo", "Undo"),
            ("U Clear", "Clear"),
            ("I Ignore", "Ignore"),
            ("K Master", "Master"),
            ("D Recycle", "Recycle"),
            ("Esc Clear", "Clear"),
        ):
            badge = QLabel(full_text)
            badge.setObjectName("ShortcutBadge")
            badge.setProperty("full_text", full_text)
            badge.setProperty("short_text", short_text)
            shortcut_layout.addWidget(badge)
            self.shortcut_badges.append(badge)

        keybind_button = QPushButton("Keys")
        keybind_button.setObjectName("KeybindButton")
        keybind_button.setToolTip("Configure keyboard shortcuts.")
        keybind_button.clicked.connect(self.open_keybind_settings)
        self.keybind_button = keybind_button

        layout.addWidget(self.player_cluster, 1)
        layout.addWidget(shortcuts, 0, Qt.AlignRight)
        layout.addWidget(keybind_button, 0, Qt.AlignRight)
        self.update_responsive_layout()
        return bar

    def set_player_cluster_width(self, width, save=True):
        self.player_cluster_width = max(360, min(1300, int(width)))
        target_width = self.responsive_player_cluster_width()
        if hasattr(self, "player_cluster"):
            self.player_cluster.setMinimumWidth(260)
            self.player_cluster.setMaximumWidth(target_width)
        if save:
            self.settings = load_app_settings()
            self.settings["player_cluster_width"] = self.player_cluster_width
            save_app_settings(self.settings)

    def responsive_player_cluster_width(self):
        available = max(280, self.width() - 290)
        return max(260, min(self.player_cluster_width, available))

    def update_responsive_layout(self):
        compact = self.width() < 1180
        for badge in getattr(self, "shortcut_badges", []):
            badge.setText(badge.property("short_text") if compact else badge.property("full_text"))
        if hasattr(self, "shortcut_cluster"):
            self.shortcut_cluster.setVisible(True)
        if hasattr(self, "player_cluster"):
            self.player_cluster.setMaximumWidth(self.responsive_player_cluster_width())

    def open_keybind_settings(self):
        self.stack.setCurrentWidget(self.settings_view)
        self.statusBar().showMessage("Keybind settings target opened.")

    def toggle_playback(self):
        widget = self.stack.currentWidget()
        if hasattr(widget, "open_selected_image_preview") and widget.open_selected_image_preview():
            return
        path = widget.selected_playback_path() if hasattr(widget, "selected_playback_path") else None
        if not path and self.loaded_path:
            path = self.loaded_path
        if not path:
            self.play_info_label.setText("Select playable file")
            return
        if not self.playback.available:
            QMessageBox.warning(self, "Playback", "pygame playback backend is unavailable.")
            return
        if self.playing_path and self.same_path(self.playing_path, path):
            self.pause_playback()
            return
        if self.paused_path and self.same_path(self.paused_path, path):
            self.resume_playback()
            return
        if self.loaded_path and not self.same_path(self.loaded_path, path):
            self.stop_loaded_playback(clear_ui=True)
        elif self.playing_path:
            self.stop_loaded_playback(clear_ui=True)
        try:
            self.playback.play(path)
            self.playback_duration = 0.0
            self.loaded_path = path
            self.playing_path = path
            self.paused_path = None
            self.playback_seek_offset = 0.0
            self.paused_elapsed = 0.0
            self.play_file_label.setText(Path(path).name)
            self.play_info_label.setText("00:00 / --:--")
            self.play_button.setText("Pause")
            self.play_button.setStyleSheet(f"color: {ACCENT_AMBER};")
            self.play_info_label.setStyleSheet(f"color: {ACCENT_AMBER};")
            self.playback_timer.start()
            QTimer.singleShot(0, lambda expected=path: self.load_playback_duration(expected))
            self.update_playback_progress()
        except Exception as exc:
            QMessageBox.critical(self, "Playback", str(exc))
            self.unload_playback()

    def update_playback_progress(self):
        if not self.playing_path:
            return
        position = max(0.0, self.playback.position_seconds())
        elapsed = self.playback_seek_offset + position
        if self.playback_duration > 0:
            elapsed = min(elapsed, self.playback_duration)
            self.play_slider.setValue(int((elapsed / self.playback_duration) * 1000))
            total = self.format_time(self.playback_duration)
        else:
            total = "--:--"
        self.play_info_label.setText(f"{self.format_time(elapsed)} / {total}")
        if self.playback.available and not self.playback.is_busy() and elapsed > 0:
            self.finish_playback(elapsed)

    def seek_playback_from_slider(self):
        if not self.loaded_path or self.playback_duration <= 0:
            return
        seconds = (self.play_slider.value() / 1000) * self.playback_duration
        if self.paused_path:
            self.paused_elapsed = seconds
            self.playback.seek(seconds)
            self.playback.pause()
            self.play_info_label.setText(f"{self.format_time(seconds)} / {self.format_time(self.playback_duration)}")
            return
        self.playback.seek(seconds)
        self.playing_path = self.loaded_path
        self.paused_path = None
        self.playback_seek_offset = seconds
        self.update_playback_progress()

    def format_time(self, seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def current_elapsed(self):
        if self.paused_path:
            return self.paused_elapsed
        if not self.playing_path:
            return 0.0
        position = max(0.0, self.playback.position_seconds())
        return self.playback_seek_offset + position

    def load_playback_duration(self, expected_path):
        if not self.loaded_path or not self.same_path(self.loaded_path, expected_path):
            return
        duration = self.playback.duration(expected_path)
        if not self.loaded_path or not self.same_path(self.loaded_path, expected_path):
            return
        self.playback_duration = duration
        elapsed = self.current_elapsed()
        total = self.format_time(duration) if duration > 0 else "--:--"
        self.play_info_label.setText(f"{self.format_time(elapsed)} / {total}")

    def pause_playback(self):
        if not self.playing_path:
            return
        self.paused_elapsed = min(self.current_elapsed(), self.playback_duration or self.current_elapsed())
        self.playback.pause()
        self.playback_timer.stop()
        self.paused_path = self.playing_path
        self.playing_path = None
        self.play_button.setText("Play")
        self.play_info_label.setStyleSheet("")
        self.play_info_label.setText(f"{self.format_time(self.paused_elapsed)} / {self.format_time(self.playback_duration)}")

    def resume_playback(self):
        if not self.paused_path:
            return
        self.playback.resume()
        self.playing_path = self.paused_path
        self.paused_path = None
        self.play_button.setText("Pause")
        self.play_button.setStyleSheet(f"color: {ACCENT_AMBER};")
        self.play_info_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        self.playback_timer.start()

    def finish_playback(self, elapsed):
        self.playback.stop()
        self.playback_timer.stop()
        self.playing_path = None
        self.paused_path = None
        self.paused_elapsed = 0.0
        end = self.playback_duration if self.playback_duration > 0 else elapsed
        if self.playback_duration > 0:
            self.play_slider.setValue(1000)
        self.play_info_label.setText(f"{self.format_time(end)} / {self.format_time(self.playback_duration)}")
        self.play_info_label.setStyleSheet("")
        self.play_button.setText("Play")
        self.play_button.setStyleSheet("")

    def unload_playback(self):
        try:
            self.playback.release()
        except Exception:
            pass
        self.clear_loaded_playback_ui()

    def stop_loaded_playback(self, clear_ui=False):
        try:
            self.playback.stop()
        except Exception:
            pass
        if clear_ui:
            self.clear_loaded_playback_ui()
            return
        self.playback_timer.stop()
        self.playing_path = None
        self.paused_path = None
        self.paused_elapsed = 0.0
        self.play_button.setText("Play")
        self.play_button.setStyleSheet("")
        self.play_info_label.setStyleSheet("")

    def clear_loaded_playback_ui(self):
        self.playback_timer.stop()
        self.loaded_path = None
        self.playing_path = None
        self.paused_path = None
        self.playback_duration = 0.0
        self.playback_seek_offset = 0.0
        self.paused_elapsed = 0.0
        self.play_file_label.setText("No audio")
        self.play_info_label.setText("00:00 / 00:00")
        self.play_info_label.setStyleSheet("")
        self.play_slider.setValue(0)
        self.play_button.setText("Play")
        self.play_button.setStyleSheet("")

    def release_playback_for_path(self, path):
        active_path = self.playing_path or self.paused_path or self.loaded_path
        if not active_path:
            return
        if self.same_path(active_path, path):
            self.unload_playback()

    def same_path(self, left, right):
        try:
            return Path(left).resolve() == Path(right).resolve()
        except OSError:
            return str(left).lower() == str(right).lower()

    def closeEvent(self, event):
        self.settings = load_app_settings()
        if not self.isMinimized():
            size = self.normalGeometry().size() if self.isMaximized() else self.size()
            self.settings["window_width"] = max(720, size.width())
            self.settings["window_height"] = max(420, size.height())
            self.settings["window_maximized"] = self.isMaximized()
        self.settings["player_cluster_width"] = self.player_cluster_width
        save_app_settings(self.settings)
        self.unload_playback()
        super().closeEvent(event)


def default_db_arg():
    return initial_database_path(sys.argv[1] if len(sys.argv) > 1 else None)
