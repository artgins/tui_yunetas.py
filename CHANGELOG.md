# **Changelog**

## 0.18.0 -- 20-Jul-2026
- **`yunetas --help` is now an extended help.** It printed the identical
  one-line-per-command summary that bare `yunetas` already shows, which made
  the flag pointless — you had just seen it. It now documents every command:
  its full description and every option, grouped by the job it belongs to
  (Build / Projects / Deploy targets / Deploy / Secrets / Misc).

  Bare `yunetas` keeps the compact listing, and `yunetas <command> --help`
  keeps click's own rendering; only the top-level flag changed.

  The listing is built from the commands actually registered, so one missing
  from the grouping map still appears under "Other" instead of silently
  vanishing from the help.

## 0.17.1 -- 20-Jul-2026
- **Fix the dependency declaration.** `typer[all]` was the old way to pull in
  rich/shellingham; typer stopped providing that extra (0.12 folded them into
  the base package), so every install printed
  `typer 0.27.0 does not provide the extra 'all'` and carried on. Now
  `typer>=0.12.0`, plus an explicit `rich` — `main.py` imports rich directly,
  and a dependency you import is yours to declare rather than inherit from
  another package's packaging choices.

## 0.17.0 -- 20-Jul-2026
The agent tools move INTO this package.

- **`sync_binaries.py`, `sync_configs.py` and `set_start_priorities.py` now
  ship here**, as `yunetas.agent_tools.*`, instead of being read from
  `$YUNETAS_BASE/tools/agent/` at run time.

  They were one tool released through two channels: the CLI on PyPI in
  seconds, the scripts inside the .deb/.rpm behind a full SDK release. The
  halves drifted. A live example: a node running CLI 0.14.0 against scripts
  from SDK 7.8.4 — `pipx install --upgrade yunetas` there would have handed
  `--secrets-dir` (CLI 0.16.0) to a script that had never heard of it, and the
  deploy would die with "unrecognized arguments" without anyone touching the
  SDK. That whole class of failure is gone: one version, one release.

  It also unblocks fixes. The empty-overlay rejection sat finished but
  undeliverable, waiting on an SDK release, because it lived in `tools/`.

- **Still launched as a subprocess**, not imported: the tools own their exit
  codes and install their own signal handlers (`sync_configs` wipes its
  plaintext workdir on SIGINT/SIGTERM), and importing them would put both
  under typer's control.

- `$YUNETAS_BASE/tools/agent/*.py` remain for a release or two as forwarding
  shims that print a deprecation notice, because operator runbooks reference
  those paths.

- Note the CLI still shells out to **`ycommand`**, a C binary from the SDK. So
  this does not yet make `pipx install yunetas` self-sufficient on a bare
  machine; it removes the version skew, not that dependency.

## 0.16.0 -- 19-Jul-2026
Secret overlays, so credentials stop living in project repos.

- **`--node` now passes `~/.yuneta/secrets/<node>/` to the config push.** A
  committed config declares a credential with the value `"__SECRET__"`; the
  value itself lives only on the deploy machine, in an overlay holding just
  the secret fields, deep-merged before the push. The *shape* of the config
  stays versioned in git, which is what makes it reconstructable; only the
  value is withheld.

  This exists because an SMTP password was committed in cleartext in a project
  repo. Note that adopting this does NOT fix that one: it is still in git
  history, and the only remedy there is rotating the credential.

- **`list-secrets`** shows which configs have an overlay and which FIELDS each
  supplies — never values — and flags any file whose mode is not 600.

- **There is deliberately no `set-secret`.** A command taking a credential as
  an argument writes it to your shell history and exposes it in the process
  table. Overlays are written with an editor.

- **Rotation bumps `__version__` in the committed config.** The overlay carries
  no version of its own, so a rotated value with an unchanged version would
  never be pushed. Bumping the config version is the existing batches
  convention anyway, and it leaves the *fact* of the rotation auditable in git
  while the value never touches it.

## 0.15.0 -- 19-Jul-2026
A node registry, so a remote deploy is `--node <name>`.

