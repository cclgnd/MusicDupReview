import os

from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QTableView, QVBoxLayout, QWidget

from pyside_app.data_sources import file_explorer_rows
from pyside_app.models.file_explorer import FileExplorerModel
from pyside_app.widgets.file_preview import FilePreviewWidget


class FileExplorerView(QWidget):
    def __init__(self, db_path_getter):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search files")
        self.contiguous_hash = QCheckBox("Contiguous identical hashes")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.model = FileExplorerModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.selectionModel().selectionChanged.connect(self.update_preview)
        self.preview = FilePreviewWidget(self)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.contiguous_hash)
        top.addWidget(refresh)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.preview)
        self.search.returnPressed.connect(self.refresh)
        self.contiguous_hash.stateChanged.connect(self.refresh)

    def refresh(self):
        self.model.set_files(file_explorer_rows(
            self.db_path_getter(),
            search_text=self.search.text(),
            contiguous_hash_mode=self.contiguous_hash.isChecked(),
        ))
        self.preview.set_file(None)

    def selected_file_rows(self):
        selected = self.table.selectionModel().selectedRows()
        return self.model.file_rows_at(model_index.row() for model_index in selected)

    def selected_playback_path(self):
        rows = self.selected_file_rows()
        if not rows:
            return None
        path = rows[0].get("ruta")
        return path if path and os.path.exists(path) else None

    def update_preview(self, *_args):
        rows = self.selected_file_rows()
        self.preview.set_file(rows[0] if rows else None)
