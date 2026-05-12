import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scan_service import scan_folder_to_database


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
                conn = sqlite3.connect(db_path)
                try:
                    total = conn.execute("SELECT COUNT(*) FROM archivos").fetchone()[0]
                    notes = conn.execute("SELECT notas FROM escaneos").fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(total, 3)
                self.assertIn("cancelled=1", notes)
            finally:
                os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
