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

## Version numbers: one digit per segment

Each segment of the CLI version is a single digit, 0 to 9, and they roll
over like an odometer: after `x.y.9` comes `x.(y+1).0`, after `x.9.9` comes
`(x+1).0.0` (rule of 2026-10-24: "0.23.6" had grown segments nobody reads at
a glance). The last two-digit release was **0.23.6**; the next one is
**1.0.0**, the first number above it that keeps the rule (a lower one would
sort below 0.23.6 and `pipx upgrade` would never take it). Bump the last
segment for every release; a contract change still bumps a higher one.
