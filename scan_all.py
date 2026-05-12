#!/usr/bin/env python3
"""
Escaneo COMPLETO: TODOS archivos en D:\\cdu\\music, incluidos ocultos.
- Anade columnas categoria (audio/imagen/lista/info/otro), oculto, sistema.
- Hashea MD5 todos.
- Detecta duplicados por: md5 exacto, nombre normalizado exacto, similitud >=0.90 (solo audio).
"""
import os
import stat
import hashlib
import sqlite3
import time
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("MUSIC_DUP_ROOT", os.getcwd())
DB = os.environ.get("MUSIC_DUP_DB", os.path.join(APP_DIR, "music_library.db"))
CHUNK = 1024 * 1024
HIDDEN_ATTR = 0x2
SYSTEM_ATTR = 0x4

AUDIO_EXTS = {
    ".mp3", ".flac", ".ogg", ".m4a", ".wav", ".wma", ".ape", ".mp2",
    ".aac", ".aiff", ".aif", ".opus",
    ".vgz", ".vgm", ".spc", ".psf", ".psf2", ".miniusf", ".usf",
    ".usflib", ".nsf", ".nsfe", ".gbs", ".rsn", ".mid", ".midi",
    ".mod", ".s3m", ".xm", ".it", ".sid", ".mxm", ".song",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"}
LIST_EXTS = {".m3u", ".m3u8", ".pls", ".cue", ".nml"}
INFO_EXTS = {".nfo", ".sfv", ".txt", ".log", ".rtf", ".pdf", ".doc",
             ".htm", ".html", ".mht", ".url"}
META_EXTS = {".db", ".ini", ".bak", ".peak", ".sfk", ".pkf", ".pk",
             ".cpr", ".veg", ".lnk", ".jwl", ".plc", ".ds_store",
             ".autosave", ".debug", ".new"}


def categoria(ext):
    e = ext.lower()
    if e in AUDIO_EXTS:
        return "audio"
    if e in IMAGE_EXTS:
        return "imagen"
    if e in LIST_EXTS:
        return "lista"
    if e in INFO_EXTS:
        return "info"
    if e in META_EXTS:
        return "meta"
    return "otro"


def md5_file(path, timeout_size=500_000_000):
    """MD5 con limite tamano para evitar bloqueos eternos."""
    try:
        sz = os.path.getsize(path)
        if sz > timeout_size:
            return None  # marcar como skip_size
    except Exception:
        return None
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(CHUNK), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
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
    CREATE INDEX IF NOT EXISTS idx_ext ON archivos(extension);

    CREATE TABLE IF NOT EXISTS duplicados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER NOT NULL,
        archivo_id INTEGER NOT NULL,
        tipo_match TEXT,
        score REAL
    );
    CREATE INDEX IF NOT EXISTS idx_grupo ON duplicados(grupo_id);
    """)
    # columnas adicionales (ignora error si ya existen)
    for col, typ in [("categoria","TEXT"), ("oculto","INTEGER DEFAULT 0"),
                     ("sistema","INTEGER DEFAULT 0")]:
        try:
            c.execute(f"ALTER TABLE archivos ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def descubrir(conn):
    c = conn.cursor()
    nuevos = 0
    actualizados = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            try:
                st = os.stat(full)
                # detectar oculto/sistema (windows attrs)
                attrs = 0
                try:
                    attrs = os.stat(full).st_file_attributes  # type: ignore
                except Exception:
                    pass
                oculto = 1 if attrs & HIDDEN_ATTR else 0
                sistema = 1 if attrs & SYSTEM_ATTR else 0
                cat = categoria(ext)
                c.execute("SELECT id FROM archivos WHERE ruta=?", (full,))
                row = c.fetchone()
                if row is None:
                    c.execute(
                        "INSERT INTO archivos (ruta, carpeta, nombre, extension, tamano, fecha_mod, categoria, oculto, sistema) VALUES (?,?,?,?,?,?,?,?,?)",
                        (full, dirpath, fn, ext, st.st_size, st.st_mtime, cat, oculto, sistema),
                    )
                    nuevos += 1
                else:
                    c.execute(
                        "UPDATE archivos SET categoria=?, oculto=?, sistema=?, tamano=?, fecha_mod=? WHERE id=?",
                        (cat, oculto, sistema, st.st_size, st.st_mtime, row[0]),
                    )
                    actualizados += 1
            except Exception:
                pass
        if (nuevos + actualizados) % 2000 == 0:
            conn.commit()
    conn.commit()
    return nuevos, actualizados


def hashear(conn):
    c = conn.cursor()
    c.execute("SELECT id, ruta, tamano FROM archivos WHERE escaneado=0 OR md5 IS NULL")
    rows = c.fetchall()
    total = len(rows)
    if total == 0:
        return 0, 0, 0
    ok = err = skip = 0
    t0 = time.time()
    for i, (fid, ruta, tam) in enumerate(rows, 1):
        h = md5_file(ruta)
        if h is None:
            try:
                if os.path.getsize(ruta) > 500_000_000:
                    c.execute("UPDATE archivos SET escaneado=1, error=? WHERE id=?", ("skip_too_big", fid))
                    skip += 1
                else:
                    c.execute("UPDATE archivos SET escaneado=1, error=? WHERE id=?", ("read_error", fid))
                    err += 1
            except Exception:
                c.execute("UPDATE archivos SET escaneado=1, error=? WHERE id=?", ("stat_error", fid))
                err += 1
        else:
            c.execute("UPDATE archivos SET md5=?, escaneado=1, error=NULL WHERE id=?", (h, fid))
            ok += 1
        if i % 500 == 0:
            conn.commit()
    conn.commit()
    return ok, err, skip


def normalizar(nombre):
    s = os.path.splitext(nombre)[0].lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\b(19|20)\d{2}\b", "", s)
    s = re.sub(r"\b\d{1,3}\s*kbps\b", "", s)
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"^\d{1,3}\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detectar(conn):
    c = conn.cursor()
    c.execute("DELETE FROM duplicados")
    grupo = 0

    # MD5 exacto
    c.execute("SELECT md5, COUNT(*) FROM archivos WHERE md5 IS NOT NULL AND md5<>'' GROUP BY md5 HAVING COUNT(*)>1")
    for md5, _ in c.fetchall():
        grupo += 1
        c.execute("SELECT id FROM archivos WHERE md5=?", (md5,))
        for (aid,) in c.fetchall():
            c.execute("INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)", (grupo, aid, "md5", 1.0))
    g_md5 = grupo

    # nombre exacto normalizado (solo categoria audio)
    c.execute("SELECT archivo_id FROM duplicados")
    ya = {r[0] for r in c.fetchall()}
    c.execute("SELECT id, nombre FROM archivos WHERE categoria='audio'")
    norm = defaultdict(list)
    for aid, nombre in c.fetchall():
        if aid in ya:
            continue
        n = normalizar(nombre)
        if len(n) >= 4:
            norm[n].append(aid)
    for n, ids in norm.items():
        if len(ids) > 1:
            grupo += 1
            for aid in ids:
                c.execute("INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)", (grupo, aid, "nombre_exacto", 1.0))
    g_nombre = grupo - g_md5

    # similitud >=0.90 (solo audio, no agrupados)
    c.execute("SELECT archivo_id FROM duplicados")
    ya = {r[0] for r in c.fetchall()}
    c.execute("SELECT id, nombre FROM archivos WHERE categoria='audio'")
    pendientes = [(aid, normalizar(nombre)) for aid, nombre in c.fetchall() if aid not in ya]
    pendientes = [(aid, n) for aid, n in pendientes if len(n) >= 6]
    buckets = defaultdict(list)
    for aid, n in pendientes:
        buckets[(n[:4], len(n)//5)].append((aid, n))
    asignados = set()
    for items in buckets.values():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            aid_i, n_i = items[i]
            if aid_i in asignados:
                continue
            grupo_actual = []
            for j in range(i+1, len(items)):
                aid_j, n_j = items[j]
                if aid_j in asignados:
                    continue
                ratio = SequenceMatcher(None, n_i, n_j).ratio()
                if ratio >= 0.90:
                    grupo_actual.append((aid_j, ratio))
            if grupo_actual:
                grupo += 1
                asignados.add(aid_i)
                c.execute("INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)", (grupo, aid_i, "similar", 1.0))
                for aid_j, ratio in grupo_actual:
                    asignados.add(aid_j)
                    c.execute("INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)", (grupo, aid_j, "similar", ratio))
    g_sim = grupo - g_md5 - g_nombre

    conn.commit()
    return g_md5, g_nombre, g_sim


def main():
    print(f"DB: {DB}")
    print(f"ROOT: {ROOT}")
    conn = sqlite3.connect(DB)
    init_db(conn)
    print("Descubriendo TODOS archivos (incluidos ocultos)...")
    n, u = descubrir(conn)
    print(f"  nuevos: {n}  actualizados: {u}")
    print("Hash pendientes...")
    ok, err, skip = hashear(conn)
    print(f"  ok={ok} err={err} skip={skip}")
    print("Detectando duplicados...")
    g_md5, g_nombre, g_sim = detectar(conn)
    print(f"  md5={g_md5}  nombre={g_nombre}  similar={g_sim}")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM archivos")
    print("Total archivos DB:", c.fetchone()[0])
    c.execute("SELECT categoria, COUNT(*) FROM archivos GROUP BY categoria ORDER BY 2 DESC")
    print("Por categoria:", c.fetchall())
    c.execute("SELECT oculto, COUNT(*) FROM archivos GROUP BY oculto")
    print("Ocultos:", c.fetchall())
    conn.close()


if __name__ == "__main__":
    main()
