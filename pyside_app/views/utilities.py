from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget

from database_maintenance import verify_database_files


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