- **`register-node` / `list-nodes` / `unregister-node`**, backed by
  `~/.yuneta/nodes.json` (0600), mirroring the existing project registry.
  `--node/-N` on `sync`, `sync-binaries`, `sync-configs` and `upgrade-yunos`
  resolves the node's url and OAuth2 identity.

  This is the piece the central-deploy model was missing. Everything else
  already worked: the agent tools have accepted `-u wss://` with full OAuth2
  for a while. What did not exist was anywhere to *remember* it, so every
  deploy meant re-deriving the url, the issuer and the client from a config
  file somewhere and retyping four flags.

- **No credential is ever stored.** The registry holds where a node is and
  which identity we present — url, ssh target, issuer, client_id, user_id —
  and nothing you would mind reading out loud. Passwords, client secrets and
  JWTs come from `$YUNETA_OAUTH_PASSW`, `$YUNETA_OAUTH_CLIENT_SECRET` and
  `$YUNETA_OAUTH_JWT` at call time. A file whose whole purpose is to be listed
  is the wrong place for a secret.

- **Tunnel mode.** A node registered with `--ssh user@host` instead of `--url`
  is reached by forwarding a local port to its agent (1991 by default, which
  is bound to loopback and should stay that way). The tunnel is opened on a
  free port, used for the whole command, and torn down afterwards — including
  on failure, so a leaked `ssh -N` cannot keep a port open. With both `--url`
  and `--ssh` registered, the url wins unless `--tunnel` is given.

- **`sync` uses ONE connection for both pushes**, so binaries and configs can
  never end up aimed at different agents. Relatedly, `sync-configs` now runs
  its realm auto-match against the agent it is about to push to; it was
  querying the local one.

## 0.14.0 -- 19-Jul-2026
`init` no longer reports success when cmake failed.

- **`init` now fails when a cmake fails.** Its cmake loop caught
  `CalledProcessError`, printed it, and carried on: the closing recap still
  said `Project <name> initialized` and `init done`, and the exit code was
  still `0`. So a build that could not possibly work looked like a clean run,
  the real reason scrolled past above a recap that contradicted it, and the
  breakage only surfaced later as `make: *** No rule to make target 'install'`.
  `process_directories()` now returns the directories that failed; `init`
  reports `init FAILED`, lists them, and exits `1`.

  This surfaced with the SDK's new `libc_guard.cmake`, which refuses at
  configure time to link prebuilt archives against a different glibc. The
  guard fired correctly on the node and the CLI reported success anyway.

- **`build` exits `1`, not `255`.** Its failure path used the bare `exit()`,
  which is installed by `site` and is missing under `python -S`.

## 0.13.1 -- 18-Jul-2026
Quieter `init`/`build`/`clean` output.
- The whole setup block (`Setup completed successfully`, `YUNETAS_BASE`,
  `YUNETA_VERSION`, `.config`, include dir, `Generated 'yuneta_*.h'`) was both
  printed as it happened **and** replayed in the closing recap, so every command
  showed it twice. These informational lines now live only in the recap, which
  is where they are read; errors still print immediately.
- The `yuneta_config.h ... menuconfig` warning is no longer emitted on a
  runtime-only node: its `.config` comes from the `.deb`/`.rpm` and there is no
  Kconfig tree to re-run `menuconfig` against, so the advice was unactionable.
  Nodes with the framework sources keep it.

## 0.13.0 -- 18-Jul-2026
Make `init`/`build`/`clean` usable on runtime-only nodes.
- On a node installed from the `.deb`/`.rpm` (sparse SDK: `outputs/`,
  `outputs_ext/`, `tools/`, `.config`, but no framework sources and no
  `YUNETA_VERSION`), the bare `yunetas init` / `yunetas build` still selected
  the SDK: `build` skipped every missing SDK directory and then failed on the
  project's absent `yunos/build`, while `init` bailed out with *"refusing to
  reset outputs/"*. The only working form was naming the project explicitly.
- The SDK is now **never** selectable on such a node: with no project names the
  command narrows to the registered projects and says so, so bare
  `yunetas init` + `yunetas build` work exactly as on a development node.
- `--sdk-only` there is now a clear error (it asks for the one thing that node
  cannot do), and a runtime-only node with an empty project registry fails
  pointing at `register-project` instead of silently doing nothing.
