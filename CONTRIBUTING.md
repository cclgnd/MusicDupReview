# Contributing

## Workflow

1. Branch from `main`.
2. Keep each change focused on one behavior or refactor.
3. Run tests before committing:

```powershell
python -m unittest discover -s tests
```

4. Open a pull request using the template.

## Branch Names

- `feature/<short-name>` for user-facing improvements.
- `fix/<short-name>` for defects.
- `refactor/<short-name>` for internal structure changes.
- `safety/<short-name>` for file or database safety reviews.

## Safety Rules

- Never add permanent-delete behavior.
- Keep file removal routed through the Recycle Bin.
- Confirm broad actions before applying them to a page or database.
- Treat SQLite databases, generated reports, backups, settings, and caches as local-only files.
- Add or update tests when touching duplicate detection, decision persistence, database updates, or file actions.

## Local Data

Use environment variables for machine-specific paths:

```powershell
$env:MUSIC_DUP_ROOT="D:\path\to\music"
$env:MUSIC_DUP_DB="D:\path\to\music_library.db"
$env:MUSIC_DUP_REPORT_DIR="D:\path\to\reports"
```
