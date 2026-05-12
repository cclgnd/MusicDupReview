from collections import defaultdict

from media_utils import normalize_name


def detect_duplicates(conn):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM duplicados")
    group_id = 0
    total = 0

    cursor.execute("""
        SELECT md5 FROM archivos
        WHERE md5 IS NOT NULL AND md5 <> ''
        GROUP BY md5 HAVING COUNT(*) > 1
    """)
    for (md5,) in cursor.fetchall():
        group_id += 1
        cursor.execute("SELECT id FROM archivos WHERE md5=?", (md5,))
        for (file_id,) in cursor.fetchall():
            _insert_duplicate(cursor, group_id, file_id, "md5", 1.0)
            total += 1

    cursor.execute("SELECT archivo_id FROM duplicados")
    used = {row[0] for row in cursor.fetchall()}
    cursor.execute("""
        SELECT audio_md5 FROM archivos
        WHERE audio_md5 IS NOT NULL AND audio_md5 <> ''
        GROUP BY audio_md5 HAVING COUNT(*) > 1
    """)
    for (audio_md5,) in cursor.fetchall():
        cursor.execute("SELECT id FROM archivos WHERE audio_md5=?", (audio_md5,))
        ids = [row[0] for row in cursor.fetchall() if row[0] not in used]
        if len(ids) > 1:
            group_id += 1
            for file_id in ids:
                _insert_duplicate(cursor, group_id, file_id, "audio_md5", 1.0)
                used.add(file_id)
                total += 1

    cursor.execute("SELECT archivo_id FROM duplicados")
    used = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT lower(nombre), COUNT(*) FROM archivos GROUP BY lower(nombre) HAVING COUNT(*) > 1")
    for name_key, _count in cursor.fetchall():
        cursor.execute("SELECT id FROM archivos WHERE lower(nombre)=?", (name_key,))
        ids = [row[0] for row in cursor.fetchall() if row[0] not in used]
        if len(ids) > 1:
            group_id += 1
            for file_id in ids:
                _insert_duplicate(cursor, group_id, file_id, "nombre_identico", 1.0)
                used.add(file_id)
                total += 1

    cursor.execute("SELECT archivo_id FROM duplicados")
    used = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT id, nombre, tamano FROM archivos")
    normalized_size = defaultdict(list)
    for file_id, name, size in cursor.fetchall():
        if file_id in used:
            continue
        key = (normalize_name(name), size)
        if len(key[0]) >= 4:
            normalized_size[key].append(file_id)
    for ids in normalized_size.values():
        if len(ids) > 1:
            group_id += 1
            for file_id in ids:
                _insert_duplicate(cursor, group_id, file_id, "nombre_tamano", 0.95)
                used.add(file_id)
                total += 1

    cursor.execute("SELECT archivo_id FROM duplicados")
    used = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT id, nombre FROM archivos")
    normalized = defaultdict(list)
    for file_id, name in cursor.fetchall():
        if file_id in used:
            continue
        key = normalize_name(name)
        if len(key) >= 4:
            normalized[key].append(file_id)
    for ids in normalized.values():
        if len(ids) > 1:
            group_id += 1
            for file_id in ids:
                _insert_duplicate(cursor, group_id, file_id, "nombre_normalizado", 0.8)
                total += 1

    cursor.execute("""
        SELECT ahash FROM image_metadata
        WHERE ahash IS NOT NULL AND ahash <> ''
        GROUP BY ahash HAVING COUNT(*) > 1
    """)
    for (ahash,) in cursor.fetchall():
        cursor.execute("""
            SELECT im.archivo_id FROM image_metadata im
            JOIN archivos a ON a.id = im.archivo_id
            WHERE im.ahash = ?
        """, (ahash,))
        ids = [row[0] for row in cursor.fetchall()]
        if len(ids) > 1:
            group_id += 1
            for file_id in ids:
                _insert_duplicate(cursor, group_id, file_id, "image_ahash", 0.92)
                total += 1

    conn.commit()
    return group_id, total


def add_duplicate_groups_for_new_files(conn, new_ids):
    if not new_ids:
        return 0
    cursor = conn.cursor()
    added = 0

    def next_group_id():
        cursor.execute("SELECT COALESCE(MAX(grupo_id), 0) + 1 FROM duplicados")
        return cursor.fetchone()[0]

    def ensure_group(match_type, ids, score):
        nonlocal added
        ids = sorted(set(ids))
        if len(ids) < 2:
            return
        placeholders = ",".join("?" * len(ids))
        cursor.execute(f"""
            SELECT grupo_id FROM duplicados
            WHERE tipo_match = ? AND archivo_id IN ({placeholders})
            LIMIT 1
        """, [match_type] + ids)
        row = cursor.fetchone()
        group_id = row[0] if row else next_group_id()
        for file_id in ids:
            cursor.execute("""
                SELECT 1 FROM duplicados
                WHERE grupo_id = ? AND archivo_id = ? AND tipo_match = ?
            """, (group_id, file_id, match_type))
            if cursor.fetchone():
                continue
            _insert_duplicate(cursor, group_id, file_id, match_type, score)
            added += 1

    placeholders = ",".join("?" * len(new_ids))
    cursor.execute(f"""
        SELECT id, nombre, tamano, md5, audio_md5
        FROM archivos
        WHERE id IN ({placeholders})
    """, new_ids)
    rows = [dict(row) for row in cursor.fetchall()]

    for row in rows:
        if row.get("md5"):
            cursor.execute("SELECT id FROM archivos WHERE md5 = ?", (row["md5"],))
            ensure_group("md5", [x[0] for x in cursor.fetchall()], 1.0)
        if row.get("audio_md5"):
            cursor.execute("SELECT id FROM archivos WHERE audio_md5 = ?", (row["audio_md5"],))
            ensure_group("audio_md5", [x[0] for x in cursor.fetchall()], 1.0)

        cursor.execute("SELECT id FROM archivos WHERE lower(nombre) = lower(?)", (row.get("nombre") or "",))
        ensure_group("nombre_identico", [x[0] for x in cursor.fetchall()], 1.0)

        norm = normalize_name(row.get("nombre"))
        if len(norm) >= 4:
            cursor.execute("SELECT id, nombre, tamano FROM archivos WHERE tamano = ?", (row.get("tamano"),))
            ids = [file_id for file_id, name, _size in cursor.fetchall() if normalize_name(name) == norm]
            ensure_group("nombre_tamano", ids, 0.95)

            cursor.execute("SELECT id, nombre FROM archivos")
            ids = [file_id for file_id, name in cursor.fetchall() if normalize_name(name) == norm]
            ensure_group("nombre_normalizado", ids, 0.8)

    cursor.execute(f"""
        SELECT im.ahash
        FROM image_metadata im
        WHERE im.archivo_id IN ({placeholders})
          AND im.ahash IS NOT NULL AND im.ahash <> ''
    """, new_ids)
    for (ahash,) in cursor.fetchall():
        cursor.execute("SELECT archivo_id FROM image_metadata WHERE ahash = ?", (ahash,))
        ensure_group("image_ahash", [x[0] for x in cursor.fetchall()], 0.92)

    conn.commit()
    return added


def _insert_duplicate(cursor, group_id, file_id, match_type, score):
    cursor.execute(
        "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)",
        (group_id, file_id, match_type, score),
    )
