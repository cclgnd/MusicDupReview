import sqlite3
import csv
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.environ.get("MUSIC_DUP_REPORT_DIR", APP_DIR)
DB = os.environ.get("MUSIC_DUP_DB", os.path.join(APP_DIR, "music_library.db"))
OUT_CSV = os.path.join(REPORT_DIR, "duplicados_full.csv")
OUT_MD = os.path.join(REPORT_DIR, "reporte_full.md")

conn = sqlite3.connect(DB)
c = conn.cursor()

# global stats
c.execute("SELECT COUNT(*), SUM(tamano) FROM archivos")
total, tam_total = c.fetchone()
c.execute("SELECT categoria, COUNT(*), SUM(tamano) FROM archivos GROUP BY categoria ORDER BY 2 DESC")
cats = c.fetchall()
c.execute("SELECT oculto, COUNT(*) FROM archivos GROUP BY oculto")
ocultos = dict(c.fetchall())
c.execute("SELECT COUNT(*) FROM archivos WHERE error IS NOT NULL")
n_err = c.fetchone()[0]

# duplicate stats
c.execute("SELECT tipo_match, COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados GROUP BY tipo_match")
dup_stats = c.fetchall()

# recoverable space (sum of all but smallest copy per group)
c.execute("""
SELECT d.grupo_id, a.id, a.tamano FROM duplicados d JOIN archivos a ON a.id=d.archivo_id
ORDER BY d.grupo_id, a.tamano
""")
all_dups = c.fetchall()
from collections import defaultdict
groups = defaultdict(list)
for gid, aid, tam in all_dups:
    groups[gid].append((aid, tam))
recoverable = 0
for gid, items in groups.items():
    items.sort(key=lambda x: x[1], reverse=True)  # keep largest, recover others
    for aid, tam in items[1:]:
        recoverable += tam

# top duplicate folders
c.execute("""
SELECT a.carpeta, COUNT(*) as n FROM duplicados d
JOIN archivos a ON a.id=d.archivo_id
GROUP BY a.carpeta ORDER BY n DESC LIMIT 25
""")
top_dup_folders = c.fetchall()

# write CSV with all duplicate groups
with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["grupo", "tipo_match", "score", "archivo_id", "ruta", "tamano_bytes", "md5"])
    c.execute("""
    SELECT d.grupo_id, d.tipo_match, d.score, a.id, a.ruta, a.tamano, a.md5
    FROM duplicados d JOIN archivos a ON a.id=d.archivo_id
    ORDER BY d.grupo_id, a.ruta
    """)
    for r in c.fetchall():
        w.writerow(r)

# markdown report
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("# Full Library Report — D:\\cdu\\music\n\n")
    f.write("## Global stats\n\n")
    f.write(f"- Total files: **{total}**\n")
    f.write(f"- Total size: **{tam_total/1024/1024/1024:.2f} GB**\n")
    f.write(f"- Hidden files: {ocultos.get(1, 0)}\n")
    f.write(f"- Errors / unread: {n_err}\n\n")
    f.write("### By category\n\n")
    for cat, n, sz in cats:
        f.write(f"- {cat:8s} {n:6d} files  {sz/1024/1024/1024:6.2f} GB\n")

    f.write("\n## Duplicates summary\n\n")
    for tipo, g, fi in dup_stats:
        f.write(f"- {tipo}: **{g} groups, {fi} files**\n")
    f.write(f"\n- **Recoverable space (keeping largest per group): {recoverable/1024/1024/1024:.2f} GB**\n")

    f.write("\n## Top 25 folders by duplicate count\n\n")
    for carp, n in top_dup_folders:
        f.write(f"- {n:5d}  `{carp}`\n")

    # show 10 example name-match groups (audio dupes between folders)
    f.write("\n## Example name-match groups (first 10)\n\n")
    c.execute("""
    SELECT d.grupo_id FROM duplicados d
    WHERE d.tipo_match='nombre_exacto'
    GROUP BY d.grupo_id LIMIT 10
    """)
    example_groups = [r[0] for r in c.fetchall()]
    for gid in example_groups:
        c.execute("""
        SELECT a.ruta, a.tamano, a.md5 FROM duplicados d
        JOIN archivos a ON a.id=d.archivo_id
        WHERE d.grupo_id=? ORDER BY a.ruta
        """, (gid,))
        f.write(f"\n**Group {gid}**:\n\n")
        for ruta, tam, md5 in c.fetchall():
            f.write(f"- `{ruta}` ({tam/1024/1024:.2f} MB, md5 `{md5[:12] if md5 else 'N/A'}...`)\n")

print("OK")
print(f"CSV: {OUT_CSV}")
print(f"MD : {OUT_MD}")
print(f"Total dup files: {sum(r[2] for r in dup_stats)}")
print(f"Recoverable: {recoverable/1024/1024/1024:.2f} GB")
