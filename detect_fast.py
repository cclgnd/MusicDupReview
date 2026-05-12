"""
Fast duplicate detection: md5 exact + normalized name exact.
Skips slow similarity phase.
"""
import sqlite3
import os
import re
import unicodedata
from collections import defaultdict

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("MUSIC_DUP_DB", os.path.join(APP_DIR, "music_library.db"))


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


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM duplicados")
    grupo = 0

    # 1. MD5 exact
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

    # 2. Normalized name exact (audio only, not already in md5 group)
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
    g_nombre = grupo - g_md5

    conn.commit()

    # stats
    c.execute("SELECT COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados")
    total_g, total_a = c.fetchone()
    c.execute("SELECT tipo_match, COUNT(DISTINCT grupo_id), COUNT(*) FROM duplicados GROUP BY tipo_match")
    print("Detection done")
    print(f"  md5 groups: {g_md5}")
    print(f"  name groups: {g_nombre}")
    print(f"  total groups: {total_g}, files involved: {total_a}")
    for r in c.fetchall():
        print(f"  type={r[0]} groups={r[1]} files={r[2]}")
    conn.close()


if __name__ == "__main__":
    main()
