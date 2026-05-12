import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database_maintenance import verify_database_files
from db_repository import duplicate_extensions, duplicate_group_ids, duplicate_group_rows, ensure_schema
from duplicate_rules import apply_rule_to_groups, rule_label
from file_actions import FileActionError, send_to_recycle_bin
from playback_service import PlaybackService
from review_state import save_decision, save_decisions_bulk
from undo_service import UndoStack

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = str(APP_DIR / "music_library.db")
MATCH_OPTIONS = [
    ("All", "all"),
    ("Exact file", "md5"),
    ("Same audio", "audio_md5"),
    ("Same image", "image_ahash"),
    ("Same name + size", "nombre_tamano"),
    ("Similar name", "nombre_normalizado"),
    ("Exact filename", "nombre_identico"),
]
RULE_OPTIONS = [
    ("Keep longest path", "longest_path"),
    ("Keep shortest path", "shortest_path"),
    ("Keep largest file", "largest"),
    ("Keep smallest file", "smallest"),
    ("Keep newest modified", "newest"),
    ("Keep oldest modified", "oldest"),
    ("Trash exact hash duplicates only", "exact_hash"),
    ("Clear choices", "clear"),
]


def open_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def format_bytes(size):
    size = int(size or 0)
    units = ["bytes", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "bytes":
        return f"{size:,} bytes"
    return f"{value:.2f} {unit}"


def decision_label(decision):
    return {
        "master": "Keep",
        "delete": "Trash",
        "deleted": "Deleted",
        "missing": "Missing",
        "protected": "Protected",
        "ignored": "Ignored",
        "": "Unreviewed",
    }.get(decision or "", decision or "Unreviewed")


def decision_color(decision):
    return QColor({
        "master": "#14532d",
        "delete": "#7f1d1d",
        "deleted": "#991b1b",
        "missing": "#991b1b",
        "protected": "#1e3a8a",
        "ignored": "#3f3f46",
        "": "#27272a",
    }.get(decision or "", "#27272a"))


def file_explorer_order(contiguous_hash_mode):
    if contiguous_hash_mode:
        return "COALESCE(a.audio_md5, a.md5, ''), a.carpeta, a.ruta"
    return "lower(a.nombre)"


class DuplicateRemovalView(QWidget):
    def __init__(self, db_path_getter):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.match = QComboBox()
        for label, value in MATCH_OPTIONS:
            self.match.addItem(label, value)
        self.extension = QComboBox()
        self.sort = QComboBox()
        self.sort.addItems(["group_id", "biggest file", "name", "date"])
        self.rule = QComboBox()
        for label, value in RULE_OPTIONS:
            self.rule.addItem(label, value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search path")
        self.summary = QLabel("")
        self.current_group_id = None
        self.current_rows = []
        self.loaded_group_ids = []
        self.undo_stack = UndoStack(maxlen=400)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Group", "Match", "Files", "Largest", "Recoverable", "First file"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.load_selected_group)

        self.files = QTableWidget(0, 7)
        self.files.setHorizontalHeaderLabels(["State", "Name", "Extension", "Size", "Folder", "Path", "ID"])
        self.files.horizontalHeader().setStretchLastSection(True)
        self.files.setSelectionBehavior(QTableWidget.SelectRows)
        self.files.setColumnHidden(6, True)

        keep = QPushButton("Keep")
        trash = QPushButton("Trash")
        clear = QPushButton("Clear")
        apply_group = QPushButton("Apply selected group")
        apply_page = QPushButton("Apply loaded page")
        apply_search = QPushButton("Apply full search")
        reset_group = QPushButton("Reset selected group")
        reset_page = QPushButton("Reset loaded page")
        reset_search = QPushButton("Reset full search")
        rule_group = QPushButton("Rule selected group")
        rule_page = QPushButton("Rule loaded page")
        rule_search = QPushButton("Rule full search")
        keep.clicked.connect(lambda: self.set_selected_file_state("master"))
        trash.clicked.connect(lambda: self.set_selected_file_state("delete"))
        clear.clicked.connect(lambda: self.set_selected_file_state(""))
        apply_group.clicked.connect(self.apply_selected_group)
        apply_page.clicked.connect(self.apply_loaded_page)
        apply_search.clicked.connect(self.apply_full_search)
        reset_group.clicked.connect(self.reset_selected_group)
        reset_page.clicked.connect(self.reset_loaded_page)
        reset_search.clicked.connect(self.reset_full_search)
        rule_group.clicked.connect(lambda: self.apply_rule_scope("selected group"))
        rule_page.clicked.connect(lambda: self.apply_rule_scope("loaded page"))
        rule_search.clicked.connect(lambda: self.apply_rule_scope("full search"))
        QShortcut(QKeySequence("K"), self, activated=lambda: self.set_selected_file_state("master"))
        QShortcut(QKeySequence("T"), self, activated=lambda: self.set_selected_file_state("delete"))
        QShortcut(QKeySequence("D"), self, activated=self.recycle_selected_files_direct)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_last_action)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Match"))
        toolbar.addWidget(self.match)
        toolbar.addWidget(QLabel("Extension"))
        toolbar.addWidget(self.extension)
        toolbar.addWidget(QLabel("Sort"))
        toolbar.addWidget(self.sort)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(refresh)

        actions = QHBoxLayout()
        actions.addWidget(keep)
        actions.addWidget(trash)
        actions.addWidget(clear)
        actions.addStretch(1)
        actions.addWidget(apply_group)
        actions.addWidget(apply_page)
        actions.addWidget(apply_search)
        actions.addWidget(reset_group)
        actions.addWidget(reset_page)
        actions.addWidget(reset_search)
        actions.addWidget(self.rule)
        actions.addWidget(rule_group)
        actions.addWidget(rule_page)
        actions.addWidget(rule_search)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.files)
        splitter.setSizes([300, 420])

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addLayout(actions)
        layout.addWidget(self.summary)
        layout.addWidget(splitter, 1)

        self.match.currentIndexChanged.connect(self.refresh)
        self.extension.currentIndexChanged.connect(self.refresh)
        self.sort.currentIndexChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.refresh)

    def refresh_extensions(self):
        current = self.extension.currentData() or "ALL"
        self.extension.blockSignals(True)
        self.extension.clear()
        self.extension.addItem("All", "ALL")
        try:
            with open_conn(self.db_path_getter()) as conn:
                for ext in duplicate_extensions(conn):
                    self.extension.addItem(ext, ext)
        except Exception:
            pass
        index = self.extension.findData(current)
        self.extension.setCurrentIndex(max(0, index))
        self.extension.blockSignals(False)

    def refresh(self):
        self.refresh_extensions()
        db_path = self.db_path_getter()
        if not os.path.exists(db_path):
            self.summary.setText("Database not found")
            self.table.setRowCount(0)
            return
        with open_conn(db_path) as conn:
            group_ids = duplicate_group_ids(
                conn,
                match_filter=self.match.currentData(),
                extension_filter=self.extension.currentData() or "ALL",
                search_text=self.search.text().strip(),
                group_sort=self.sort.currentText(),
            )
            self.table.setRowCount(0)
            self.files.setRowCount(0)
            self.current_group_id = None
            self.current_rows = []
            self.loaded_group_ids = group_ids[:500]
            total_files = 0
            for group_id in self.loaded_group_ids:
                rows = duplicate_group_rows(conn, group_id, "hash")
                if len(rows) < 2:
                    continue
                total_files += len(rows)
                sizes = [row["tamano"] or 0 for row in rows]
                largest = max(sizes)
                recoverable = sum(sizes) - largest
                index = self.table.rowCount()
                self.table.insertRow(index)
                values = [
                    str(group_id),
                    str(rows[0].get("tipo_match") or ""),
                    str(len(rows)),
                    format_bytes(largest),
                    format_bytes(recoverable),
                    rows[0].get("ruta") or "",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                    self.table.setItem(index, column, item)
            suffix = " Showing first 500." if len(group_ids) > 500 else ""
            self.summary.setText(f"{len(group_ids):,} groups, {total_files:,} files loaded.{suffix}")

    def load_selected_group(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        item = self.table.item(selected[0].row(), 0)
        if not item:
            return
        self.current_group_id = int(item.text())
        with open_conn(self.db_path_getter()) as conn:
            self.current_rows = duplicate_group_rows(conn, self.current_group_id, "hash")
        self.render_files()

    def render_files(self):
        self.files.setRowCount(0)
        for row in self.current_rows:
            index = self.files.rowCount()
            self.files.insertRow(index)
            decision = row.get("decision") or ""
            values = [
                decision_label(decision),
                row.get("nombre") or "",
                row.get("extension") or "",
                format_bytes(row.get("tamano")),
                row.get("carpeta") or "",
                row.get("ruta") or "",
                str(row.get("id")),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                if column == 0:
                    item.setBackground(decision_color(decision))
                    item.setForeground(Qt.white)
                self.files.setItem(index, column, item)

    def selected_file_rows(self):
        selected = self.files.selectionModel().selectedRows()
        rows = []
        for model_index in selected:
            id_item = self.files.item(model_index.row(), 6)
            if id_item:
                file_id = int(id_item.text())
                row = next((r for r in self.current_rows if r["id"] == file_id), None)
                if row:
                    rows.append(row)
        return rows

    def selected_playback_path(self):
        rows = self.selected_file_rows()
        if not rows:
            return None
        row = rows[0]
        if (row.get("decision") or "") in ("deleted", "missing"):
            return None
        path = row.get("ruta")
        return path if path and os.path.exists(path) else None

    def set_selected_file_state(self, decision):
        rows = self.selected_file_rows()
        if not rows:
            QMessageBox.information(self, "State", "Select file rows first.")
            return
        self.undo_stack.push("state", rows)
        with open_conn(self.db_path_getter()) as conn:
            for row in rows:
                save_decision(conn, row["id"], decision)
                row["decision"] = decision
        self.render_files()
        self.summary.setText(f"Updated {len(rows)} file state(s).")

    def recycle_selected_files_direct(self):
        rows = [
            row for row in self.selected_file_rows()
            if os.path.exists(row.get("ruta") or "") and (row.get("decision") or "") not in ("deleted", "missing")
        ]
        if not rows:
            QMessageBox.information(self, "Recycle", "Select existing file rows first.")
            return
        self.undo_stack.push("delete", rows)
        errors = []
        changed = 0
        with open_conn(self.db_path_getter()) as conn:
            for row in rows:
                try:
                    send_to_recycle_bin(row["ruta"])
                    save_decision(conn, row["id"], "deleted")
                    row["decision"] = "deleted"
                    changed += 1
                except FileActionError as exc:
                    errors.append(f"{row['ruta']}: {exc}")
        self.render_files()
        if errors:
            QMessageBox.critical(self, "Recycle errors", "\n".join(errors[:10]))
        self.summary.setText(f"Sent {changed} file(s) to Recycle Bin.")

    def undo_last_action(self):
        item = self.undo_stack.pop()
        if not item:
            self.summary.setText("Nothing to undo.")
            return
        restored = 0
        blocked = 0
        with open_conn(self.db_path_getter()) as conn:
            for state in item["rows"]:
                row = next((r for r in self.current_rows if r["id"] == state["id"]), None)
                if item["action"] == "delete" and not os.path.exists(state.get("path", "")):
                    save_decision(conn, state["id"], "deleted")
                    if row:
                        row["decision"] = "deleted"
                    blocked += 1
                    continue
                save_decision(conn, state["id"], state["decision"])
                if row:
                    row["decision"] = state["decision"]
                restored += 1
        self.render_files()
        self.summary.setText(f"Undo restored {restored} state(s); {blocked} file(s) still in Recycle Bin.")

    def apply_selected_group(self):
        if self.current_group_id is None:
            QMessageBox.information(self, "Apply", "Select a group first.")
            return
        self.apply_group_ids([self.current_group_id], "selected group")

    def apply_loaded_page(self):
        if not self.loaded_group_ids:
            QMessageBox.information(self, "Apply", "No loaded groups.")
            return
        self.apply_group_ids(self.loaded_group_ids, "loaded page")

    def apply_full_search(self):
        with open_conn(self.db_path_getter()) as conn:
            group_ids = duplicate_group_ids(
                conn,
                match_filter=self.match.currentData(),
                extension_filter=self.extension.currentData() or "ALL",
                search_text=self.search.text().strip(),
                group_sort=self.sort.currentText(),
            )
        if not group_ids:
            QMessageBox.information(self, "Apply", "No groups in current search.")
            return
        self.apply_group_ids(group_ids, "full search")

    def apply_group_ids(self, group_ids, scope_label):
        delete_by_id = {}
        with open_conn(self.db_path_getter()) as conn:
            for group_id in group_ids:
                for row in duplicate_group_rows(conn, group_id, "hash"):
                    if (row.get("decision") or "") == "delete":
                        delete_by_id[row["id"]] = row
        deletes = [row for row in delete_by_id.values() if os.path.exists(row.get("ruta") or "")]
        if not deletes:
            QMessageBox.information(self, "Apply", f"No existing files marked Trash in {scope_label}.")
            return
        preview = "\n".join(row["ruta"] for row in deletes[:8])
        if len(deletes) > 8:
            preview += f"\n... and {len(deletes) - 8} more"
        answer = QMessageBox.question(
            self,
            "Delete confirmation",
            f"Apply scope: {scope_label}\nSend {len(deletes)} file(s) to Recycle Bin?\n\n{preview}\n\nNo permanent delete will be used.",
        )
        if answer != QMessageBox.Yes:
            return
        errors = []
        changed = 0
        with open_conn(self.db_path_getter()) as conn:
            for row in deletes:
                try:
                    send_to_recycle_bin(row["ruta"])
                    save_decision(conn, row["id"], "deleted")
                    row["decision"] = "deleted"
                    changed += 1
                except FileActionError as exc:
                    errors.append(f"{row['ruta']}: {exc}")
        self.render_files()
        self.refresh()
        if errors:
            QMessageBox.critical(self, "Apply errors", "\n".join(errors[:10]))
        self.summary.setText(f"Sent {changed} file(s) to Recycle Bin.")

    def reset_selected_group(self):
        if self.current_group_id is None:
            QMessageBox.information(self, "Reset", "Select a group first.")
            return
        self.reset_group_ids([self.current_group_id], "selected group")

    def reset_loaded_page(self):
        if not self.loaded_group_ids:
            QMessageBox.information(self, "Reset", "No loaded groups.")
            return
        self.reset_group_ids(self.loaded_group_ids, "loaded page")

    def reset_full_search(self):
        with open_conn(self.db_path_getter()) as conn:
            group_ids = duplicate_group_ids(
                conn,
                match_filter=self.match.currentData(),
                extension_filter=self.extension.currentData() or "ALL",
                search_text=self.search.text().strip(),
                group_sort=self.sort.currentText(),
            )
        if not group_ids:
            QMessageBox.information(self, "Reset", "No groups in current search.")
            return
        self.reset_group_ids(group_ids, "full search")

    def reset_group_ids(self, group_ids, scope_label):
        rows_by_id = {}
        with open_conn(self.db_path_getter()) as conn:
            for group_id in group_ids:
                for row in duplicate_group_rows(conn, group_id, "hash"):
                    if (row.get("decision") or "") in ("master", "delete", "protected", "ignored"):
                        rows_by_id[row["id"]] = row
            if not rows_by_id:
                QMessageBox.information(self, "Reset", f"No review choices to reset in {scope_label}.")
                return
            for file_id in rows_by_id:
                save_decision(conn, file_id, "")
        for row in self.current_rows:
            if row["id"] in rows_by_id:
                row["decision"] = ""
        self.render_files()
        self.refresh()
        self.summary.setText(f"Reset {len(rows_by_id)} review choice(s) in {scope_label}.")

    def apply_rule_scope(self, scope_label):
        group_ids = self.group_ids_for_scope(scope_label)
        if not group_ids:
            QMessageBox.information(self, "Rules", f"No groups in {scope_label}.")
            return
        rule = self.rule.currentData()
        answer = QMessageBox.question(
            self,
            "Rules",
            f"Apply rule to {len(group_ids)} group(s)?\n\nRule: {rule_label(rule)}\nScope: {scope_label}\n\nFiles are not moved until Apply.",
        )
        if answer != QMessageBox.Yes:
            return
        groups = []
        with open_conn(self.db_path_getter()) as conn:
            for group_id in group_ids:
                rows = duplicate_group_rows(conn, group_id, "hash")
                if len(rows) >= 2:
                    groups.append(rows)
            decision_updates, changed = apply_rule_to_groups(groups, rule)
            save_decisions_bulk(conn, decision_updates)
        current_group_id = self.current_group_id
        self.refresh()
        if current_group_id is not None:
            self.load_current_group_by_id(current_group_id)
        self.summary.setText(f"Rule applied to {len(groups)} group(s): {changed} file choice(s) changed.")

    def group_ids_for_scope(self, scope_label):
        if scope_label == "selected group":
            return [self.current_group_id] if self.current_group_id is not None else []
        if scope_label == "loaded page":
            return self.loaded_group_ids[:]
        with open_conn(self.db_path_getter()) as conn:
            return duplicate_group_ids(
                conn,
                match_filter=self.match.currentData(),
                extension_filter=self.extension.currentData() or "ALL",
                search_text=self.search.text().strip(),
                group_sort=self.sort.currentText(),
            )

    def load_current_group_by_id(self, group_id):
        with open_conn(self.db_path_getter()) as conn:
            self.current_rows = duplicate_group_rows(conn, group_id, "hash")
        self.current_group_id = group_id
        self.render_files()


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


class MaintenanceWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

    def run(self):
        try:
            self.finished_ok.emit(verify_database_files(self.db_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class UtilitiesView(QWidget):
    def __init__(self, db_path_getter):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.worker = None
        self.status = QLabel("Ready")
        self.backups = QListWidget()
        check = QPushButton("Check Files Now")
        check.clicked.connect(self.check_files)
        backup = QPushButton("Backup Current Database")
        backup.clicked.connect(self.backup_database)
        refresh_backups = QPushButton("Refresh Backup List")
        refresh_backups.clicked.connect(self.refresh_backups)

        layout = QVBoxLayout(self)
        layout.addWidget(check)
        layout.addWidget(backup)
        layout.addWidget(refresh_backups)
        layout.addWidget(QLabel("Backups"))
        layout.addWidget(self.backups, 1)
        layout.addWidget(QLabel("Pending: recent searches, re-unify files, integrity report."))
        layout.addWidget(self.status)
        self.refresh_backups()

    def check_files(self):
        db_path = self.db_path_getter()
        if not os.path.exists(db_path):
            QMessageBox.warning(self, "Check files", "Database not found.")
            return
        self.status.setText("Checking database paths...")
        self.worker = MaintenanceWorker(db_path)
        self.worker.finished_ok.connect(self._check_finished)
        self.worker.failed.connect(self._check_failed)
        self.worker.start()

    def _check_finished(self, stats):
        self.status.setText(
            f"Missing {stats['missing']}, existing {stats['existing']}, new {stats['new']}, duplicate rows {stats['duplicates']}"
        )

    def _check_failed(self, message):
        self.status.setText("Check failed")
        QMessageBox.critical(self, "Check files", message)

    def backup_database(self):
        source = Path(self.db_path_getter())
        if not source.exists():
            QMessageBox.warning(self, "Backup", "Database not found.")
            return
        backup_dir = Path(__file__).resolve().parents[1] / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"{source.stem}_backup_pyside_{stamp}{source.suffix}"
        backup.write_bytes(source.read_bytes())
        self.status.setText(f"Backup created: {backup}")
        self.refresh_backups()

    def refresh_backups(self):
        self.backups.clear()
        backup_dir = Path(__file__).resolve().parents[1] / "backups"
        if not backup_dir.exists():
            return
        for path in sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
            self.backups.addItem(str(path))


class MainWindow(QMainWindow):
    def __init__(self, db_path=DEFAULT_DB):
        super().__init__()
        self.db_path = db_path
        self.playback = PlaybackService()
        self.playing_path = None
        self.setWindowTitle("Music Duplicate Review - PySide6")
        self.resize(1180, 760)

        self.nav = QListWidget()
        self.stack = QStackedWidget()
        self.views = [
            ("Duplicate Removal", DuplicateRemovalView(self.current_db_path)),
            ("File Explorer", FileExplorerView(self.current_db_path)),
            ("Utilities", UtilitiesView(self.current_db_path)),
        ]
        for label, widget in self.views:
            self.nav.addItem(QListWidgetItem(label))
            self.stack.addWidget(widget)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(self.nav, 0)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Open Database", self.open_database)
        file_menu.addAction("Refresh Current View", self.refresh_current_view)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        self.statusBar().showMessage(self.db_path)
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_label = QLabel("No audio")
        self.statusBar().addPermanentWidget(self.play_label, 1)
        self.statusBar().addPermanentWidget(self.play_button)
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_playback)
        self.refresh_current_view()

    def current_db_path(self):
        return self.db_path

    def open_database(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open duplicate database", self.db_path, "SQLite database (*.db *.sqlite);;All files (*.*)"
        )
        if path:
            self.db_path = path
            self.statusBar().showMessage(self.db_path)
            self.refresh_current_view()

    def refresh_current_view(self):
        widget = self.stack.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def toggle_playback(self):
        if self.playing_path:
            self.stop_playback()
            return
        widget = self.stack.currentWidget()
        path = widget.selected_playback_path() if hasattr(widget, "selected_playback_path") else None
        if not path:
            self.play_label.setText("Select an existing playable file")
            return
        if not self.playback.available:
            QMessageBox.warning(self, "Playback", "pygame playback backend is unavailable.")
            return
        try:
            self.playback.play(path)
            self.playing_path = path
            self.play_label.setText(Path(path).name)
            self.play_button.setText("Stop")
        except Exception as exc:
            QMessageBox.critical(self, "Playback", str(exc))
            self.stop_playback()

    def stop_playback(self):
        try:
            self.playback.stop()
        except Exception:
            pass
        self.playing_path = None
        self.play_label.setText("No audio")
        self.play_button.setText("Play")

    def closeEvent(self, event):
        self.stop_playback()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
