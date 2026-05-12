import os
import sqlite3
import time
from pathlib import Path

from duplicate_detection import add_duplicate_groups_for_new_files
from media_utils import audio_md5_file, category_for_extension, image_fingerprint, md5_file


def verify_database_files(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, ruta, carpeta, tamano, fecha_mod FROM archivos")
    rows = [dict(row) for row in cursor.fetchall()]
    known_paths = {row["ruta"] for row in rows}
    roots = scan_roots_for_connection(conn)
    use_audio_md5 = connection_uses_audio_md5(conn)
    folders = roots or {
        row["carpeta"] for row in rows
        if row.get("carpeta") and os.path.isdir(row.get("carpeta"))
    }
    existing = missing = changed = 0

    for row in rows:
        path = row["ruta"]
        if not os.path.exists(path):
            missing += 1
            cursor.execute(
                "INSERT OR REPLACE INTO decisiones (archivo_id, decision, fecha) VALUES (?,?,?)",
                (row["id"], "missing", time.time()),
            )
            continue
        existing += 1
        cursor.execute("DELETE FROM decisiones WHERE archivo_id=? AND decision='missing'", (row["id"],))

    new_files = 0
    new_ids = []
    known_folders = {
        row["carpeta"] for row in rows
        if row.get("carpeta") and os.path.isdir(row.get("carpeta"))
    }
    scan_folders = known_folders or folders
    for folder in scan_folders:
        try:
            names = os.listdir(folder)
        except Exception:
            continue
        for name in names:
            path = os.path.join(folder, name)
            if not os.path.isfile(path) or path in known_paths:
                continue
            new_files += 1
            try:
                stat = os.stat(path)
                ext = Path(path).suffix.lower()
                category = category_for_extension(ext)
                file_md5 = md5_file(path)
                audio_md5 = audio_md5_file(path, ext) if use_audio_md5 and category == "audio" else None
                cursor.execute("""
                    INSERT INTO archivos
                    (ruta, carpeta, nombre, extension, tamano, fecha_mod, md5, audio_md5, escaneado, categoria)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (path, folder, name, ext, stat.st_size, stat.st_mtime, file_md5, audio_md5, 1, category))
                file_id = cursor.lastrowid
                new_ids.append(file_id)
                known_paths.add(path)
                if category == "imagen":
                    width, height, ahash = image_fingerprint(path)
                    cursor.execute("""
                        INSERT OR REPLACE INTO image_metadata (archivo_id, width, height, ahash)
                        VALUES (?,?,?,?)
                    """, (file_id, width, height, ahash))
            except Exception:
                continue

    conn.commit()
    duplicates = add_duplicate_groups_for_new_files(conn, new_ids) if new_ids else 0
    conn.close()
    return {
        "existing": existing,
        "missing": missing,
        "changed": changed,
        "new": new_files,
        "duplicates": duplicates,
    }


def scan_roots_for_connection(conn):
    roots = set()
    try:
        for (notes,) in conn.execute("SELECT notas FROM escaneos WHERE notas LIKE 'root=%'"):
            root = (notes or "")[5:].split(";")[0]
            if root and os.path.isdir(root):
                roots.add(root)
    except Exception:
        pass
    return roots


def connection_uses_audio_md5(conn):
    try:
        for (_notes,) in conn.execute("SELECT notas FROM escaneos WHERE notas LIKE '%audio_md5=1%'"):
            return True
        row = conn.execute("""
            SELECT 1 FROM archivos
            WHERE audio_md5 IS NOT NULL AND audio_md5 <> ''
            LIMIT 1
        """).fetchone()
        return bool(row)
    except Exception:
        return False
