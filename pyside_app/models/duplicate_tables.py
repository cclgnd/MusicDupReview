from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from pyside_app.formatting import decision_color, decision_label, format_bytes


class DuplicateGroupsModel(QAbstractTableModel):
    headers = ["Group", "Match", "Files", "Largest", "Recoverable", "First file"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def set_groups(self, rows):
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
        if role == Qt.DisplayRole:
            return str(row[index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def group_id_at(self, row_index):
        if 0 <= row_index < len(self.rows):
            return int(self.rows[row_index][0])
        return None


class DuplicateFilesModel(QAbstractTableModel):
    headers = ["State", "Name", "Extension", "Size", "Folder", "Path", "ID"]

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
        decision = row.get("decision") or ""
        column = index.column()
        if role == Qt.DisplayRole:
            values = [
                decision_label(decision),
                row.get("nombre") or "",
                row.get("extension") or "",
                format_bytes(row.get("tamano")),
                row.get("carpeta") or "",
                row.get("ruta") or "",
                str(row.get("id")),
            ]
            return values[column]
        if role == Qt.BackgroundRole and column == 0:
            return decision_color(decision)
        if role == Qt.ForegroundRole and column == 0:
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
