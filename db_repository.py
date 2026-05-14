import os


def ensure_schema(conn):
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS archivos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruta TEXT UNIQUE NOT NULL,
        carpeta TEXT,
        nombre TEXT,
        extension TEXT,
        tamano INTEGER,
        fecha_mod REAL,
        md5 TEXT,
        escaneado INTEGER DEFAULT 0,
        error TEXT,
        categoria TEXT,
        oculto INTEGER DEFAULT 0,
        sistema INTEGER DEFAULT 0,
        audio_md5 TEXT
    );
    CREATE TABLE IF NOT EXISTS metadata (
        archivo_id INTEGER PRIMARY KEY,
        artista TEXT,
        titulo TEXT,
        album TEXT,
        ano TEXT,
        genero TEXT,
        bitrate INTEGER,
        duracion REAL,
        sample_rate INTEGER,
        canales INTEGER,
        FOREIGN KEY(archivo_id) REFERENCES archivos(id)
    );
    CREATE TABLE IF NOT EXISTS image_metadata (
        archivo_id INTEGER PRIMARY KEY,
        width INTEGER,
        height INTEGER,
        ahash TEXT,
        FOREIGN KEY(archivo_id) REFERENCES archivos(id)
    );
    CREATE TABLE IF NOT EXISTS duplicados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER NOT NULL,
        archivo_id INTEGER NOT NULL,
        tipo_match TEXT,
        score REAL
    );
    CREATE TABLE IF NOT EXISTS decisiones (
        archivo_id INTEGER PRIMARY KEY,
        decision TEXT,
        fecha REAL
    );
    CREATE TABLE IF NOT EXISTS decisiones_session_backup (
        archivo_id INTEGER PRIMARY KEY,
        decision TEXT,
        fecha REAL,
        snapshot_fecha REAL
    );
    CREATE TABLE IF NOT EXISTS escaneos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inicio REAL,
        fin REAL,
        total_archivos INTEGER,
        total_duplicados INTEGER,
        notas TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_md5 ON archivos(md5);
    CREATE INDEX IF NOT EXISTS idx_ext ON archivos(extension);
    CREATE INDEX IF NOT EXISTS idx_grupo ON duplicados(grupo_id);
    """)
    ensure_column(cursor, "archivos", "categoria", "TEXT")
    ensure_column(cursor, "archivos", "oculto", "INTEGER DEFAULT 0")
    ensure_column(cursor, "archivos", "sistema", "INTEGER DEFAULT 0")
    ensure_column(cursor, "archivos", "audio_md5", "TEXT")
    ensure_column(cursor, "duplicados", "score", "REAL")
    conn.commit()


def ensure_column(cursor, table, column, decl):
    cursor.execute(f"PRAGMA table_info({table})")
    if column not in {row[1] for row in cursor.fetchall()}:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def duplicate_extensions(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT COALESCE(a.extension,'') AS ext
        FROM duplicados d
        JOIN archivos a ON a.id = d.archivo_id
        WHERE COALESCE(a.extension,'') <> ''
        ORDER BY ext
    """)
    return [row[0] for row in cursor.fetchall()]


