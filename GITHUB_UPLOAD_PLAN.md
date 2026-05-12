# GitHub Upload Plan

## Target

- Owner: `cclgnd`
- Repository: `MusicDupReview`
- Visibility: private unless explicitly changed before creation.

## Included

- Python source files.
- `pyside_app/` source.
- Unit tests in `tests/`.
- Project docs: `README.md`, `MIGRATION_NOTES.md`, `PROJECT_FUNCTIONS_REVIEW.md`.
- GitHub Actions workflow for Windows unit tests.

## Excluded

- SQLite databases.
- CSV/Markdown duplicate reports with local media paths.
- Local settings.
- Backups and prototype folders.
- Virtual environments, caches, bytecode, shortcuts.

## Safe Upload Sequence

1. Verify tests pass locally.
2. Initialize Git in `D:\MusicDupReview`.
3. Commit the cleaned source tree.
4. Create `cclgnd/MusicDupReview`.
5. Push `main`.
6. Verify GitHub Actions starts on the pushed commit.

## Repository Deletion Guard

Delete remote repositories only after listing exact names and receiving explicit confirmation. This avoids accidental loss of unrelated work in the `cclgnd` account.
