from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from database_maintenance import verify_database_files
from scan_service import scan_folder_to_database


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
    def __init__(self, db_path_getter, database_changed=None):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.database_changed = database_changed
        self.worker = None
        self.scan_worker = None
        self.status = QLabel("Ready")
        self.scan_detail = QLabel("")
        self.scan_detail.setWordWrap(True)
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.backups = QListWidget()
        self.scan_button = QPushButton("Scan Folder...")
        self.scan_button.clicked.connect(self.scan_folder)
        self.cancel_scan_button = QPushButton("Cancel Scan")
        self.cancel_scan_button.setEnabled(False)
        self.cancel_scan_button.clicked.connect(self.cancel_scan)
        check = QPushButton("Check Files Now")
        check.clicked.connect(self.check_files)
        backup = QPushButton("Backup Current Database")
        backup.clicked.connect(self.backup_database)
        refresh_backups = QPushButton("Refresh Backup List")
        refresh_backups.clicked.connect(self.refresh_backups)

        scan_actions = QHBoxLayout()
        scan_actions.addWidget(self.scan_button)
        scan_actions.addWidget(self.cancel_scan_button)

        layout = QVBoxLayout(self)
        layout.addLayout(scan_actions)
        layout.addWidget(check)
        layout.addWidget(backup)
        layout.addWidget(refresh_backups)
        layout.addWidget(self.scan_progress)
        layout.addWidget(self.scan_detail)
        layout.addWidget(QLabel("Backups"))
        layout.addWidget(self.backups, 1)
        layout.addWidget(QLabel("Pending: recent searches, re-unify files, integrity report."))
        layout.addWidget(self.status)
        self.refresh_backups()

    def scan_folder(self):
        if self.scan_worker and self.scan_worker.isRunning():
            QMessageBox.information(self, "Scan folder", "A folder scan is already running.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Scan music folder")
        if not folder:
            return
        db_path = self.db_path_getter()
        self.status.setText(f"Scanning folder in background: {folder}")
        self.scan_detail.setText(folder)
        self.scan_progress.setRange(0, 0)
        self.scan_progress.setVisible(True)
        self.scan_button.setEnabled(False)
        self.cancel_scan_button.setEnabled(True)
        self.scan_worker = FolderScanWorker(db_path, folder)
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
        self.status.setText(
            f"Scanning... {stats['discovered']:,} files seen, {stats['new']:,} new, {stats['updated']:,} updated"
        )
        current = stats.get("current_path") or stats.get("current_folder") or stats.get("root") or ""
        self.scan_detail.setText(current)

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
        if self.database_changed:
            self.database_changed()
        QMessageBox.information(
            self,
            title,
            "\n".join([
                f"Folder: {stats['root']}",
                f"Status: {title}",
                f"Files found: {stats['discovered']:,}",
                f"New files: {stats['new']:,}",
                f"Updated files: {stats['updated']:,}",
                f"Unchanged files: {stats['unchanged']:,}",
                f"Hash errors: {stats['errors']:,}",
                f"Duplicate groups: {stats['duplicate_groups']:,}",
                f"Duplicate files: {stats['duplicate_files']:,}",
                f"Elapsed: {stats['elapsed_seconds']:.1f}s",
            ]),
        )

    def _scan_failed(self, message):
        self.scan_button.setEnabled(True)
        self.cancel_scan_button.setEnabled(False)
        self.scan_progress.setVisible(False)
        self.status.setText("Scan failed")
        self.scan_detail.setText("")
        QMessageBox.critical(self, "Scan folder", message)

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
