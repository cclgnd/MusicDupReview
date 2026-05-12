# MusicDupReview Function Review

Generated: 2026-05-11

## What The App Does Now

`dup_review_gui.py` is the main app. It can:

- Open an existing duplicate-search database.
- Create a new independent search database from any folder.
- Create a new search using exact MD5 or audio-only MD5.
- Check the current search against the real file structure.
- Back up the current search database.
- Filter duplicate groups by match type, search text, and file type.
- Sort groups by original group id or biggest single file.
- Sort rows inside groups by hash, size, path length, name, or extension.
- Review duplicate rows, mark keep/delete/move, and apply changes.
- Preview image files in rows.
- Play audio files, seek through playback, and show bitrate.
- Show full MD5 and audio MD5 hashes with color-coded hash values.
- Build folder merge groups for audio duplicates.

## Main Files

- `dup_review_gui.py`: current GUI app and most active code.
- `Launch_DupReview.bat`: starts the app using the local `.venv` Python.
- `music_library.db`: current default search database.
- `dup_review_settings.json`: remembers app window and last database.
- `PROJECT_FUNCTIONS_REVIEW.md`: this cleanup map.
- `backups/`: dated project backups.

## Current Support/Legacy Files

These look like earlier scan/report/debug scripts. Keep until verified, but many are likely not needed by the modern GUI path:

- `scan_music.py`: old MP3-only scanner.
- `scan_all.py`: older broader scanner.
- `detect_fast.py`: older duplicate detector.
- `audio_md5_all.py`: computes audio MD5 for existing DB.
- `audio_scan_g124.py`, `bench_audio_md5.py`, `check_g124.py`, `diff_g124.py`, `check_progress.py`: investigation/benchmark helpers.
- `report_audio_md5.py`, `report_full.py`: report generators.
- `duplicados*.csv`, `reporte*.md`: generated reports/data snapshots.

## GUI Function Map

### Startup And Settings

- `__init__`: creates app state, opens database, builds UI, loads groups.
- `_load_settings`: reads `dup_review_settings.json`.
- `_save_settings`: stores last DB path and window geometry/state.
- `_on_close`: saves settings, stops audio, closes DB.
- `main`: creates Tk root and starts app.

### Database Schema

- `_ensure_decisions_table`: wrapper for schema setup.
- `_ensure_schema`: creates/updates database tables and indexes.
- `_ensure_column`: adds missing DB columns.

### Style And UI

- `_setup_styles`: configures Tk/ttk colors and widget style.
- `_build_ui`: builds filters, list area, playback/status bar.
- `_build_menu`: builds top menu.
- `_show_playback_panel`: shows playback bar during audio.
- `_hide_playback_panel`: hides playback bar when idle.
- `_resize_playback_slider`: keeps seek bar responsive.
- `_return_focus_to_root`: returns keyboard focus after button use.
- `_ui_command`: wraps button commands.

### Search Databases

- `new_search_database`: asks folder and output DB, runs scan.
- `_create_scan_database`: scans files, hashes them, stores image metadata.
- `_audio_md5_file`: computes audio-only MD5 for audio files.
- `_audio_md5_mp3`: skips MP3 ID3v2 and ID3v1 tags before hashing audio bytes.
- `open_database`: opens another search database.
- `_switch_database`: closes current DB and loads chosen DB.
- `backup_database`: copies current database to timestamped backup.
- `verify_database_files`: menu action to check disk vs current DB.
- `_verify_database_files`: removes missing files, updates changed files, adds new files, rebuilds duplicates.
- `_scan_roots_for_connection`: reads scan roots from DB notes.

### File Classification And Hashing

- `_category_for_extension`: maps extension to audio/image/list/info/other.
- `_md5_file`: computes full file MD5.
- `_image_fingerprint`: gets image size and perceptual average hash.
- `_detect_duplicates_for_connection`: rebuilds duplicate groups.
- `_normalize_name`: creates normalized file-name keys for fuzzy-ish name grouping.

### Filters And Loading

- `_on_filter_change`: resets page and reloads.
- `_set_extension_filter`: applies file type filter.
- `_refresh_extension_menu`: rebuilds file type menu from DB extensions.
- `_load_groups`: finds matching duplicate group ids.
- group sort can show biggest single-file groups first.
- `_group_has_missing_or_deleted`: checks if group has missing/deleted rows.
- `_render_page`: clears current page and renders visible groups.
- `_build_group_block`: renders group header and rows.

