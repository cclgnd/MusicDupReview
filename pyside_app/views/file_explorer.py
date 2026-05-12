import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from pyside_app.db import open_conn
from pyside_app.formatting import decision_label, format_bytes


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
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Extension", "Size", "Folder", "Status", "Hash link"])
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
        self.table.setRowCount(0)
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
            for row in cursor.fetchall():
                index = self.table.rowCount()
                self.table.insertRow(index)
                current_hash = row["audio_md5"] or row["md5"] or ""
                hash_link = "same as previous" if current_hash and current_hash == previous_hash else ""
                values = [
                    row["nombre"],
                    row["extension"],
                    format_bytes(row["tamano"]),
                    row["carpeta"],
                    decision_label(row["decision"]),
                    hash_link,
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value or ""))
                    item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                    if hash_link:
                        item.setBackground(QColor("#1e3a8a"))
                        item.setForeground(Qt.white)
                    self.table.setItem(index, column, item)
                previous_hash = current_hash
