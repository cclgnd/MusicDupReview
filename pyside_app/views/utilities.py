from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database_maintenance import database_integrity_report, verify_database_files
from pyside_app.config import APP_DIR
from pyside_app.settings import load_app_settings, save_app_settings
from scan_service import scan_folder_to_database, scan_history_rows, scan_summary_lines


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


class FolderScanWorker(QThread):
    progress = Signal(dict)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path, folder):
        super().__init__()
        self.db_path = db_path
        self.folder = folder
        self.cancel_requested = False

    def cancel(self):
        self.cancel_requested = True

    def run(self):
        try:
            self.finished_ok.emit(
                scan_folder_to_database(
                    self.db_path,
                    self.folder,
                    self.progress.emit,
                    should_cancel=lambda: self.cancel_requested,
                )
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class UtilitiesView(QWidget):
    def __init__(self, db_path_getter, database_changed=None, database_setter=None):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.database_changed = database_changed
        self.database_setter = database_setter
        self.settings = load_app_settings()
        self.worker = None
        self.scan_worker = None
        self.status = QLabel("Ready")
        self.scan_detail = QLabel("")
        self.scan_detail.setWordWrap(True)
        self.scan_live = QTextEdit()
        self.scan_live.setReadOnly(True)
        self.scan_live.setMaximumHeight(140)
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.backups = QListWidget()
        self.scan_history = QListWidget()
        self.integrity_report = QTextEdit()
        self.integrity_report.setReadOnly(True)
        self.scan_button = QPushButton("Scan Folder...")
        self.scan_button.clicked.connect(self.scan_folder)
        self.open_scan_folder_button = QPushButton("Open Last Scan Folder")
        self.open_scan_folder_button.clicked.connect(self.open_last_scan_folder)
        self.cancel_scan_button = QPushButton("Cancel Scan")
        self.cancel_scan_button.setEnabled(False)
        self.cancel_scan_button.clicked.connect(self.cancel_scan)
        check = QPushButton("Check Files Now")
        check.clicked.connect(self.check_files)
        integrity = QPushButton("Refresh Integrity Report")
        integrity.clicked.connect(self.refresh_integrity_report)
        backup = QPushButton("Backup Current Database")
        backup.clicked.connect(self.backup_database)
        refresh_backups = QPushButton("Refresh Backup List")
        refresh_backups.clicked.connect(self.refresh_backups)

        scan_actions = QHBoxLayout()
        scan_actions.addWidget(self.scan_button)
        scan_actions.addWidget(self.open_scan_folder_button)
        scan_actions.addWidget(self.cancel_scan_button)

        layout = QVBoxLayout(self)
        layout.addLayout(scan_actions)
        layout.addWidget(check)
        layout.addWidget(integrity)
        layout.addWidget(backup)
        layout.addWidget(refresh_backups)
        layout.addWidget(self.scan_progress)
        layout.addWidget(self.scan_detail)
        layout.addWidget(self.scan_live)
        layout.addWidget(QLabel("Recent Scans"))
        layout.addWidget(self.scan_history, 1)
        layout.addWidget(QLabel("Backups"))
        layout.addWidget(self.backups, 1)
        layout.addWidget(QLabel("Integrity Report"))
        layout.addWidget(self.integrity_report, 1)
        layout.addWidget(self.status)
        self.refresh_scan_history()
        self.refresh_backups()
        self.refresh_integrity_report()

    def scan_folder(self):
        if self.scan_worker and self.scan_worker.isRunning():
            QMessageBox.information(self, "Scan folder", "A folder scan is already running.")
            return
        self.settings = load_app_settings()
        start_folder = self.settings.get("last_scan_folder", "")
        if start_folder and not Path(start_folder).is_dir():
            start_folder = ""
        folder = QFileDialog.getExistingDirectory(self, "Scan music folder", start_folder)
        if not folder:
            return
        self.settings["last_scan_folder"] = folder
        save_app_settings(self.settings)
        previous_db_path = self.db_path_getter()
        db_path = self.new_search_database_path(folder)
        self.status.setText(f"Scanning folder into new database: {db_path}")
        self.scan_detail.setText(folder)
        self.scan_live.setPlainText(
            f"Starting scan...\nNew database: {db_path}\nPrevious database: {previous_db_path}\nUI stays usable. Playback remains available."
        )
        self.scan_progress.setRange(0, 0)
        self.scan_progress.setVisible(True)
        self.scan_button.setEnabled(False)
        self.cancel_scan_button.setEnabled(True)
        self.scan_worker = FolderScanWorker(db_path, folder)
        self.scan_worker.previous_db_path = previous_db_path
        self.scan_worker.target_db_path = db_path
        self.scan_worker.progress.connect(self._scan_progress)
        self.scan_worker.finished_ok.connect(self._scan_finished)
        self.scan_worker.failed.connect(self._scan_failed)
        self.scan_worker.start()

    def cancel_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.cancel_scan_button.setEnabled(False)
            self.status.setText("Cancelling scan after current file...")

    def _scan_progress(self, stats):
        phase = stats.get("phase", "scan")
        self.status.setText(
            f"{phase.title()}... {stats['discovered']:,} seen, {stats['hashed']:,} hashed, {stats['files_per_second']:.1f}/s"
        )
        current = stats.get("current_path") or stats.get("current_folder") or stats.get("root") or ""
        self.scan_detail.setText(f"{phase}: {current}")
        lines = [
            f"Phase: {phase}",
            f"Folder: {stats.get('root', '')}",
            f"Current: {current}",
            f"Files seen: {stats['discovered']:,}",
            f"New: {stats['new']:,}   Updated: {stats['updated']:,}   Unchanged: {stats['unchanged']:,}",
            f"Hashed: {stats['hashed']:,}   Errors: {stats['errors']:,}",
            f"Duplicate groups: {stats.get('duplicate_groups', 0):,}   Duplicate files: {stats.get('duplicate_files', 0):,}",
            f"Elapsed: {stats.get('elapsed_seconds', 0.0):.1f}s   Rate: {stats.get('files_per_second', 0.0):.1f}/s",
        ]
        self.scan_live.setPlainText("\n".join(lines))
        self.scan_live.verticalScrollBar().setValue(self.scan_live.verticalScrollBar().maximum())

    def _scan_finished(self, stats):
        self.scan_button.setEnabled(True)
        self.cancel_scan_button.setEnabled(False)
        self.scan_progress.setVisible(False)
        title = "Scan cancelled" if stats.get("cancelled") else "Scan complete"
        self.status.setText(
            f"{title}: {stats['duplicate_groups']:,} duplicate groups, {stats['duplicate_files']:,} duplicate files"
        )
        self.scan_detail.setText(
            f"{stats['discovered']:,} files processed from {stats['root']}"
        )
        self.scan_live.setPlainText("\n".join(scan_summary_lines(stats)))
        target_db_path = getattr(self.scan_worker, "target_db_path", "")
        previous_db_path = getattr(self.scan_worker, "previous_db_path", "")
        if previous_db_path:
            self.vacuum_database(previous_db_path)
        if target_db_path:
            self.settings = load_app_settings()
            self.settings["db_path"] = target_db_path
            save_app_settings(self.settings)
            if self.database_setter:
                self.database_setter(target_db_path)
        if self.database_changed and not self.database_setter:
            self.database_changed()
        self.refresh_scan_history()
        self.refresh_integrity_report()

    def new_search_database_path(self, folder):
        root = Path(folder)
        safe_name = "".join(char if char.isalnum() else "_" for char in root.name).strip("_") or "search"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_dir = APP_DIR / "search_databases"
        db_dir.mkdir(exist_ok=True)
        return str(db_dir / f"{safe_name}_{stamp}.db")

    def vacuum_database(self, db_path):
        path = Path(db_path)
        if not path.exists():
            return
        try:
            import sqlite3
            conn = sqlite3.connect(str(path))
            try:
                conn.execute("VACUUM")
            finally:
                conn.close()
        except sqlite3.Error:
            return

    def _scan_failed(self, message):
        self.scan_button.setEnabled(True)
        self.cancel_scan_button.setEnabled(False)
        self.scan_progress.setVisible(False)
        self.status.setText("Scan failed")
        self.scan_detail.setText("")
        self.scan_live.setPlainText(message)
        QMessageBox.critical(self, "Scan folder", message)

    def open_last_scan_folder(self):
        settings = load_app_settings()
        folder = settings.get("last_scan_folder", "")
        if not folder or not Path(folder).is_dir():
            QMessageBox.information(self, "Scan folder", "No existing scan folder is saved.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def check_files(self):
        db_path = self.db_path_getter()
        if not Path(db_path).exists():
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
        backup_dir = Path(__file__).resolve().parents[2] / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"{source.stem}_backup_pyside_{stamp}{source.suffix}"
        backup.write_bytes(source.read_bytes())
        self.status.setText(f"Backup created: {backup}")
        self.refresh_backups()

    def refresh_backups(self):
        self.backups.clear()
        backup_dir = Path(__file__).resolve().parents[2] / "backups"
        if not backup_dir.exists():
            return
        for path in sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
            self.backups.addItem(str(path))

    def refresh_scan_history(self):
        self.scan_history.clear()
        for row in scan_history_rows(self.db_path_getter(), limit=20):
            self.scan_history.addItem(row)

    def refresh_integrity_report(self):
        report = database_integrity_report(self.db_path_getter())
        self.integrity_report.setPlainText("\n".join(report["lines"]))
