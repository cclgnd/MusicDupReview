import os
from contextlib import closing

from db_repository import duplicate_group_ids, duplicate_group_rows
from pyside_app.db import open_conn
from pyside_app.formatting import format_bytes


def duplicate_group_summaries(
    db_path,
    match_filter="all",
    extension_filter="ALL",
    search_text="",
    group_sort="group_id",
    limit=500,
):
    if not os.path.exists(db_path):
        return [], [], 0, 0

    with closing(open_conn(db_path)) as conn:
        limit = max(0, int(limit))
        group_ids = duplicate_group_ids(
            conn,
            match_filter=match_filter,
            extension_filter=extension_filter,
            search_text=search_text,
            group_sort=group_sort,
        )
        visible_group_ids = group_ids[:limit]
        summaries = []
        total_files = 0
        for group_id in visible_group_ids:
            rows = duplicate_group_rows(conn, group_id, "hash")
            if len(rows) < 2:
                continue
            total_files += len(rows)
            sizes = [row["tamano"] or 0 for row in rows]
            largest = max(sizes)
            recoverable = sum(sizes) - largest
            summaries.append([
                group_id,
                str(rows[0].get("tipo_match") or ""),
                len(rows),
                format_bytes(largest),
                format_bytes(recoverable),
                rows[0].get("ruta") or "",
            ])
        return group_ids, visible_group_ids, summaries, total_files


def file_explorer_order(contiguous_hash_mode):
    if contiguous_hash_mode:
        return "COALESCE(a.audio_md5, a.md5, ''), a.carpeta, a.ruta"
    return "lower(a.nombre)"


def file_explorer_rows(db_path, search_text="", contiguous_hash_mode=False, limit=500):
    if not os.path.exists(db_path):
        return []

    limit = max(0, int(limit))
    search_text = search_text.strip()
    with closing(open_conn(db_path)) as conn:
        cursor = conn.cursor()
        if search_text:
            cursor.execute("""
                SELECT a.nombre, a.extension, a.tamano, a.carpeta, a.ruta, a.md5, a.audio_md5,
                       COALESCE(d.decision,'') AS decision
                FROM archivos a
                LEFT JOIN decisiones d ON d.archivo_id = a.id
                WHERE a.ruta LIKE ?
                ORDER BY """ + file_explorer_order(contiguous_hash_mode) + f"""
                LIMIT {int(limit)}
            """, (f"%{search_text}%",))
        else:
            cursor.execute("""
                SELECT a.nombre, a.extension, a.tamano, a.carpeta, a.ruta, a.md5, a.audio_md5,
                       COALESCE(d.decision,'') AS decision
                FROM archivos a
                LEFT JOIN decisiones d ON d.archivo_id = a.id
                ORDER BY """ + file_explorer_order(contiguous_hash_mode) + f"""
                LIMIT {int(limit)}
            """)

        previous_hash = None
        rows = []
        for row in cursor.fetchall():
            current_hash = row["audio_md5"] or row["md5"] or ""
            row_data = dict(row)
            row_data["hash_link"] = "same as previous" if current_hash and current_hash == previous_hash else ""
            rows.append(row_data)
            previous_hash = current_hash
        return rows
