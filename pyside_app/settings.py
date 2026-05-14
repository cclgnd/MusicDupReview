import json
from pathlib import Path

from pyside_app.config import APP_DIR, DEFAULT_DB

SETTINGS_PATH = APP_DIR / "dup_review_settings.json"


def load_app_settings(settings_path=SETTINGS_PATH):
    path = Path(settings_path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_app_settings(settings, settings_path=SETTINGS_PATH):
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dict(settings), handle, indent=2, sort_keys=True)


def initial_database_path(cli_path=None, settings_path=SETTINGS_PATH):
    if cli_path:
        return cli_path
    settings = load_app_settings(settings_path)
    saved_value = settings.get("db_path") or ""
    saved_path = Path(saved_value) if saved_value else None
    if saved_value and Path(settings_path) != SETTINGS_PATH:
        return saved_value
    if saved_path and saved_path.exists():
        return str(saved_path)
    latest_path = latest_database_path(settings_path)
    if latest_path:
        return str(latest_path)
    return DEFAULT_DB


def latest_database_path(settings_path=SETTINGS_PATH):
    candidates = []
    root = APP_DIR if Path(settings_path) == SETTINGS_PATH else Path(settings_path).parent
    search_dir = root / "search_databases"
    if search_dir.exists():
        candidates.extend(path for path in search_dir.glob("*.db") if path.is_file())
    if Path(settings_path) != SETTINGS_PATH and root.exists():
        candidates.extend(path for path in root.glob("*.db") if path.is_file())
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)
