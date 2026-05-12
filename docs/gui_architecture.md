# GUI Architecture Decision

## Decision

Use PySide6 with Qt Widgets as the primary GUI engine.

## Status

Accepted.

## Why

- The app is a dense desktop review tool, not a marketing-style web UI.
- Qt Widgets provide mature tables, splitters, dialogs, shortcuts, menus, status bars, and threaded workers.
- PySide6 keeps the Python domain logic in-process, avoiding a web sidecar boundary for file actions.
- Qt's model/view architecture supports scalable data views when the app outgrows item widgets.

## Current State

- `dup_review_gui.py` is the legacy Tkinter app.
- `pyside_app/` is the target GUI path.
- The first PySide6 implementation still uses `QTableWidget` as a migration bridge.

## Target Architecture

- `pyside_app/main.py`: application entry point only.
- `pyside_app/window.py`: top-level window, navigation, menus, status playback.
- `pyside_app/views/`: user-facing pages.
- `pyside_app/models/`: Qt table models backed by repository/service calls.
- `pyside_app/config.py`: app paths and UI option constants.
- Root service modules remain GUI-independent.

## Migration Rules

- Keep file operations routed through `file_actions.send_to_recycle_bin`.
- Keep database changes in repository/service functions, not raw UI handlers.
- Prefer `QTableView + QAbstractTableModel` for new table work.
- Keep the Tkinter app available until PySide6 reaches feature parity.
- Add tests before changing duplicate grouping, decision persistence, or file action behavior.
