from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from pyside_app.formatting import decision_label, format_bytes


class FileExplorerModel(QAbstractTableModel):
    headers = ["Name", "Extension", "Size", "Folder", "Status", "Hash link"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def set_files(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = index.column()
        values = [
            row.get("nombre") or "",
            row.get("extension") or "",
            format_bytes(row.get("tamano")),
            row.get("carpeta") or "",
            decision_label(row.get("decision")),
            row.get("hash_link") or "",
        ]
        if role == Qt.DisplayRole:
            return values[column]
        if role == Qt.BackgroundRole and row.get("hash_link"):
            return QColor("#1e3a8a")
        if role == Qt.ForegroundRole and row.get("hash_link"):
            return QColor("#ffffff")
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def file_rows_at(self, row_indexes):
        rows = []
        for row_index in row_indexes:
            if 0 <= row_index < len(self.rows):
                rows.append(self.rows[row_index])
        return rows
