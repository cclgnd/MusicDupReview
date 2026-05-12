#!/usr/bin/env python3
"""
Scan a music folder, compute MP3 MD5 hashes, and store duplicate groups in SQLite.
"""
import os
import sys
import hashlib
import sqlite3
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = os.environ.get("MUSIC_DUP_ROOT", os.getcwd())
DB = os.environ.get("MUSIC_DUP_DB", str(APP_DIR / "music_library.db"))
CHUNK = 1024 * 1024  # 1 MB


def md5_file(path):
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(CHUNK), b""):
                h.update(block)
        return h.hexdigest()
    except Exception as e:
        return None


def init_db(conn):
    c = conn.cursor()
    c.executescript("""
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
        error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_md5 ON archivos(md5);
    CREATE INDEX IF NOT EXISTS idx_carpeta ON archivos(carpeta);
    CREATE INDEX IF NOT EXISTS idx_tamano ON archivos(tamano);

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

    CREATE TABLE IF NOT EXISTS duplicados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER NOT NULL,
        archivo_id INTEGER NOT NULL,
        tipo_match TEXT,
        FOREIGN KEY(archivo_id) REFERENCES archivos(id)
    );
    CREATE INDEX IF NOT EXISTS idx_grupo ON duplicados(grupo_id);

    CREATE TABLE IF NOT EXISTS escaneos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inicio REAL,
        fin REAL,
        total_archivos INTEGER,
        total_duplicados INTEGER,
        notas TEXT
    );
    """)
    conn.commit()


def discover(conn):
    c = conn.cursor()
    print("Descubriendo archivos...")
    nuevos = 0
    for dirpath, _, filenames in os.walk(ROOT):
        for fn in filenames:
            if not fn.lower().endswith(".mp3"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
                c.execute(
                    "INSERT OR IGNORE INTO archivos (ruta, carpeta, nombre, extension, tamano, fecha_mod) VALUES (?,?,?,?,?,?)",
                    (full, dirpath, fn, ".mp3", st.st_size, st.st_mtime),
                )
                if c.rowcount:
                    nuevos += 1
            except Exception as e:
                pass
        if nuevos and nuevos % 2000 == 0:
            conn.commit()
            print(f"  {nuevos} nuevos...")
    conn.commit()
    print(f"Descubrimiento: {nuevos} archivos nuevos")


def hash_pendientes(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM archivos WHERE escaneado=0")
    total = c.fetchone()[0]
    print(f"Hash MD5 pendiente: {total} archivos")
    if total == 0:
        return
    c.execute("SELECT id, ruta FROM archivos WHERE escaneado=0")
    rows = c.fetchall()
    t0 = time.time()
    procesados = 0
    for fid, ruta in rows:
        h = md5_file(ruta)
        if h is None:
            c.execute(
                "UPDATE archivos SET escaneado=1, error=? WHERE id=?",
                ("read_error", fid),
            )
        else:
            c.execute(
                "UPDATE archivos SET md5=?, escaneado=1 WHERE id=?", (h, fid)
            )
        procesados += 1
        if procesados % 200 == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = procesados / elapsed if elapsed else 0
            eta = (total - procesados) / rate if rate else 0
            print(
                f"  {procesados}/{total}  {rate:.1f}/s  ETA {eta/60:.1f} min"
            )
    conn.commit()
    print(f"Hash completado: {procesados} en {(time.time()-t0)/60:.1f} min")


def detectar_dup(conn):
    c = conn.cursor()
    c.execute("DELETE FROM duplicados")
    c.execute(
        "SELECT md5, COUNT(*) FROM archivos WHERE md5 IS NOT NULL GROUP BY md5 HAVING COUNT(*)>1"
    )
    grupos = c.fetchall()
    grupo_id = 0
    total_arch = 0
    for md5, _ in grupos:
        grupo_id += 1
        c.execute("SELECT id FROM archivos WHERE md5=?", (md5,))
        for (aid,) in c.fetchall():
            c.execute(
                "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match) VALUES (?,?,?)",
                (grupo_id, aid, "md5"),
            )
            total_arch += 1
    conn.commit()
    return grupo_id, total_arch


def reporte(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM archivos")
    total = c.fetchone()[0]
    c.execute("SELECT SUM(tamano) FROM archivos")
    tam = c.fetchone()[0] or 0
    c.execute(
        "SELECT COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados"
    )
    grupos, arch_dup = c.fetchone()
    c.execute("""
        SELECT SUM(tamano) FROM archivos
        WHERE id IN (
            SELECT archivo_id FROM duplicados d
            WHERE archivo_id NOT IN (
                SELECT MIN(archivo_id) FROM duplicados GROUP BY grupo_id
            )
        )
    """)
    tam_recuperable = c.fetchone()[0] or 0
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Total archivos     : {total}")
    print(f"Tamano total       : {tam/1024/1024/1024:.2f} GB")
    print(f"Grupos duplicados  : {grupos}")
    print(f"Archivos duplicados: {arch_dup}")
    print(f"Espacio recuperable: {tam_recuperable/1024/1024/1024:.2f} GB")
    return total, grupos, arch_dup, tam_recuperable


def main():
    print(f"DB: {DB}")
    print(f"ROOT: {ROOT}")
    conn = sqlite3.connect(DB)
    init_db(conn)
    t0 = time.time()
    discover(conn)
    hash_pendientes(conn)
    grupos, arch_dup = detectar_dup(conn)
    total, _, _, tam_rec = reporte(conn)
    c = conn.cursor()
    c.execute(
        "INSERT INTO escaneos (inicio, fin, total_archivos, total_duplicados, notas) VALUES (?,?,?,?,?)",
        (t0, time.time(), total, arch_dup, "md5_only"),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
