# **Changelog**

## 0.9.0 -- 12-Jun-2026
External projects integration and agent sync wrappers:
- New `register-project` / `unregister-project` / `list-projects`:
  registry in `$YUNETAS_BASE/.projects.json` (machine-local, gitignored).
- `init` / `build` / `clean` now also process each registered project's
  `yunos/` after the SDK. Select with positional project names
  (SDK skipped) or `--sdk-only`.
- New `sync-binaries` / `sync-configs`: wrappers over
  `tools/agent/sync_*.py`, forwarding arguments. `sync-configs` drives
  from each registered project's `yunos/batches/<host>/` (`--host`, with
  hostname auto-match).

## 0.8.0 -- 08-Apr-2026
include performance in build

## 0.7.0 -- 30-Mar-2026
remove musl

## v0.5.7 -- 27-Sep-2025
Get YUNETAS_BASE from:
    1) ENV, 2) /yuneta/development/yunetas, 3) /yuneta/development, else fail

## v0.5.6 -- 09-Sep-2025
Remove full outputs directory on init

## v0.5.5 -- 10-Ago-2025
Remove common directory

## 0.5.8 -- 21-Jan-2026
save the output test in a txt file. To have a history of tests.

