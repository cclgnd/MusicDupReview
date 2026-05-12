import os

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QTableView, QVBoxLayout, QWidget

from pyside_app.db import open_conn
from pyside_app.models.file_explorer import FileExplorerModel


def file_explorer_order(contiguous_hash_mode):
    if contiguous_hash_mode:
        return "COALESCE(a.audio_md5, a.md5, ''), a.carpeta, a.ruta"
    return "lower(a.nombre)"


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
        db_path = self.db_path_getter()
        self.model.set_files([])
        if not os.path.exists(db_path):
            return
        term = f"%{self.search.text().strip()}%"
        with open_conn(db_path) as conn:
            cursor = conn.cursor()
            if self.search.text().strip():
                cursor.execute("""
                    SELECT a.nombre, a.extension, a.tamano, a.carpeta, a.ruta, a.md5, a.audio_md5,
                           COALESCE(d.decision,'') AS decision
                    FROM archivos a
                    LEFT JOIN decisiones d ON d.archivo_id = a.id
                    WHERE a.ruta LIKE ?
                    ORDER BY """ + file_explorer_order(self.contiguous_hash.isChecked()) + """
                    LIMIT 500
                """, (term,))
            else:
                cursor.execute("""
                    SELECT a.nombre, a.extension, a.tamano, a.carpeta, a.ruta, a.md5, a.audio_md5,
                           COALESCE(d.decision,'') AS decision
                    FROM archivos a
                    LEFT JOIN decisiones d ON d.archivo_id = a.id
                    ORDER BY """ + file_explorer_order(self.contiguous_hash.isChecked()) + """
                    LIMIT 500
                """)
            previous_hash = None
            rows = []
            for row in cursor.fetchall():
                current_hash = row["audio_md5"] or row["md5"] or ""
                hash_link = "same as previous" if current_hash and current_hash == previous_hash else ""
                row_data = dict(row)
                row_data["hash_link"] = hash_link
                rows.append(row_data)
                previous_hash = current_hash
            self.model.set_files(rows)
