import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from db_repository import duplicate_extensions, duplicate_group_ids, duplicate_group_rows
from duplicate_rules import apply_rule_to_groups, rule_label
from file_actions import FileActionError, send_to_recycle_bin
from pyside_app.config import MATCH_OPTIONS, RULE_OPTIONS
from pyside_app.data_sources import duplicate_group_summaries
from pyside_app.db import open_conn
from pyside_app.models.duplicate_tables import DuplicateFilesModel, DuplicateGroupsModel
from pyside_app.widgets.file_preview import FilePreviewWidget
from review_state import save_decision, save_decisions_bulk
from undo_service import UndoStack


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
        self.group_model = DuplicateGroupsModel(self)
        self.file_model = DuplicateFilesModel(self)
        self.table = QTableView()
        self.table.setModel(self.group_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().selectionChanged.connect(self.load_selected_group)

        self.files = QTableView()
        self.files.setModel(self.file_model)
        self.files.horizontalHeader().setStretchLastSection(True)
        self.files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.hideColumn(6)
        self.files.selectionModel().selectionChanged.connect(self.update_preview)
        self.preview = FilePreviewWidget(self)

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
        splitter.addWidget(self.preview)
        splitter.setSizes([260, 360, 180])

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
            self.group_model.set_groups([])
            self.file_model.set_files([])
            self.preview.set_file(None)
            return

        group_ids, visible_group_ids, group_rows, total_files = duplicate_group_summaries(
            db_path,
            match_filter=self.match.currentData(),
            extension_filter=self.extension.currentData() or "ALL",
            search_text=self.search.text().strip(),
            group_sort=self.sort.currentText(),
        )
        self.file_model.set_files([])
        self.current_group_id = None
        self.current_rows = []
        self.preview.set_file(None)
        self.loaded_group_ids = visible_group_ids
        self.group_model.set_groups(group_rows)
        suffix = " Showing first 500." if len(group_ids) > len(visible_group_ids) else ""
        self.summary.setText(f"{len(group_ids):,} groups, {total_files:,} files loaded.{suffix}")

    def load_selected_group(self, *_args):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        group_id = self.group_model.group_id_at(selected[0].row())
        if group_id is None:
            return
        self.current_group_id = group_id
        with open_conn(self.db_path_getter()) as conn:
            self.current_rows = duplicate_group_rows(conn, self.current_group_id, "hash")
        self.render_files()

    def render_files(self):
        self.file_model.set_files(self.current_rows)
        self.preview.set_file(None)

    def selected_file_rows(self):
        selected = self.files.selectionModel().selectedRows()
        return self.file_model.file_rows_at(model_index.row() for model_index in selected)

    def selected_playback_path(self):
        rows = self.selected_file_rows()
        if not rows:
            return None
        row = rows[0]
        if (row.get("decision") or "") in ("deleted", "missing"):
            return None
        path = row.get("ruta")
        return path if path and os.path.exists(path) else None

    def update_preview(self, *_args):
        rows = self.selected_file_rows()
        self.preview.set_file(rows[0] if rows else None)

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