- Development nodes (framework sources present) are unaffected.

## 0.12.2 -- 17-Jul-2026
Drop the per-invocation `Using YUNETAS_BASE at ...` banner.
- 0.12.1 moved it to stderr to unbreak completion, but it still printed on every
  single invocation. It is now not printed at import time at all — the base is
  still recapped by `final_messages` at the end of `init`/`build`/`clean`, which
  is the only place it was actually useful. Completion invocations now emit
  nothing but the candidates on either stream.
- **Shell completion without editing your dotfiles:** drop the script into the
  bash-completion user dir, which its dynamic loader picks up on demand — no
  `.bashrc` change (unlike `yunetas --install-completion`):
  `yunetas --show-completion > ~/.local/share/bash-completion/completions/yunetas`,
  then open a new shell.

## 0.12.1 -- 17-Jul-2026
Fix shell completion: keep the startup banner off stdout.
- The `Using YUNETAS_BASE at ...` line printed at import time went to **stdout**,
  which runs on every invocation — including the shell-completion one, whose
  `COMPREPLY` is captured from stdout. So the banner showed up as a bogus
  completion candidate and broke `yunetas <tab>`. It now prints to **stderr**
  (matching the error path just above it); stdout carries only the candidates.
- Get it: reinstall the CLI (`pipx install --force <tui_yunetas path>` or, once
  published, `pipx upgrade yunetas`), then `yunetas --install-completion` and
  restart the shell.

## 0.12.0 -- 08-Jul-2026
- Verify `linux-ext-libs` is up to date before build.

## 0.11.1 -- 15-Jun-2026
Make a resumed upgrade idempotent instead of aborting.
- When a prior update installed binaries and registered the new yuno rows but
  never promoted them (`deactivate-snap` missing), re-running the deploy hit the
  agent's idempotent "... already exists" answers. `sync-binaries` /
  `sync-configs` painted those as red `FAILED`, and `upgrade-yunos` aborted at
  `find-new-yunos create=1` — skipping the one step that mattered,
  `deactivate-snap` (the operator had to run it by hand).
- `sync-binaries` / `sync-configs`: an `install-binary` / `create-config` that
  comes back "... already exists" is now reported as `ALREADY PRESENT`
  (idempotent, yellow) and counts as ok, not a failure.
- `upgrade-yunos`: if `find-new-yunos create=1` fails only because the rows
  already exist, it no longer aborts — it falls through to `deactivate-snap`,
  which performs the promotion. The agent's comments are surfaced (no longer
  suppressed) so a mixed or genuine failure is still visible, and a
  non-idempotent error still fails closed.

## 0.11.0 -- 15-Jun-2026
Couple binary+config deploys, and don't stack snaps in `upgrade-yunos`.
- New `sync` command: pushes binaries AND configs in one step (`sync-binaries`
  then `sync-configs`) so a binary bump never ships without its matching config
  bump — the stale-config failure mode behind verify-by-default OIDC breakage
  (new fail-closed binary vs old no-CA config). Shared extra args are forwarded
  to both tools; use the individual commands for tool-specific flags. If the
  binaries push fails, configs are not synced (no half-deploy).
- `sync-binaries` now prints a one-line reminder to sync the matching configs
  after a successful (non-dry-run) push.
- `upgrade-yunos`: if a snap is already active, reuse it as the rollback point
  instead of shooting a new one (`active_snap_name` via `*snaps`). The by-name
  idempotency check is unchanged when no snap is active.
- Refactor: the `sync-configs` realm-match + push loop moved to a shared
  `push_configs()` helper, reused by both `sync-configs` and `sync`.

## 0.10.1 -- 14-Jun-2026
Quieter `upgrade-yunos` output.
- `run_ycommand` gained an `echo_output` flag; the two `find-new-yunos`
  steps now suppress ycommand's raw stdout. The preview is no longer printed
  twice (raw JSON + formatted list) and `create=1` no longer dumps the verbose
  created-node table — a one-line `Created N new yuno row(s).` summary replaces
  it. Command echo and error/stderr handling are unchanged.

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