### Rows And Visuals

- `_assign_hash_colors`: assigns stable colors for MD5 and audio MD5 values.
- `_hash_color`: returns color for a hash value from the right palette.
- `_build_file_row`: builds one file row.
- file rows show exact byte size plus MB size.
- summary bar shows filtered file count and total filtered size.
- `_is_image_row`: detects image row.
- `_make_image_preview`: creates row thumbnail.
- `_fit_path_label`: recalculates path wrapping.
- `_wrap_path_to_width`: wraps long paths.
- `_apply_row_color`: applies row state colors, missing state, hash colors.

### Selection And Keyboard

- `_on_row_click`: selects or toggles row.
- `_selected_rows`: returns selected rows.
- `_clear_selection`: clears selected rows.
- `_on_key`: handles keyboard shortcuts.
- `_toggle_multi_select`: toggles multi-select.
- `_update_mode_indicator`: updates shortcut/status text.

### Delete/Move/Decisions

- `_immediate_delete`: deletes selected files immediately.
- `move_file_dialog`: chooses move destination.
- `_on_decision_change`: stores keep/delete/move decision.
- `_auto_suggest_group`: suggests one keep and duplicate actions.
- `reset_all_to_keep`: resets visible decisions.
- `auto_suggest_all`: auto-suggests visible groups.
- `apply_decisions`: applies delete and move decisions.

### Audio Playback

- `_space_pressed`: play/stop selected file.
- `_format_time`: formats seconds.
- `_format_bitrate`: formats bitrate.
- `_row_is_playing`: checks if row is current audio.
- `_rows_include_playing`: checks if actions affect current audio.
- `_release_if_rows_affect_playback`: stops only if needed.
- `_cancel_playback_timer`: cancels timer.
- `_reset_playback_bar`: resets/hides player.
- `_get_audio_duration`: gets audio duration.
- `_event_to_seek_seconds`: maps slider mouse position to time.
- `_on_seek_press`: begins seek.
- `_on_seek_drag`: live seek drag.
- `_on_seek_release`: finishes seek.
- `_seek_playback`: jumps audio to a time.
- `_start_playback_timer`: starts UI timer.
- `_update_playback_timer`: refreshes playback time/bar.
- `play_file`: starts audio.
- `stop_audio`: stops audio.
- `_release_audio`: unloads pygame handle on Windows.

### Folder Merge Tools

- `open_folder`: opens containing folder.
- `_folder_clone_counts`: counts audio clones for folder.
- `_folder_clone_rows`: rows used by folder merge.
- `build_folder_clone_group`: creates merged group from folder audio hashes.
- `_folder_audio_rows`: gets audio hash rows for folder.
- `_find_merge_candidate_folders`: finds donor folders.
- `_folder_leftovers_after_removing`: checks leftovers after cleanup.
- `preview_folder_merge`: shows merge cleanup preview.
- `_apply_folder_merge`: deletes donor duplicates and removes empty dirs.

### Pagination

- `prev_page`: previous duplicate page.
- `next_page`: next duplicate page.

## Clutter / Cleanup Candidates

High value cleanup:

- Split `dup_review_gui.py` into modules:
  - `app.py` for GUI shell.
  - `db.py` for schema and DB operations.
  - `scanner.py` for new search and verify.
  - `audio_player.py` for playback.
  - `rows.py` for row rendering.
  - `folder_merge.py` for folder merge tools.

- Remove or archive old scripts once the GUI scanner is trusted:
  - likely archive: `scan_music.py`, `detect_fast.py`, `report_full.py`, `report_audio_md5.py`.
  - keep short-term: `audio_md5_all.py`, `scan_all.py` until audio MD5 behavior is fully integrated in new scanner.

- Move generated CSV/Markdown reports to `reports/`.
- Move backups to `backups/` only.
- Add `requirements.txt` with `pygame`, `send2trash`, `pillow`.
- Add a small `README_APP.md` for normal use only.

## Risk Notes

- `verify_database_files` now changes the active database. It removes missing rows and rebuilds duplicate groups.
- New search can compute audio-only MD5. MP3 uses tag-skipping audio bytes; other audio formats currently fall back to full-file MD5.
- The folder merge tools are powerful and should stay behind previews/confirmations.
