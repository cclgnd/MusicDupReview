import time

TRANSIENT_DECISIONS = ("master", "protected", "delete", "ignored", "keep")


def clear_transient_decisions(conn):
    placeholders = ",".join("?" * len(TRANSIENT_DECISIONS))
    conn.execute(
        f"DELETE FROM decisiones WHERE decision IN ({placeholders})",
        TRANSIENT_DECISIONS,
    )
    conn.commit()


def save_session_snapshot(conn):
    now = time.time()
    conn.execute("DELETE FROM decisiones_session_backup")
    conn.execute(
        """
        INSERT INTO decisiones_session_backup (archivo_id, decision, fecha, snapshot_fecha)
        SELECT archivo_id, decision, fecha, ?
        FROM decisiones
        """,
        (now,),
    )
    conn.commit()


def recover_session_snapshot(conn):
    placeholders = ",".join("?" * len(TRANSIENT_DECISIONS))
    conn.execute(
        f"DELETE FROM decisiones WHERE decision IN ({placeholders})",
        TRANSIENT_DECISIONS,
    )
    cur = conn.execute(
        f"""
        INSERT OR REPLACE INTO decisiones (archivo_id, decision, fecha)
        SELECT b.archivo_id, b.decision, b.fecha
        FROM decisiones_session_backup b
        JOIN archivos a ON a.id = b.archivo_id
        WHERE b.decision IN ({placeholders})
        """,
        TRANSIENT_DECISIONS,
    )
    conn.commit()
    return cur.rowcount if cur.rowcount is not None else 0


def save_decision(conn, file_id, decision):
    if decision == "":
        conn.execute("DELETE FROM decisiones WHERE archivo_id=?", (file_id,))
    else:
        conn.execute(
            "INSERT OR REPLACE INTO decisiones (archivo_id, decision, fecha) VALUES (?,?,?)",
            (file_id, decision, 0),
        )
    conn.commit()


def save_decisions_bulk(conn, updates):
    if not updates:
        return
    for file_id, decision in updates:
        if decision == "":
            conn.execute("DELETE FROM decisiones WHERE archivo_id=?", (file_id,))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO decisiones (archivo_id, decision, fecha) VALUES (?,?,?)",
                (file_id, decision, 0),
            )
    conn.commit()
