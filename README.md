# TUI for yunetas

> This is the TUI (Terminal User Interface) for [Yuneta Simplified](https://yuneta.io)

<a href="https://yuneta.io/">
    <img src="https://github.com/artgins/yunetas/blob/main/docs/doc.yuneta.io/_static/yuneta-image.svg?raw=true" alt="Icon" width="200" /> <!-- Adjust the width as needed -->
</a>

[Yuneta Simplified](https://yuneta.io) is a development framework about messages and services, based on 
[Event-driven](https://en.wikipedia.org/wiki/Event-driven_programming), 
[Automata-based](https://en.wikipedia.org/wiki/Automata-based_programming) 
and [Object-oriented](https://en.wikipedia.org/wiki/Object-oriented_programming) 
programming.

Yuneta is based in functions, but it manages a system of virtual classes 
defined by programmatically and schematically.  

All his philosophy is based on that virtual classes (namely GClass or class G).

All architecture done by configuration, based in schema,
easy to see by human eye. 
Of course, you have an API functions to change configuration and data in real time. 

For [Linux](https://en.wikipedia.org/wiki/Linux) and [RTOS/ESP32](https://www.espressif.com/en/products/sdks/esp-idf). 

Versions in C, Javascript and (TODO) Python.

For more details, see [doc.yuneta.io](https://doc.yuneta.io) 



[pypi-badge]: https://img.shields.io/pypi/v/yunetas


# Commands

```shell
yunetas init                  # create build dirs, compiler/build-type from .config (menuconfig)
yunetas build [-j N]          # make -jN install: SDK + registered projects
yunetas clean                 # make clean:   SDK + registered projects
yunetas test [-j N] [--serial] [--clean]
                              # make -jN install (SDK + root build/), then ctest -jN
                              # (serially on an SDK older than 7.26.3); the log is
                              # build/<date>.j<N>.txt

# External projects (registry in ~/.yuneta/projects.json, machine-local)
yunetas register-project <path>     # <path> must contain yunos/CMakeLists.txt
yunetas unregister-project <name>
yunetas list-projects
yunetas init|build|clean <name>...  # only those projects (SDK skipped)
yunetas init|build|clean --sdk-only # only the SDK

# Deploy targets (registry in ~/.yuneta/nodes.json, mode 600, no credential in it)
yunetas register-node <name> --url wss://<host>:1993 -I <issuer> -Z <client-id> -x <user>
yunetas register-node <name> --ssh yuneta@<host>   # tunnel to the node's loopback agent
yunetas unregister-node <name>
yunetas list-nodes

# Deploy (the agent tools ship inside this package, yunetas.agent_tools)
yunetas sync                  [-n|-a|...]          # binaries AND configs together (recommended)
yunetas sync-binaries         [-n|-a|--role R|...] # outputs/yunos vs the agent
yunetas sync-configs          [-n|-a|-r|...]       # auto-match batches/<host>/ to the agent's realm_ids
yunetas sync-configs --host <host> [...]          # or target one batches dir explicitly
yunetas upgrade-yunos [--no-snap|--snap-name N|-y|-n]  # find-new-yunos -> snapshot -> deactivate-snap
yunetas set-start-priorities  [-n|-a|--rule P=N]  # launch tier of each yuno, by role

# every deploy command takes --node <name> (and --tunnel) to act on a registered node

# This node
yunetas restart-agents [-n|-y|--without-spare]  # restart the agents that run a
                                # replaced binary: the main one, then the spare once
                                # the main answers
```

On a **runtime-only node** (installed from the `.deb`/`.rpm`: `outputs/`,
`outputs_ext/`, `tools/` and `.config`, but no framework sources and no
`YUNETA_VERSION`) there is no SDK to build, so `init`/`build`/`clean` with no
arguments process the registered projects only — naming them is optional.
`--sdk-only` is an error there.

The deploy commands exit with `1` when a push (or a restart they did) failed,
so a script can tell. `sync` reads it: it does not push the configs after a
failed binaries pass.

`sync-binaries --role <role>` (repeatable) pushes only those roles. Without
it, a change to one yuno can drag in every other binary that differs by a few
bytes, because the local SDK is newer than the node's. A role that the agent
does not have, or that has no local build, is an error (exit 2).


# The agents of this node

A build from source installs `yuneta_agent` and `yuneta_agent22` straight into
`/yuneta/agent`, while the old processes go on running the old binary.
`yunetas build` ends with a warning when that is the case. `yunetas
restart-agents` restarts them in the safe order:

1. It keeps the running binary as `/yuneta/agent/<agent>.bak-running-<date>`,
   because after the restart it exists nowhere else.
2. It restarts the main agent, and checks that it runs the binary on disk and
   answers a command.
3. Only then does it do the same with the spare. The spare is the way into a
   node whose main agent does not come up, so a failure leaves it alone.

When the spare does not run, the command refuses to restart the main agent:
if the main agent does not come up, the node has no agent at all. Start the
spare first, or give `--without-spare` to restart the main agent alone.

An agent in its systemd unit is restarted with `sudo -n systemctl restart`. An
agent run by hand is restarted with `--stop` and its own command line again.
Run the command as the user that owns the agents. It is never automatic: the
release suite builds on a node in a worktree of its own, and an automatic
restart would load that build into the node's agents.


# Deploy flow

Two steps: **push the artifacts, then promote them.**

```shell
# 1. Push binaries AND configs in one go (so a binary bump never ships
#    without its matching config bump — the verify-by-default footgun:
#    a new fail-closed runtime against a stale no-CA config breaks OIDC).
yunetas sync                  # = sync-binaries + sync-configs

# 2. Promote the freshly installed releases to primary and restart.
yunetas upgrade-yunos         # find-new-yunos (confirm) -> snapshot -> deactivate-snap
```

`sync` installs a new version next to the old one and does not activate it;
`upgrade-yunos` is the promote step. It previews `find-new-yunos` first and
stops there when there is nothing new, then asks, then shoots a rollback
snapshot (idempotent by name; reuses an already-active snap instead of
stacking a new one; `--no-snap` to skip), then runs `create=1`, then
`deactivate-snap` triggers `restart_nodes()` on the agent. Preview the steps
with `-n`.

A row that the agent marks `already registered, pending promotion
(deactivate-snap): create-yuno ...` (a `create=1` of an earlier run that was
never promoted, SDK 7.25.5 and later) is counted apart. It needs no
`create=1`, only the promotion:

```text
1 new yuno row(s) would be created:
  create-yuno id=gate^one ...
1 yuno row(s) already registered, pending promotion:
  already registered, pending promotion (deactivate-snap): create-yuno id=gate^two ...
...
1 created, 1 already registered.
```

When every row is already registered, `create=1` is skipped and the command
goes on to `deactivate-snap`.

For a same-version hot-patch (no `APP_VERSION` bump) you don't need
`upgrade-yunos`: `sync-binaries` stops each rebuilt yuno, overwrites its
binary and starts it again (`--no-restart` to skip that).

A config is applied in one of two ways:

- **Same version, new content** (`UPDATE`): the yuno reads it at its next
  start. `sync-configs -r` restarts the yunos that use it.
- **New version** (`BUMP`): a yuno runs the config version of its own row,
  so a restart changes nothing. `upgrade-yunos` promotes it.


# Remote nodes

Register the node once, then add `--node <name>` to any deploy command:

```shell
yunetas register-node prod --url wss://myhost:1993 \
    -I https://auth.example.com/realms/r -Z myhost -x me@example.com
export YUNETA_OAUTH_PASSW=...        # or YUNETA_OAUTH_JWT=<a token you have>
yunetas sync -n --node prod
yunetas upgrade-yunos --node prod
```

The registry stores where a node is and which identity you present, never a
credential. The password comes from `$YUNETA_OAUTH_PASSW` (and the secret of
a confidential client from `$YUNETA_OAUTH_CLIENT_SECRET`). The CLI never puts
them on a command line, where any local user reads them in `ps`: the agent
tools inherit them in the environment, and the CLI's own `ycommand` calls log
in once and carry the token.


# How to build this package

## Build and publish

`pdm` builds and publishes it. No permanent install is needed:

```shell
  # 1. Change the version in yunetas/__version__.py, write the CHANGELOG, commit
  # 2. From the source root folder:
  pipx run pdm build
  pipx run pdm publish --no-build --username __token__ --password <your-api-token>
```

PyPI never accepts a version number twice: check the built wheel before
the upload.

## Tests

The tests use `pytest` and need the packages of the CLI (typer, rich):

```shell
  python3 -m venv /tmp/venv-yunetas
  /tmp/venv-yunetas/bin/pip install typer rich pytest
  /tmp/venv-yunetas/bin/python -m pytest tests
```

## Install the package in editable mode using pip from the source root folder:

```shell
  pip install -e .
```
