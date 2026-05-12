"""
Compute audio-only MD5 for all MP3 files (skipping ID3v2 + ID3v1 tags).
Stores in archivos.audio_md5. Then re-detects duplicates with new layer.
"""
import os
import sqlite3
import hashlib
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("MUSIC_DUP_DB", os.path.join(APP_DIR, "music_library.db"))

conn = sqlite3.connect(DB)
c = conn.cursor()

# add column if missing
try:
    c.execute("ALTER TABLE archivos ADD COLUMN audio_md5 TEXT")
    conn.commit()
    print("Added column audio_md5")
except sqlite3.OperationalError:
    print("Column audio_md5 already exists")

c.execute("CREATE INDEX IF NOT EXISTS idx_audio_md5 ON archivos(audio_md5)")
conn.commit()


def audio_md5_mp3(path):
    """Skip ID3v2 (start) and ID3v1 (last 128 bytes if present)."""
    sz = os.path.getsize(path)
    if sz < 10:
        return None, 0
    start = 0
    end = sz
    h = hashlib.md5()
    with open(path, "rb") as f:
        head = f.read(10)
        if head[:3] == b"ID3":
            tag_size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
            start = tag_size + 10
        f.seek(sz - 128)
        if f.read(3) == b"TAG":
            end = sz - 128
        f.seek(start)
        remaining = end - start
        while remaining > 0:
            chunk = f.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest(), end - start


# get pending mp3 files
c.execute("SELECT id, ruta FROM archivos WHERE extension='.mp3' AND (audio_md5 IS NULL OR audio_md5='')")
rows = c.fetchall()
total = len(rows)
print(f"MP3 files to process: {total}")

t0 = time.time()
ok = err = 0
for i, (fid, ruta) in enumerate(rows, 1):
    try:
        h, _ = audio_md5_mp3(ruta)
        if h:
            c.execute("UPDATE archivos SET audio_md5=? WHERE id=?", (h, fid))
            ok += 1
        else:
            err += 1
    except Exception:
        err += 1
    if i % 500 == 0:
        conn.commit()
        elapsed = time.time() - t0
        rate = i / elapsed
        eta = (total - i) / rate
        print(f"  {i}/{total}  {rate:.1f}/s  ETA {eta:.0f}s")

conn.commit()
elapsed = time.time() - t0
print(f"Done: ok={ok} err={err} time={elapsed:.1f}s ({elapsed/60:.2f} min)")

# now redetect duplicates including audio_md5 layer
print("\nRedetecting duplicates with new audio_md5 layer...")
c.execute("DELETE FROM duplicados")
grupo = 0

# 1. Full MD5 exact (all files)
c.execute("SELECT md5, COUNT(*) FROM archivos WHERE md5 IS NOT NULL AND md5<>'' GROUP BY md5 HAVING COUNT(*)>1")
for md5, _ in c.fetchall():
    grupo += 1
    c.execute("SELECT id FROM archivos WHERE md5=?", (md5,))
    for (aid,) in c.fetchall():
        c.execute(
            "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)",
            (grupo, aid, "md5", 1.0),
        )
g_md5 = grupo

# 2. Audio MD5 (mp3) - same audio different tags
c.execute("SELECT archivo_id FROM duplicados")
used = {r[0] for r in c.fetchall()}
c.execute("SELECT audio_md5, COUNT(*) FROM archivos WHERE audio_md5 IS NOT NULL AND audio_md5<>'' GROUP BY audio_md5 HAVING COUNT(*)>1")
for amd5, _ in c.fetchall():
    c.execute("SELECT id FROM archivos WHERE audio_md5=?", (amd5,))
    ids = [r[0] for r in c.fetchall() if r[0] not in used]
    if len(ids) > 1:
        grupo += 1
        for aid in ids:
            c.execute(
                "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)",
                (grupo, aid, "audio_md5", 1.0),
            )
            used.add(aid)
g_audio = grupo - g_md5

# 3. Normalized name (audio only, not in any group)
import re
import unicodedata
from collections import defaultdict


def normalize(name):
    s = os.path.splitext(name)[0].lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\b(19|20)\d{2}\b", "", s)
    s = re.sub(r"\b\d{1,3}\s*kbps\b", "", s)
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"^\d{1,3}\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


c.execute("SELECT archivo_id FROM duplicados")
used = {r[0] for r in c.fetchall()}
c.execute("SELECT id, nombre FROM archivos WHERE categoria='audio'")
norm = defaultdict(list)
for aid, nombre in c.fetchall():
    if aid in used:
        continue
    n = normalize(nombre)
    if len(n) >= 4:
        norm[n].append(aid)
for n, ids in norm.items():
    if len(ids) > 1:
        grupo += 1
        for aid in ids:
            c.execute(
                "INSERT INTO duplicados (grupo_id, archivo_id, tipo_match, score) VALUES (?,?,?,?)",
                (grupo, aid, "nombre_exacto", 1.0),
            )
g_nombre = grupo - g_md5 - g_audio

conn.commit()
c.execute("SELECT tipo_match, COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados GROUP BY tipo_match")
print("\nFinal duplicate stats:")
for tipo, gr, fi in c.fetchall():
    print(f"  {tipo}: {gr} groups, {fi} files")
c.execute("SELECT COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados")
total_g, total_a = c.fetchone()
print(f"  TOTAL: {total_g} groups, {total_a} files")
conn.close()
