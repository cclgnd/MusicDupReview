from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = str(APP_DIR / "music_library.db")

MATCH_OPTIONS = [
    ("All", "all"),
    ("Exact file", "md5"),
    ("Same audio", "audio_md5"),
    ("Same image", "image_ahash"),
    ("Same name + size", "nombre_tamano"),
    ("Similar name", "nombre_normalizado"),
    ("Exact filename", "nombre_identico"),
]

RULE_OPTIONS = [
    ("Keep longest path", "longest_path"),
    ("Keep shortest path", "shortest_path"),
    ("Keep largest file", "largest"),
    ("Keep smallest file", "smallest"),
    ("Keep newest modified", "newest"),
    ("Keep oldest modified", "oldest"),
    ("Trash exact hash duplicates only", "exact_hash"),
    ("Clear choices", "clear"),
]
