import os
import sqlite3
import tempfile
import unittest

from db_repository import (
    create_folder_clone_group,
    duplicate_group_ids,
    ensure_schema,
    group_has_missing_or_deleted,
    rows_marked_for_trash,
)
from duplicate_detection import detect_duplicates
from review_state import save_decision
from undo_service import UndoStack


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def add_file(conn, path, name, ext, size, md5=None, audio_md5=None):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO archivos (ruta, carpeta, nombre, extension, tamano, fecha_mod, md5, audio_md5, escaneado, categoria)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (path, os.path.dirname(path), name, ext, size, 1.0, md5, audio_md5, 1, "audio"))
    return cursor.lastrowid


class ServiceTests(unittest.TestCase):
    def test_duplicate_detection_and_extension_filter(self):
        conn = make_conn()
        add_file(conn, r"C:\a\one.mp3", "one.mp3", ".mp3", 10, md5="same")
        add_file(conn, r"C:\b\two.mp3", "two.mp3", ".mp3", 11, md5="same")
        add_file(conn, r"C:\c\three.wav", "three.wav", ".wav", 12, md5="other")
        conn.commit()

        groups, rows = detect_duplicates(conn)

        self.assertEqual(groups, 1)
        self.assertEqual(rows, 2)
        self.assertEqual(len(duplicate_group_ids(conn, extension_filter=".mp3")), 1)
        self.assertEqual(duplicate_group_ids(conn, extension_filter=".wav"), [])

    def test_rows_marked_for_trash_by_scope(self):
        conn = make_conn()
        keep_id = add_file(conn, r"C:\a\keep.mp3", "keep.mp3", ".mp3", 10, md5="same")
        trash_id = add_file(conn, r"C:\b\trash.mp3", "trash.mp3", ".mp3", 11, md5="same")
        detect_duplicates(conn)
        save_decision(conn, keep_id, "master")
        save_decision(conn, trash_id, "delete")

        rows = rows_marked_for_trash(conn, "database")

        self.assertEqual([row["id"] for row in rows], [trash_id])

    def test_missing_or_deleted_group_detection(self):
        conn = make_conn()
        file_id = add_file(conn, r"C:\missing\a.mp3", "a.mp3", ".mp3", 10, md5="same")
        add_file(conn, r"C:\missing\b.mp3", "b.mp3", ".mp3", 10, md5="same")
        detect_duplicates(conn)

        self.assertTrue(group_has_missing_or_deleted(conn, 1, path_exists=lambda _path: False))
        save_decision(conn, file_id, "deleted")
        self.assertTrue(group_has_missing_or_deleted(conn, 1, path_exists=lambda _path: True))

    def test_create_folder_clone_group_replaces_group_membership(self):
        conn = make_conn()
        file_a = add_file(conn, r"C:\a\a.mp3", "a.mp3", ".mp3", 10, audio_md5="audio-1")
        file_b = add_file(conn, r"C:\b\b.mp3", "b.mp3", ".mp3", 10, audio_md5="audio-1")
        conn.execute(
            "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)",
            (7, file_a, "audio_md5", 1.0),
        )
        conn.commit()

        new_group_id, affected = create_folder_clone_group(conn, [file_a, file_b])

        self.assertEqual(affected, [7])
        rows = conn.execute(
            "SELECT archivo_id FROM duplicados WHERE grupo_id=? ORDER BY archivo_id",
            (new_group_id,),
        ).fetchall()
        self.assertEqual([row[0] for row in rows], [file_a, file_b])

    def test_undo_stack_caps_memory_and_keeps_snapshot(self):
        stack = UndoStack(maxlen=2)
        stack.push("state", [{"id": 1, "decision": "", "_missing": False, "ruta": "a"}])
        stack.push("state", [{"id": 2, "_decision_var": Var("delete"), "_missing": True, "ruta": "b"}])
        stack.push("state", [{"id": 3, "decision": "master", "_missing": False, "ruta": "c"}])

        latest = stack.pop()
        previous = stack.pop()

        self.assertEqual(latest["rows"][0]["id"], 3)
        self.assertEqual(previous["rows"][0]["id"], 2)
        self.assertFalse(stack)


if __name__ == "__main__":
    unittest.main()
