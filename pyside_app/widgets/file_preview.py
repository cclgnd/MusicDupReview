import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from pyside_app.formatting import decision_label, format_bytes


class FilePreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_row = None
        self.name = QLabel("No file selected")
        self.name.setWordWrap(True)
        self.path = QLabel("")
        self.path.setWordWrap(True)
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.folder = QLabel("")
        self.folder.setWordWrap(True)
        self.md5 = QLabel("")
        self.md5.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.audio_md5 = QLabel("")
        self.audio_md5.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.size = QLabel("")
        self.state = QLabel("")

        open_file = QPushButton("Open File")
        open_folder = QPushButton("Open Folder")
        open_file.clicked.connect(self.open_file)
        open_folder.clicked.connect(self.open_folder)
        self.open_file_button = open_file
        self.open_folder_button = open_folder

        fields = QGridLayout()
        fields.addWidget(QLabel("Name"), 0, 0)
        fields.addWidget(self.name, 0, 1)
        fields.addWidget(QLabel("State"), 1, 0)
        fields.addWidget(self.state, 1, 1)
        fields.addWidget(QLabel("Size"), 2, 0)
        fields.addWidget(self.size, 2, 1)
        fields.addWidget(QLabel("Folder"), 3, 0)
        fields.addWidget(self.folder, 3, 1)
        fields.addWidget(QLabel("Path"), 4, 0)
        fields.addWidget(self.path, 4, 1)
        fields.addWidget(QLabel("MD5"), 5, 0)
        fields.addWidget(self.md5, 5, 1)
        fields.addWidget(QLabel("Audio MD5"), 6, 0)
        fields.addWidget(self.audio_md5, 6, 1)

        actions = QGridLayout()
        actions.addWidget(open_file, 0, 0)
        actions.addWidget(open_folder, 0, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Selected File"))
        layout.addLayout(fields)
        layout.addLayout(actions)
        self.set_file(None)

    def set_file(self, row):
        self.current_row = row
        has_file = bool(row)
        self.open_file_button.setEnabled(has_file)
        self.open_folder_button.setEnabled(has_file)
        if not row:
            self.name.setText("No file selected")
            self.state.setText("")
            self.size.setText("")
            self.folder.setText("")
            self.path.setText("")
            self.md5.setText("")
            self.audio_md5.setText("")
            return
        self.name.setText(row.get("nombre") or "")
        self.state.setText(decision_label(row.get("decision")))
        self.size.setText(format_bytes(row.get("tamano")))
        self.folder.setText(row.get("carpeta") or "")
        self.path.setText(row.get("ruta") or "")
        self.md5.setText(row.get("md5") or "")
        self.audio_md5.setText(row.get("audio_md5") or "")

    def open_file(self):
        path = self._current_path()
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_folder(self):
        row = self.current_row or {}
        folder = row.get("carpeta") or str(Path(row.get("ruta") or "").parent)
        if not folder or not os.path.isdir(folder):
            QMessageBox.information(self, "Open folder", "Selected file folder does not exist.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _current_path(self):
        path = (self.current_row or {}).get("ruta") or ""
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Open file", "Selected file does not exist.")
            return ""
        return path
