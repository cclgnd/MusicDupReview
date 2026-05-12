import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from pyside_app.data_sources import file_explorer_rows
from pyside_app.models.file_explorer import FileExplorerModel
from pyside_app.widgets.file_preview import FilePreviewWidget


class FileExplorerRefreshWorker(QThread):
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, db_path, search_text, contiguous_hash_mode):
        super().__init__()
        self.db_path = db_path
        self.search_text = search_text
        self.contiguous_hash_mode = contiguous_hash_mode

    def run(self):
        try:
            self.finished_ok.emit(file_explorer_rows(
                self.db_path,
                search_text=self.search_text,
                contiguous_hash_mode=self.contiguous_hash_mode,
            ))
        except Exception as exc:
            self.failed.emit(str(exc))


class FileExplorerView(QWidget):
    def __init__(self, db_path_getter):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search files")
        self.contiguous_hash = QCheckBox("Contiguous identical hashes")
        self.refresh_worker = None
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.status = QLabel("Ready")
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
        top.addWidget(self.refresh_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.preview)
        layout.addWidget(self.status)
        self.search.returnPressed.connect(self.refresh)
        self.contiguous_hash.stateChanged.connect(self.refresh)

    def refresh(self):
        if self.refresh_worker and self.refresh_worker.isRunning():
            self.status.setText("File search already running.")
            return
        self.status.setText("Loading files...")
        self.refresh_button.setEnabled(False)
        self.refresh_worker = FileExplorerRefreshWorker(
            self.db_path_getter(),
            self.search.text(),
            self.contiguous_hash.isChecked(),
        )
        self.refresh_worker.finished_ok.connect(self._refresh_finished)
        self.refresh_worker.failed.connect(self._refresh_failed)
        self.refresh_worker.start()

    def _refresh_finished(self, rows):
        self.refresh_button.setEnabled(True)
        self.model.set_files(rows)
        self.preview.set_file(None)
        self.status.setText(f"{len(rows):,} files loaded.")

    def _refresh_failed(self, message):
        self.refresh_button.setEnabled(True)
        self.status.setText("File search failed.")
        self.preview.set_file(None)
        QMessageBox.critical(self, "File search", message)

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
