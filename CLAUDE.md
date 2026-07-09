# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repo.

## ⚠️ First step: read the yunetas CLAUDE.md

**Before doing anything in this repo, read the yunetas SDK's `CLAUDE.md`.**
This repo is normally checked out as the `utils/python/tui_yunetas` git
submodule of yunetas, so it lives at `/yuneta/development/yunetas/CLAUDE.md`
(standalone clone: `github.com/artgins/yunetas`, `CLAUDE.md` at the root). It
carries the framework-wide rules that also govern this codebase:
always-braces (Python included), no silent errors, English-only committed
docs, the build/deploy/release conventions this CLI drives (`yunetas
init/build/test/clean`, `sync-binaries`, `sync-configs`, `upgrade-yunos`),
and the submodule flow. This file only adds the tui_yunetas-specific layer
on top.

## This repo in the yunetas ecosystem

- The `yunetas` CLI (Python, published to PyPI; `pipx install yunetas` for
  production use, conda env for development). Source in `yunetas/`.
- It is the canonical build/deploy interface of the SDK — behavior changes
  here must stay in sync with the flows documented in the yunetas `CLAUDE.md`
  and `docs/doc.yuneta.io/deploying-yunos.md`.
- To ship: commit on `main` here, publish to PyPI when releasing, then
  **bump the `utils/python/tui_yunetas` submodule pointer in yunetas**.
