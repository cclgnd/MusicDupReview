import sqlite3
import csv
import os
from collections import defaultdict

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.environ.get("MUSIC_DUP_REPORT_DIR", APP_DIR)
DB = os.environ.get("MUSIC_DUP_DB", os.path.join(APP_DIR, "music_library.db"))
OUT_CSV = os.path.join(REPORT_DIR, "duplicados_audio_md5.csv")
OUT_MD = os.path.join(REPORT_DIR, "reporte_audio_md5.md")

conn = sqlite3.connect(DB)
c = conn.cursor()

c.execute("SELECT tipo_match, COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados GROUP BY tipo_match")
stats = c.fetchall()

# recoverable space
c.execute("SELECT d.grupo_id, a.id, a.tamano FROM duplicados d JOIN archivos a ON a.id=d.archivo_id ORDER BY d.grupo_id, a.tamano DESC")
groups = defaultdict(list)
for gid, aid, tam in c.fetchall():
    groups[gid].append((aid, tam))

recov_total = 0
recov_by_type = defaultdict(int)
for gid, items in groups.items():
    items.sort(key=lambda x: x[1], reverse=True)
    c.execute("SELECT tipo_match FROM duplicados WHERE grupo_id=? LIMIT 1", (gid,))
    tipo = c.fetchone()[0]
    for aid, tam in items[1:]:
        recov_total += tam
        recov_by_type[tipo] += tam

# write csv with audio_md5
with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["grupo", "tipo_match", "archivo_id", "ruta", "tamano", "md5", "audio_md5"])
    c.execute("""
    SELECT d.grupo_id, d.tipo_match, a.id, a.ruta, a.tamano, a.md5, a.audio_md5
    FROM duplicados d JOIN archivos a ON a.id=d.archivo_id
    ORDER BY d.grupo_id, a.ruta
    """)
    for r in c.fetchall():
        w.writerow(r)

# top examples per type
def top_examples(tipo, n=5):
    c.execute("SELECT DISTINCT grupo_id FROM duplicados WHERE tipo_match=? LIMIT ?", (tipo, n))
    return [r[0] for r in c.fetchall()]

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("# Audio MD5 Detection Report\n\n")
    f.write("## Layered detection summary\n\n")
    f.write("| Layer | Groups | Files | Recoverable |\n")
    f.write("|---|---:|---:|---:|\n")
    for tipo, g, fi in stats:
        rec = recov_by_type[tipo]
        f.write(f"| {tipo} | {g} | {fi} | {rec/1024/1024/1024:.2f} GB |\n")
    f.write(f"| **TOTAL** | **{sum(r[1] for r in stats)}** | **{sum(r[2] for r in stats)}** | **{recov_total/1024/1024/1024:.2f} GB** |\n\n")

    f.write("## What each layer means\n\n")
    f.write("- **md5**: byte-identical files (full file MD5 matches). Pure copies.\n")
    f.write("- **audio_md5**: same audio data, different ID3 tags. True duplicates with metadata edits.\n")
    f.write("- **nombre_exacto**: same normalized filename, but audio differs. Likely different rips/encodes.\n\n")

    f.write("## Audio MD5 examples (same audio, different tags)\n\n")
    for gid in top_examples("audio_md5", 8):
        c.execute("""
        SELECT a.ruta, a.tamano, a.md5, a.audio_md5
        FROM duplicados d JOIN archivos a ON a.id=d.archivo_id
        WHERE d.grupo_id=? ORDER BY a.ruta
        """, (gid,))
        f.write(f"\n**Group {gid}**\n\n")
        for ruta, tam, md5, amd5 in c.fetchall():
            f.write(f"- `{ruta}`\n")
            f.write(f"  - size: {tam:,}  full_md5: `{md5[:12]}...`  audio_md5: `{amd5[:12]}...`\n")

print("OK")
print(f"CSV: {OUT_CSV}")
print(f"MD : {OUT_MD}")
print(f"Total recoverable: {recov_total/1024/1024/1024:.2f} GB")
