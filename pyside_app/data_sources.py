import os
from contextlib import closing

from db_repository import duplicate_group_ids, duplicate_group_rows
from db_repository import duplicate_extensions as db_duplicate_extensions
from pyside_app.db import open_conn
from pyside_app.formatting import format_bytes


def duplicate_extension_values(db_path):
    if not os.path.exists(db_path):
        return []

    with closing(open_conn(db_path)) as conn:
        return db_duplicate_extensions(conn)


def file_extension_values(db_path):
    if not os.path.exists(db_path):
        return []
    with closing(open_conn(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT COALESCE(extension, '') AS ext
            FROM archivos
            WHERE COALESCE(extension, '') <> ''
            ORDER BY ext
        """)
        return [row[0] for row in cursor.fetchall()]


def all_file_rows(db_path, extension_filter="ALL", search_text="", sort_value="name", limit=500):
    if not os.path.exists(db_path):
        return []

    where = []
    params = []
    if extension_filter != "ALL":
        where.append("a.extension = ?")
        params.append(extension_filter)
    if search_text.strip():
        where.append("a.ruta LIKE ?")
        params.append(f"%{search_text.strip()}%")

    order = {
        "biggest file": "a.tamano DESC, lower(a.nombre), a.id",
        "smallest file": "a.tamano ASC, lower(a.nombre), a.id",
        "name": "lower(a.nombre), a.id",
        "name desc": "lower(a.nombre) DESC, a.id",
        "date": "a.fecha_mod DESC, lower(a.nombre), a.id",
        "same_file_hash": "COALESCE(a.md5, ''), lower(a.nombre), a.id",
        "same_audio_hash": "COALESCE(a.audio_md5, ''), lower(a.nombre), a.id",
    }.get(sort_value, "lower(a.nombre), a.id")

    sql = """
        SELECT a.id, a.ruta, a.nombre, a.carpeta, a.extension, a.categoria,
               a.tamano, a.md5, a.audio_md5, a.fecha_mod,
               m.bitrate, m.duracion,
               NULL AS grupo_id,
               'all' AS tipo_match,
               NULL AS score,
               COALESCE(de.decision,'') AS decision
        FROM archivos a
        LEFT JOIN metadata m ON m.archivo_id = a.id
        LEFT JOIN decisiones de ON de.archivo_id = a.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order} LIMIT {max(0, int(limit))}"

    with closing(open_conn(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


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
