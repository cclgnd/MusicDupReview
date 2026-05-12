# Migration Notes

## Current Stabilization Rules

- Keep Tkinter UI functional until backend services are separated.
- Preserve `archivos`, `duplicados`, `decisiones`, and `escaneos` schema compatibility.
- Treat `deleted` and `missing` as persistent file-condition states.
- Treat `master`, `delete`, `protected`, and `ignored` as session review choices.
- Keep Recycle Bin as only destructive file action.
- Keep daily backups in `backups/` before UI/backend rewrites.

## Next Split

- `db_repository.py`: schema setup and duplicate group read queries done; mutation queries pending.
- `review_state.py`: decisions, session snapshot/recovery, save helpers done.
- `file_actions.py`: Recycle Bin send done; future restore/quarantine hooks pending.
- `playback_service.py`: pygame backend wrapper done; future chiptune backend pending.
- `duplicate_rules.py`: scoped Keep/Trash rule application done.
- `media_utils.py`: file category, hashes, name normalization, image fingerprint done.
- `duplicate_detection.py`: full duplicate rebuild and new-file incremental duplicate checks done.
- `database_maintenance.py`: Check files now availability/new-file update workflow done.
- `undo_service.py`: bounded undo stack and row snapshots done.
- `pyside_app/`: standalone PySide6 shell started; Tkinter launcher preserved.
  - Duplicate Removal: group list, file rows, Keep/Trash/Clear, scoped Apply, scoped Reset, scoped Rules, K/T/D/Ctrl+Z shortcuts started.
  - File Explorer: searchable file table and contiguous identical-hash display started.
  - Shared playback: Play/Stop status-bar control and Space shortcut started.

## Pending Jobs

- Fix Ctrl+Z after `D` delete:
  - Restore file from Recycle Bin to original path when possible.
  - If restore is unavailable, keep row as `Deleted` and show clear status instead of reverting to playable state.
  - Block playback for rows whose file no longer exists.
- Add three main GUI windows/views:
  - File Explorer.
  - Duplicate Removal.
  - Utilities / Maintenance.
- Define useful tasks for Utilities:
  - Check file availability.
  - Recover last session state.
  - Recent searches.
  - Re-unify search files into app-managed folder.
  - Backup current search.
  - Integrity reports.
  - Chiptune playback support notes.
- Add `New Presentation` option.
- Add contiguous identical-hash file mode:
  - Temporarily disable duplicate grouping. Started in PySide File Explorer.
  - Show files as ordered filesystem/hash sequence. Started.
  - Highlight adjacent/contiguous identical hashes. Started.
  - Reuse mode for other non-grouped review scenarios.

## PySide6 Target

- Main window with filter toolbar, grouped file list, action scope dialogs, and bottom playback bar.
- Replace row widgets with model/view rows.
- Keep keyboard behavior:
  - Ctrl+click multi-select while held.
  - Space play/stop selected file.
  - D direct Recycle Bin.
  - Ctrl+Z undo review state.

## Roadmap

1. Stabilize current Tkinter app.
   - Fix Ctrl+Z delete behavior.
   - Keep Deleted/Missing rows non-playable.
   - Finish state colors, shortcuts, scoped reset/apply/rules.

2. Extract backend services without changing UI.
   - Move schema code to `db_repository.py`. Done.
   - Move review state/session recovery to `review_state.py`. Done.
   - Move Recycle Bin send operation to `file_actions.py`. Done.
   - Move playback to `playback_service.py`. Done.
   - Move scoped rules to `duplicate_rules.py`. Done.
   - Move duplicate detection to `duplicate_detection.py`. Done.
   - Move Check files now workflow to `database_maintenance.py`. Done.
   - Move duplicate group/search queries to repository layer. Done.
   - Move remaining mutation queries to repository layer. Pending.
   - Move undo stack out of GUI. Done.
   - Move selection state out of GUI. Pending.

3. Add safety tests.
   - Decision state transitions.
   - Recycle Bin failure behavior.
   - Undo behavior.
   - Missing/deleted playback blocking.
   - Extension/search filtering.

4. Build PySide6 shell.
   - Main navigation with File Explorer, Duplicate Removal, Utilities. Started.
   - Shared bottom playback bar. Started.
   - Shared state/shortcut handling. Pending.

5. Port Duplicate Removal first.
   - Reuse backend services.
   - Implement grouped model/view list. Started.
   - Implement scoped Apply, Rules, Reset. Started for selected group, loaded page, full search.

6. Add File Explorer view.
   - Folder tree. Pending.
   - File table. Started.
   - Hash/status columns.
   - Contiguous identical-hash mode. Started.

7. Add Utilities view.
   - Availability check.
   - Recent searches. Pending.
   - Backups. Started.
   - Re-unify files workflow.
   - Reports.

8. Retire Tkinter.
   - Run parity checks.
   - Keep old app backup.
   - Switch launcher to PySide6 entry point.
