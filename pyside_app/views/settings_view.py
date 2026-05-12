from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from pyside_app.settings import load_app_settings, save_app_settings


class SettingsView(QWidget):
    def __init__(self, db_path_getter, database_setter):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.database_setter = database_setter
        self.db_label = QLabel()
        self.db_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.db_label.setWordWrap(True)
        self.scan_folder_label = QLabel()
        self.scan_folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.scan_folder_label.setWordWrap(True)

        choose_db = QPushButton("Choose Database...")
        choose_db.clicked.connect(self.choose_database)
        choose_scan_folder = QPushButton("Set Default Scan Folder...")
        choose_scan_folder.clicked.connect(self.choose_scan_folder)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Active Database"))
        layout.addWidget(self.db_label)
        layout.addWidget(choose_db)
        layout.addWidget(QLabel("Default Scan Folder"))
        layout.addWidget(self.scan_folder_label)
        layout.addWidget(choose_scan_folder)
        layout.addStretch(1)
        self.refresh()

    def refresh(self):
        settings = load_app_settings()
        self.db_label.setText(self.db_path_getter())
        self.scan_folder_label.setText(settings.get("last_scan_folder") or "Not set")

    def choose_database(self):
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Open duplicate database",
            self.db_path_getter(),
            "SQLite database (*.db *.sqlite);;All files (*.*)",
        )
        if path:
            self.database_setter(path)
            self.refresh()

    def choose_scan_folder(self):
        settings = load_app_settings()
        start_folder = settings.get("last_scan_folder", "")
        if start_folder and not Path(start_folder).is_dir():
            start_folder = ""
        folder = QFileDialog.getExistingDirectory(self, "Default scan folder", start_folder)
        if folder:
            settings["last_scan_folder"] = folder
            save_app_settings(settings)
            self.refresh()
