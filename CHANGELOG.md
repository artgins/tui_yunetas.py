# **Changelog**

## 0.10.0 -- 13-Jun-2026
Agent-aware deploy: realm auto-match and a one-shot upgrade flow.
- `sync-configs` without `--host` now matches each project's
  `yunos/batches/<host>/` directories against the realm_ids the local agent
  manages (`*list-realms`) and syncs every match — a node running several
  realms deploys all the relevant ones in one go (a batches dir is named after
  its realm_id, the deploy FQDN). `--host` still targets one dir explicitly;
  if the agent can't be reached it falls back to the legacy single-hostname
  guess. New `--url` / `-u` (used for the realm query and forwarded to the
  sync).
- New `upgrade-yunos`: promotes freshly installed binaries/configs to primary
  on the local agent. Optional rollback snapshot (idempotent by name, default
  `pre-upgrade-<YYYYMMDD>`, `--no-snap` to skip) -> `find-new-yunos` preview +
  confirm (`--yes` to skip the prompt) -> `find-new-yunos create=1` ->
  `deactivate-snap` (restart_nodes: SIGKILL + treedb reload, newest release
  wins). `--dry-run` prints the agent commands without running them.

## 0.9.1 -- 13-Jun-2026
Move the project registry out of the source tree:
- The registry now lives in `~/.yuneta/projects.json` (user runtime state),
  not `$YUNETAS_BASE/.projects.json`. It is independent of the checkout: which
  external projects to build alongside the SDK is daily-use state, it has
  nothing to do with the contents of any source tree.
- One-time soft migration: on first run, if the legacy
  `$YUNETAS_BASE/.projects.json` exists and the new file does not, it is moved
  across (a notice is printed). No manual step needed.

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
- Runtime-only nodes (`.deb`/`.rpm` sparse SDK: no `YUNETA_VERSION`, headers
  shipped in `outputs/include`) are supported: `init <project>` /
  `build <project>` work there; a plain `init` refuses to reset the
  shipped `outputs/`.

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