def duplicate_group_ids(conn, match_filter="all", extension_filter="ALL", search_text="", group_sort="group_id"):
    cursor = conn.cursor()
    where = ["d.tipo_match <> 'image_size'"]
    params = []
    if match_filter == "nombre_normalizado":
        where.append("d.tipo_match IN ('nombre_normalizado','nombre_exacto')")
    elif match_filter != "all":
        where.append("d.tipo_match = ?")
        params.append(match_filter)
    if extension_filter != "ALL":
        where.append("""d.grupo_id IN (
            SELECT d_ext.grupo_id FROM duplicados d_ext
            JOIN archivos a_ext ON a_ext.id = d_ext.archivo_id
            WHERE a_ext.extension = ?
            GROUP BY d_ext.grupo_id
            HAVING COUNT(*) >= 2
        )""")
        params.append(extension_filter)
    if search_text:
        where.append("""d.grupo_id IN (
            SELECT d3.grupo_id FROM duplicados d3
            JOIN archivos a3 ON a3.id = d3.archivo_id
            WHERE a3.ruta LIKE ?
        )""")
        params.append(f"%{search_text}%")

    sql = """SELECT d.grupo_id,
                    MAX(a.tamano) as max_size,
                    MIN(lower(a.nombre)) as group_name,
                    MAX(a.fecha_mod) as newest
             FROM duplicados d JOIN archivos a ON a.id = d.archivo_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY d.grupo_id"
    if group_sort == "biggest file":
        sql += " ORDER BY max_size DESC, d.grupo_id"
    elif group_sort == "smallest file":
        sql += " ORDER BY max_size ASC, d.grupo_id"
    elif group_sort == "name":
        sql += " ORDER BY group_name, d.grupo_id"
    elif group_sort == "name desc":
        sql += " ORDER BY group_name DESC, d.grupo_id"
    elif group_sort == "date":
        sql += " ORDER BY newest DESC, d.grupo_id"
    else:
        sql += " ORDER BY d.grupo_id"
    cursor.execute(sql, params)
    return [row[0] for row in cursor.fetchall()]


def all_duplicate_group_ids(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT grupo_id
        FROM duplicados
        WHERE tipo_match <> 'image_size'
        ORDER BY grupo_id
    """)
    return [row[0] for row in cursor.fetchall()]


def group_has_missing_or_deleted(conn, group_id, path_exists=os.path.exists):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.ruta, COALESCE(de.decision,'') as decision
        FROM duplicados d
        JOIN archivos a ON a.id = d.archivo_id
        LEFT JOIN decisiones de ON de.archivo_id = a.id
        WHERE d.grupo_id = ?
    """, (group_id,))
    for path, decision in cursor.fetchall():
        if decision in ("deleted", "missing") or not path_exists(path):
            return True
    return False


def filtered_duplicate_totals(conn, group_ids):
    if not group_ids:
        return 0, 0
    cursor = conn.cursor()
    count = 0
    total_size = 0
    chunk_size = 500
    for index in range(0, len(group_ids), chunk_size):
        chunk = group_ids[index:index + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        cursor.execute(f"""
            SELECT COUNT(*), COALESCE(SUM(a.tamano), 0)
            FROM duplicados d
            JOIN archivos a ON a.id = d.archivo_id
            WHERE d.grupo_id IN ({placeholders})
        """, list(chunk))
        rows, size = cursor.fetchone()
        count += rows or 0
        total_size += size or 0
    return count, total_size


def duplicate_group_rows(conn, group_id, row_sort="hash"):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.ruta, a.nombre, a.carpeta, a.extension, a.categoria,
               a.tamano, a.md5, a.audio_md5,
               a.fecha_mod,
               m.bitrate, m.duracion,
               d.grupo_id,
               d.tipo_match, d.score, COALESCE(de.decision,'') as decision
        FROM duplicados d
        JOIN archivos a ON a.id = d.archivo_id
        LEFT JOIN metadata m ON m.archivo_id = a.id
        LEFT JOIN decisiones de ON de.archivo_id = a.id
        WHERE d.grupo_id = ?
    """ + row_order_clause(row_sort), (group_id,))
    return [dict(row) for row in cursor.fetchall()]


def duplicate_groups_for_ids(conn, group_ids, row_sort="hash"):
    groups = []
    for group_id in group_ids:
        rows = duplicate_group_rows(conn, group_id, row_sort)
        if len(rows) >= 2:
            groups.append(rows)
    return groups


def group_ids_for_file_ids(conn, file_ids):
    if not file_ids:
        return []
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(file_ids))
    cursor.execute(f"SELECT DISTINCT grupo_id FROM duplicados WHERE archivo_id IN ({placeholders})", list(file_ids))
    return [row[0] for row in cursor.fetchall()]


