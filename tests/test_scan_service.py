import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pyside_app.config import DEFAULT_DB
from pyside_app.settings import initial_database_path, load_app_settings, save_app_settings
from scan_service import scan_folder_to_database, scan_history_rows, scan_summary_lines


class ScanServiceTests(unittest.TestCase):
    def test_scan_folder_discovers_hashes_and_detects_duplicates(self):
        with tempfile.TemporaryDirectory() as root:
            db = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
            db_path = db.name
            db.close()
            try:
                root_path = Path(root)
                (root_path / "one.txt").write_bytes(b"same-content")
                (root_path / "two.txt").write_bytes(b"same-content")
                (root_path / "three.txt").write_bytes(b"different")

                stats = scan_folder_to_database(db_path, root)

                self.assertEqual(stats["discovered"], 3)
                self.assertEqual(stats["new"], 3)
                self.assertEqual(stats["hashed"], 3)
                self.assertEqual(stats["errors"], 0)
                self.assertEqual(stats["duplicate_groups"], 1)
                self.assertEqual(stats["duplicate_files"], 2)
                self.assertIn(Path(stats["current_path"]).name, {"one.txt", "two.txt", "three.txt"})
                self.assertEqual(stats["current_folder"], root)

                conn = sqlite3.connect(db_path)
                try:
                    total = conn.execute("SELECT COUNT(*) FROM archivos").fetchone()[0]
                    groups = conn.execute("SELECT COUNT(DISTINCT grupo_id) FROM duplicados").fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(total, 3)
                self.assertEqual(groups, 1)

                repeat_stats = scan_folder_to_database(db_path, root)
                self.assertEqual(repeat_stats["new"], 0)
                self.assertEqual(repeat_stats["unchanged"], 3)

                history = scan_history_rows(db_path)
                self.assertEqual(len(history), 2)
                self.assertIn("complete", history[0])
                self.assertIn("3 files", history[0])
                self.assertIn(root, history[0])

                summary = scan_summary_lines(stats)
                self.assertIn("Status: Scan complete", summary)
                self.assertIn("Duplicate files: 2", summary)
            finally:
                os.unlink(db_path)

    def test_scan_folder_can_cancel_with_partial_results(self):
        with tempfile.TemporaryDirectory() as root:
            db = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
            db_path = db.name
            db.close()
            try:
                root_path = Path(root)
                for index in range(5):
                    (root_path / f"{index}.txt").write_bytes(f"content-{index}".encode("ascii"))

                calls = {"count": 0}

                def should_cancel():
                    calls["count"] += 1
                    return calls["count"] > 3

                stats = scan_folder_to_database(db_path, root, should_cancel=should_cancel)

                self.assertTrue(stats["cancelled"])
                self.assertEqual(stats["discovered"], 3)
                self.assertEqual(stats["duplicate_groups"], 0)
                self.assertTrue(stats["current_path"].endswith("2.txt"))
                conn = sqlite3.connect(db_path)
                try:
                    total = conn.execute("SELECT COUNT(*) FROM archivos").fetchone()[0]
                    notes = conn.execute("SELECT notas FROM escaneos").fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(total, 3)
                self.assertIn("cancelled=1", notes)

                history = scan_history_rows(db_path)
                self.assertEqual(len(history), 1)
                self.assertIn("cancelled", history[0])
                self.assertIn(root, history[0])

                summary = scan_summary_lines(stats)
                self.assertIn("Status: Scan cancelled", summary)
            finally:
                os.unlink(db_path)

    def test_app_settings_round_trip_and_ignore_invalid_json(self):
        with tempfile.TemporaryDirectory() as root:
            settings_path = Path(root) / "settings.json"

            self.assertEqual(load_app_settings(settings_path), {})
            save_app_settings({"last_scan_folder": root}, settings_path)
            self.assertEqual(load_app_settings(settings_path)["last_scan_folder"], root)

            settings_path.write_text("{invalid", encoding="utf-8")
            self.assertEqual(load_app_settings(settings_path), {})

    def test_initial_database_path_prefers_cli_then_saved_then_default(self):
        with tempfile.TemporaryDirectory() as root:
            settings_path = Path(root) / "settings.json"

            self.assertEqual(initial_database_path(settings_path=settings_path), DEFAULT_DB)
            save_app_settings({"db_path": r"C:\music\saved.sqlite"}, settings_path)
            self.assertEqual(initial_database_path(settings_path=settings_path), r"C:\music\saved.sqlite")
            self.assertEqual(
                initial_database_path(r"C:\music\cli.sqlite", settings_path=settings_path),
                r"C:\music\cli.sqlite",
            )


if __name__ == "__main__":
    unittest.main()
