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
    return settings.get("db_path") or DEFAULT_DB