def rows_marked_for_trash(conn, scope, group_ids=None):
    cursor = conn.cursor()
    if scope == "selected_groups":
        group_ids = group_ids or []
        if not group_ids:
            return []
        placeholders = ",".join("?" * len(group_ids))
        cursor.execute(f"""
            SELECT a.id, a.ruta, a.nombre, a.carpeta
            FROM duplicados d
            JOIN archivos a ON a.id = d.archivo_id
            JOIN decisiones de ON de.archivo_id = a.id
            WHERE d.grupo_id IN ({placeholders})
              AND de.decision = 'delete'
        """, list(group_ids))
    else:
        cursor.execute("""
            SELECT a.id, a.ruta, a.nombre, a.carpeta
            FROM archivos a
            JOIN decisiones de ON de.archivo_id = a.id
            WHERE de.decision = 'delete'
        """)
    return [dict(row) for row in cursor.fetchall()]


def create_folder_clone_group(conn, file_ids):
    if not file_ids:
        return None, []
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(file_ids))
    cursor.execute(f"SELECT DISTINCT grupo_id FROM duplicados WHERE archivo_id IN ({placeholders})", list(file_ids))
    affected_groups = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT COALESCE(MAX(grupo_id), 0) + 1 FROM duplicados")
    new_group_id = cursor.fetchone()[0]
    cursor.execute(f"DELETE FROM duplicados WHERE archivo_id IN ({placeholders})", list(file_ids))
    for file_id in file_ids:
        cursor.execute(
            "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)",
            (new_group_id, file_id, "audio_md5", 1.0),
        )

    if affected_groups:
        placeholders = ",".join("?" * len(affected_groups))
        cursor.execute(f"""
            DELETE FROM duplicados
            WHERE grupo_id IN ({placeholders})
              AND grupo_id IN (
                  SELECT grupo_id FROM duplicados
                  GROUP BY grupo_id
                  HAVING COUNT(*) < 2
              )
        """, affected_groups)

    conn.commit()
    return new_group_id, affected_groups


def row_order_clause(row_sort):
    if row_sort == "same_file_hash":
        return """
        ORDER BY
            CASE
                WHEN COALESCE(a.md5, '') = '' THEN 2
                WHEN (
                    SELECT COUNT(*)
                    FROM duplicados d2
                    JOIN archivos a2 ON a2.id = d2.archivo_id
                    WHERE d2.grupo_id = d.grupo_id
                      AND COALESCE(a2.md5, '') = COALESCE(a.md5, '')
                ) > 1 THEN 0
                ELSE 1
            END,
            COALESCE(a.md5, ''),
            a.tamano DESC,
            a.ruta
        """
    if row_sort == "same_audio_hash":
        return """
        ORDER BY
            CASE
                WHEN COALESCE(a.audio_md5, '') = '' THEN 2
                WHEN (
                    SELECT COUNT(*)
                    FROM duplicados d2
                    JOIN archivos a2 ON a2.id = d2.archivo_id
                    WHERE d2.grupo_id = d.grupo_id
                      AND COALESCE(a2.audio_md5, '') = COALESCE(a.audio_md5, '')
                ) > 1 THEN 0
                ELSE 1
            END,
            COALESCE(a.audio_md5, ''),
            a.tamano DESC,
            a.ruta
        """
    if row_sort == "biggest file":
        return " ORDER BY a.tamano DESC, a.ruta"
    if row_sort == "smallest file":
        return " ORDER BY a.tamano ASC, a.ruta"
    if row_sort == "longest path":
        return " ORDER BY LENGTH(a.ruta) DESC, a.ruta"
    if row_sort == "shortest path":
        return " ORDER BY LENGTH(a.ruta) ASC, a.ruta"
    if row_sort == "file name":
        return " ORDER BY lower(a.nombre), a.ruta"
    if row_sort == "extension":
        return " ORDER BY a.extension, lower(a.nombre), a.ruta"
    return " ORDER BY COALESCE(a.md5,''), COALESCE(a.audio_md5,''), a.extension, a.tamano DESC, a.ruta"
