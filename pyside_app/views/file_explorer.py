from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QTableView, QVBoxLayout, QWidget

from pyside_app.data_sources import file_explorer_rows
from pyside_app.models.file_explorer import FileExplorerModel


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

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.contiguous_hash)
        top.addWidget(refresh)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        self.search.returnPressed.connect(self.refresh)
        self.contiguous_hash.stateChanged.connect(self.refresh)

    def refresh(self):
        self.model.set_files(file_explorer_rows(
            self.db_path_getter(),
            search_text=self.search.text(),
            contiguous_hash_mode=self.contiguous_hash.isChecked(),
        ))
