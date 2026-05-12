import os
import sqlite3
import tempfile
import unittest

from db_repository import ensure_schema
from duplicate_detection import detect_duplicates
from pyside_app.data_sources import duplicate_group_summaries, file_explorer_rows
from review_state import save_decision


def create_db_file():
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
    path = handle.name
    handle.close()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return path, conn


def add_file(conn, path, name, ext, size, md5=None, audio_md5=None):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO archivos (ruta, carpeta, nombre, extension, tamano, fecha_mod, md5, audio_md5, escaneado, categoria)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (path, os.path.dirname(path), name, ext, size, 1.0, md5, audio_md5, 1, "audio"))
    return cursor.lastrowid


class PySideDataSourceTests(unittest.TestCase):
    def test_duplicate_group_summaries_return_display_rows(self):
        path, conn = create_db_file()
        try:
            add_file(conn, r"C:\a\small.mp3", "small.mp3", ".mp3", 10, md5="same")
            add_file(conn, r"C:\b\large.mp3", "large.mp3", ".mp3", 30, md5="same")
            conn.commit()
            detect_duplicates(conn)
            conn.close()

            group_ids, visible_group_ids, summaries, total_files = duplicate_group_summaries(path)

            self.assertEqual(group_ids, [1])
            self.assertEqual(visible_group_ids, [1])
            self.assertEqual(total_files, 2)
            self.assertEqual(summaries[0][:5], [1, "md5", 2, "30 bytes", "10 bytes"])
        finally:
            conn.close()
            os.unlink(path)

    def test_file_explorer_rows_include_decision_and_hash_adjacency(self):
        path, conn = create_db_file()
        try:
            first_id = add_file(conn, r"C:\music\a.mp3", "a.mp3", ".mp3", 10, md5="same")
            add_file(conn, r"C:\music\b.mp3", "b.mp3", ".mp3", 11, md5="same")
            add_file(conn, r"C:\music\c.mp3", "c.mp3", ".mp3", 12, md5="other")
            conn.commit()
            save_decision(conn, first_id, "master")
            conn.close()

            rows = file_explorer_rows(path, contiguous_hash_mode=True)

            self.assertEqual([row["nombre"] for row in rows], ["c.mp3", "a.mp3", "b.mp3"])
            self.assertEqual(rows[1]["decision"], "master")
            self.assertEqual(rows[1]["hash_link"], "")
            self.assertEqual(rows[2]["hash_link"], "same as previous")
        finally:
            conn.close()
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
