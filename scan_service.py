import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from db_repository import ensure_schema
from duplicate_detection import detect_duplicates
from media_utils import IMAGE_EXTS, audio_md5_file, category_for_extension, image_fingerprint, md5_file


def scan_folder_to_database(db_path, root_path, progress_callback=None, should_cancel=None):
    root = Path(root_path)
    if not root.is_dir():
        raise ValueError(f"Folder not found: {root_path}")

    started = time.time()
    stats = {
        "root": str(root),
        "discovered": 0,
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "hashed": 0,
        "errors": 0,
        "duplicate_groups": 0,
        "duplicate_files": 0,
        "elapsed_seconds": 0.0,
        "files_per_second": 0.0,
        "cancelled": False,
        "current_path": "",
        "current_folder": "",
    }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        cursor = conn.cursor()
        for path in iter_files(root):
            if should_cancel and should_cancel():
                stats["cancelled"] = True
                break
            stats["current_path"] = str(path)
            stats["current_folder"] = str(path.parent)
            stats["discovered"] += 1
            update_scan_timing(stats, started)
            if progress_callback and stats["discovered"] % 100 == 0:
                progress_callback(dict(stats))
            try:
                file_stats = upsert_scanned_file(cursor, path)
                stats[file_stats] += 1
                if file_stats in ("new", "updated"):
                    stats["hashed"] += 1
            except Exception:
                stats["errors"] += 1
            if stats["discovered"] % 200 == 0:
                conn.commit()

        conn.commit()
        if progress_callback:
            progress_callback(dict(stats))
        if not stats["cancelled"]:
            groups, duplicate_files = detect_duplicates(conn)
            stats["duplicate_groups"] = groups
            stats["duplicate_files"] = duplicate_files
        update_scan_timing(stats, started)
        cursor.execute(
            "INSERT INTO escaneos (inicio, fin, total_archivos, total_duplicados, notas) VALUES (?,?,?,?,?)",
            (
                started,
                time.time(),
                stats["discovered"],
                stats["duplicate_files"],
                f"root={root};audio_md5=1;cancelled={int(stats['cancelled'])}",
            ),
        )
        conn.commit()
        return stats
    finally:
        conn.close()


def update_scan_timing(stats, started):
    elapsed = time.time() - started
    stats["elapsed_seconds"] = elapsed
    stats["files_per_second"] = (stats["discovered"] / elapsed) if elapsed > 0 else 0.0


def scan_summary_lines(stats):
    title = "Scan cancelled" if stats.get("cancelled") else "Scan complete"
    return [
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
        f"Rate: {stats.get('files_per_second', 0.0):.1f} files/s",
    ]


def scan_history_rows(db_path, limit=20):
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT inicio, fin, total_archivos, total_duplicados, notas
            FROM escaneos
            ORDER BY COALESCE(fin, inicio) DESC
            LIMIT ?
        """, (int(limit),))
        return [format_scan_history_row(dict(row)) for row in cursor.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def format_scan_history_row(row):
    notes = row.get("notas") or ""
    root = value_from_notes(notes, "root") or "unknown folder"
    cancelled = value_from_notes(notes, "cancelled") == "1"
    status = "cancelled" if cancelled else "complete"
    timestamp = row.get("fin") or row.get("inicio") or 0
    when = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M") if timestamp else "unknown time"
    return (
        f"{when} - {status} - {int(row.get('total_archivos') or 0):,} files, "
        f"{int(row.get('total_duplicados') or 0):,} duplicate files - {root}"
    )


def value_from_notes(notes, key):
    prefix = f"{key}="
    for part in (notes or "").split(";"):
        if part.startswith(prefix):
            return part[len(prefix):]
    return ""


def iter_files(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            yield Path(dirpath) / filename


def upsert_scanned_file(cursor, path):
    path = Path(path)
    stat = path.stat()
    full_path = str(path)
    folder = str(path.parent)
    name = path.name
    ext = path.suffix.lower()
    category = category_for_extension(ext)

    row = cursor.execute(
        "SELECT id, tamano, fecha_mod FROM archivos WHERE ruta=?",
        (full_path,),
    ).fetchone()
    unchanged = row and row["tamano"] == stat.st_size and row["fecha_mod"] == stat.st_mtime
    if unchanged:
        return "unchanged"

    file_md5 = md5_file(full_path)
    audio_md5 = audio_md5_file(full_path, ext) if category == "audio" else None
    if row:
        file_id = row["id"]
        cursor.execute("""
            UPDATE archivos
            SET carpeta=?, nombre=?, extension=?, tamano=?, fecha_mod=?, md5=?, audio_md5=?,
                escaneado=1, error=NULL, categoria=?
            WHERE id=?
        """, (folder, name, ext, stat.st_size, stat.st_mtime, file_md5, audio_md5, category, file_id))
        result = "updated"
    else:
        cursor.execute("""
            INSERT INTO archivos
            (ruta, carpeta, nombre, extension, tamano, fecha_mod, md5, audio_md5, escaneado, error, categoria)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (full_path, folder, name, ext, stat.st_size, stat.st_mtime, file_md5, audio_md5, 1, None, category))
        file_id = cursor.lastrowid
        result = "new"

    if ext in IMAGE_EXTS:
        width, height, ahash = image_fingerprint(full_path)
        cursor.execute("""
            INSERT OR REPLACE INTO image_metadata (archivo_id, width, height, ahash)
            VALUES (?,?,?,?)
        """, (file_id, width, height, ahash))
    return result
