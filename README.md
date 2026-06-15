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
yunetas build                 # make install: SDK + registered projects
yunetas clean                 # make clean:   SDK + registered projects
yunetas test                  # ctest

# External projects (registry in ~/.yuneta/projects.json, machine-local)
yunetas register-project <path>     # <path> must contain yunos/CMakeLists.txt
yunetas unregister-project <name>
yunetas list-projects
yunetas init|build|clean <name>...  # only those projects (SDK skipped)
yunetas init|build|clean --sdk-only # only the SDK

# Deploy helpers (wrappers over $YUNETAS_BASE/tools/agent/sync_*.py)
yunetas sync                  [-n|-a|...]          # binaries AND configs together (recommended)
yunetas sync-binaries         [-n|-a|...]          # outputs/yunos vs the local agent
yunetas sync-configs          [-n|-a|-r|...]       # auto-match batches/<host>/ to the agent's realm_ids
yunetas sync-configs --host <host> [...]          # or target one batches dir explicitly
yunetas upgrade-yunos [--no-snap|--snap-name N|-y|-n]  # snapshot -> find-new-yunos -> deactivate-snap
```


# Deploy flow

Two steps: **push the artifacts, then promote them.**

```shell
# 1. Push binaries AND configs in one go (so a binary bump never ships
#    without its matching config bump — the verify-by-default footgun:
#    a new fail-closed runtime against a stale no-CA config breaks OIDC).
yunetas sync                  # = sync-binaries + sync-configs

# 2. Promote the freshly installed releases to primary and restart.
yunetas upgrade-yunos         # snapshot -> find-new-yunos (confirm) -> deactivate-snap
```

`sync` does not restart anything by itself; `upgrade-yunos` is the promote
step. It shoots a rollback snapshot first (idempotent by name; reuses an
already-active snap instead of stacking a new one; `--no-snap` to skip), then
previews `find-new-yunos` and asks before `create=1`, then `deactivate-snap`
triggers `restart_nodes()` on the agent. Preview either step with `-n`.

For a same-version hot-patch (no `APP_VERSION` bump) you don't need
`upgrade-yunos`: `sync` then bounce the affected yunos (`kill-yuno` +
`run-yuno` / `play-yuno`).


# How build this package


## Install pdm

This package use `pdm` to build and publish.

```shell
    pip install pdm
    pip install cement
    pip install plumbum
    pip install fastapi
    pip install "uvicorn[standard]"
    pip install "typer[all]"
```

## Build and publish
```shell
  # Firstly change the version (explained below)
  # Next go to source root folder
  pdm build
  pdm publish --username __token__ --password <your-api-token> # (me: the full command is saved in publish-tui_yunetas.sh)
```

## Install the package in editable mode using pip from the source root folder:

```shell
  pip install -e .
```

## Change the version

> Edit the `__version__.py` file and change the variable `__version__`.
Then [build and publish](build-and-publish)
