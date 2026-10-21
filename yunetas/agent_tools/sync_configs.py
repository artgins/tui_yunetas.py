#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_configs.py — compare the yuno configs in the CURRENT DIRECTORY against what
the local yuneta_agent already has installed, and (optionally) push the
differences.

This is the config-side sibling of ``sync_binaries.py``. The two differ in how
they DISCOVER work, because configs are not centralized the way binaries are:

  * ``sync_binaries.py`` drives from ``$YUNETAS_BASE/outputs/yunos/`` — every
    built binary lives in one well-known directory.
  * Configs live scattered under each yuno's ``batches/<host>/`` directory, so
    this script drives from the CURRENT DIRECTORY. You ``cd`` into the batches
    directory holding the ``*.json`` configs you want to sync, then run it.

Identity / matching
-------------------
A config in the agent is keyed by ``(id, version)``:

  * ``id``      is supplied as a command parameter; by convention it equals the
                config FILENAME without the ``.json`` extension
                (``auth_bff.1801.json`` -> id ``auth_bff.1801``, mirroring the
                live agent ids ``scheduler_wz.5004``, ``gate_auraair.4502`` …).
  * ``version`` is NOT a parameter: the agent reads it from the ``__version__``
                field INSIDE the file content. ``__description__`` is read the
                same way. (See ``cmd_create_config`` / ``cmd_update_config`` in
                ``yunos/c/yuno_agent/src/c_agent.c``.)

So this script, for every ``*.json`` in the directory (skipping ``_*.json``
batch/deploy helpers):

  1. derives the config id from the filename,
  2. reads ``__version__`` from the file (a file without it is not a deployable
     config under the current agent contract -> skipped),
  3. looks the id up in the agent via ``ycommand -c '*list-configs'`` (the
     leading ``*`` makes ycommand emit raw JSON instead of the table) for the
     PRIMARY version, and reads every installed version from
     ``ycommand -c '*list-configs-instances'``,
  4. classifies it.

Classification
--------------
  * NEW        — id not in the agent                       -> create-config
  * BUMP       — local version not installed, > primary    -> create-config
  * INSTALLED  — local version already an installed record  -> skipped (pending
                 but not the primary (pending promote)         promote)
  * UPDATE     — same version, content changed             -> update-config
  * UP-TO-DATE — same version, identical content           -> skipped
  * DOWNGRADE  — local version  <  agent version           -> reported only, NOT pushed
  * agent-only — agent has a config absent here            -> skipped (informational)

A DOWNGRADE is never offered for install: seeding a stale version with
create-config would break the version logic, so it is reported and left alone.

Like ``*list-binaries``, ``*list-configs`` reports only the primary (id,version);
if a freshly built config's version is already created as a non-primary record,
create-config would fail "already exists". The instance list from
``*list-configs-instances`` is the authoritative "is this version already
installed?" check that guards the BUMP path (it carries no content, so a content
change to an already-installed non-primary version must be pushed manually with
update-config).

The new-version install verb is ``create-config`` (it refuses to overwrite an
existing ``(id, version)``); ``update-config`` overwrites the content of an
existing same-version record. ``create-config`` also answers to the alias
``install-config``, by analogy with ``install-binary``.

Content upload uses the same ``content64=$$(<path>)`` macro as binaries; ``$$()``
base64-encodes the file. We pass the file's absolute path so it resolves
regardless of ycommand's working directory.

Restart handling
----------------
Installing a config does NOT require stopping the yuno. This is the key
difference from a binary: ``update-binary`` fails with text-file-busy while the
yuno is running from that slot, so ``sync_binaries.py`` MUST kill first and then
must bring it back. A config push has no such constraint — it always succeeds on
a running yuno; it simply does not take effect until that yuno next (re)starts.

So by default this script only pushes, then prints the affected yuno ids (from
the agent record's ``yunos`` field; a config id is ``<role>.<yuno_id>``, and the
field lists the using yuno instance ids) as a ``kill-yuno`` + ``run-yuno``
reminder. Restarting to apply the change is a separate, optional step.

Pass ``--restart`` to also bounce the using yunos right away, scoped by yuno
``id`` (never node-wide), preserving each one's prior run/play state:

    kill-yuno id=<yuno_id>   (only if running) -> poll *list-yunos until it exits
    run-yuno id=<yuno_id> play=0   (it was running)
    play-yuno id=<yuno_id>         (only if it had been playing)

A yuno that is not running is left stopped (it reads the new config on its next
start). NEW configs have no agent record yet (typically a yuno not created here)
and are never auto-restarted — their ids are printed as a reminder.

Only an UPDATE (same version, new content) is applied by a restart. A yuno runs
the config version of its own row (``name_version``, read by
``get_yuno_config()`` in ``c_agent.c``), and a BUMP (``create-config`` of a new
version) moves that row only with ``find-new-yunos create=1`` +
``deactivate-snap``: ``yunetas upgrade-yunos``. So a BUMP is never restarted;
the tool prints that hint instead.

The exit code is 1 when a push or a restart failed, so ``yunetas sync`` and a
script can tell.

The affected yunos are restarted in ascending ``start_priority`` order (read
from the agent's ``*list-yunos`` record), so infrastructure comes back before
its dependents instead of in alphabetical id order.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from yunetas.agent_tools.common import (
    add_agent_arguments, ask, bold, cmp_versions, cyan, dim, green,
    obtain_jwt, parse_leading_json, red, set_tls_flags, ycmd_base, yellow,
)


# ----------------------------------------------------------------------------
#   JSON helpers
# ----------------------------------------------------------------------------
def strip_jsonc(text):
    """
    Remove ``//`` line comments and ``/* */`` block comments that live OUTSIDE
    of strings. Yuneta loads its configs with a non-strict parser
    (``config_gbuffer2json``) that tolerates comments, so a plain ``json.loads``
    would choke on otherwise-valid config files.
    """
    out = []
    i, n = 0, len(text)
    in_str = False
    esc = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def load_jsonc(path):
    """Load a (possibly comment-bearing) JSON config file into a dict."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(strip_jsonc(text))


# ----------------------------------------------------------------------------
#   Discovery
# ----------------------------------------------------------------------------
def local_configs(config_dir):
    """
    Return {id: {id, version, description, path, content}} for every config
    ``*.json`` in config_dir. Files starting with '_' (batch/deploy helpers such
    as ``_deploy_*.json`` / ``_update-configs.json``) are skipped, as are files
    without a ``__version__`` field (not deployable under the agent contract).

    The config id is the filename without the ``.json`` extension.
    """
    out = {}
    for name in sorted(os.listdir(config_dir)):
        if name.startswith("_") or not name.endswith(".json"):
            continue
        path = os.path.join(config_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            content = load_jsonc(path)
        except (OSError, json.JSONDecodeError) as e:
            print(red("  ! %s: cannot parse as JSON (%s), skipped" % (name, e)))
            continue
        if not isinstance(content, dict):
            print(red("  ! %s: top-level JSON is not an object, skipped" % name))
            continue
        version = content.get("__version__", "")
        if version == "" or version is None:
            print(yellow("  ! %s: no __version__ field, skipped (not a deployable config)" % name))
            continue
        cid = name[:-len(".json")]
        out[cid] = {
            "id": cid,
            "version": str(version),
            "description": content.get("__description__", ""),
            "path": os.path.abspath(path),
            "content": content,
        }
    return out


def agent_configs(ycommand, url, jwt):
    """
    Return {id: {version, description, date, zcontent, yunos}} from the agent via
    'ycommand -c *list-configs' (the '*' forces raw JSON). One record per id
    (the current primary version).
    """
    cmd = ycmd_base(ycommand, url, jwt) + ["-c", "*list-configs"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        print(red("ERROR: cannot run ycommand: %s" % e))
        sys.exit(2)
    try:
        data = parse_leading_json(res.stdout)
    except json.JSONDecodeError:
        print(red("ERROR: '*list-configs' did not return JSON. Is the agent up?"))
        print(dim(res.stdout[:500]))
        print(dim(res.stderr[:500]))
        sys.exit(2)
    if not isinstance(data, list):
        print(red("ERROR: unexpected '*list-configs' payload (not a list)."))
        sys.exit(2)
    out = {}
    for rec in data:
        cid = rec.get("id")
        if not cid:
            continue
        out[cid] = {
            "version": str(rec.get("version", "?")),
            "description": rec.get("description", ""),
            "date": rec.get("date", "?"),
            "zcontent": rec.get("zcontent", None),
            "yunos": rec.get("yunos", []),
        }
    return out


def agent_config_instances(ycommand, url, jwt):
    """
    Return {id: set(version, ...)} for EVERY installed config record, via
    'ycommand -c *list-configs-instances' (the '*' forces raw JSON).

    '*list-configs' reports only the primary (id,version); a freshly built
    config whose version is already created as a non-primary record must not be
    offered to create-config (which refuses to overwrite an existing
    (id,version)). This set is the authoritative "is this version already
    installed?". Returns {} on any error so classify() degrades gracefully.
    """
    cmd = ycmd_base(ycommand, url, jwt) + ["-c", "*list-configs-instances"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        data = parse_leading_json(res.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}
    if not isinstance(data, list):
        return {}
    out = {}
    for rec in data:
        cid = rec.get("id")
        ver = rec.get("version")
        if not cid or ver is None:
            continue
        out.setdefault(cid, set()).add(str(ver))
    return out


# ----------------------------------------------------------------------------
#   Classification
# ----------------------------------------------------------------------------
def classify(local, agent, instances):
    """
    Drive from the LOCAL configs found in the directory. For each one look it up
    in the agent and compare. Agent-only configs (present in the agent, absent
    here) are appended as informational 'orphan' rows.

    `instances` is {id: set(version)} from '*list-configs-instances'; it guards
    the NEW/BUMP paths so a version already created as a non-primary record
    (pending promote) is not offered to a doomed create-config.

    kind in {new, bump, installed, update, uptodate, downgrade, orphan}.
    """
    rows = []
    for cid, lc in sorted(local.items()):
        ac = agent.get(cid)
        already_installed = lc["version"] in instances.get(cid, set())
        if ac is None:
            # No primary at all. If the version is somehow already a record,
            # create-config would still fail; flag it as installed not new.
            rows.append({
                "id": cid,
                "kind": "installed" if already_installed else "new",
                "action": None if already_installed else "create-config",
                "local": lc, "agent": None,
            })
            continue
        cmp = cmp_versions(lc["version"], ac["version"])
        if cmp > 0:
            if already_installed:
                # Version already created as a non-primary record (primary is an
                # older one, e.g. pending promote). create-config would fail
                # "already exists"; nothing to push — it only needs promotion.
                rows.append({
                    "id": cid, "kind": "installed", "action": None,
                    "local": lc, "agent": ac,
                })
            else:
                rows.append({
                    "id": cid, "kind": "bump", "action": "create-config",
                    "local": lc, "agent": ac,
                })
        elif cmp < 0:
            # Local is OLDER than the agent. Installing it would break the
            # version logic (create-config would seed a stale version), so we
            # only report it — never offer to push it.
            rows.append({
                "id": cid, "kind": "downgrade", "action": None,
                "local": lc, "agent": ac,
            })
        else:
            # Same version. Only worth an update-config if content changed.
            if lc["content"] == ac["zcontent"]:
                rows.append({
                    "id": cid, "kind": "uptodate", "action": None,
                    "local": lc, "agent": ac,
                })
            else:
                rows.append({
                    "id": cid, "kind": "update", "action": "update-config",
                    "local": lc, "agent": ac,
                })

    for cid, ac in sorted(agent.items()):
        if cid not in local:
            rows.append({
                "id": cid, "kind": "orphan", "action": None,
                "local": None, "agent": ac,
            })
    return rows


KIND_LABEL = {
    "new":       (lambda s: green(s),  "NEW",        "create-config"),
    "bump":      (lambda s: green(s),  "BUMP",       "create-config"),
    "installed": (lambda s: cyan(s),   "INSTALLED",  "-"),
    "update":    (lambda s: yellow(s), "UPDATE",     "update-config"),
    "uptodate":  (lambda s: dim(s),    "up-to-date", "-"),
    "downgrade": (lambda s: red(s),    "DOWNGRADE",  "-"),
    "orphan":    (lambda s: dim(s),    "agent-only", "-"),
}


def print_table(rows, show_uptodate):
    print()
    print(bold("%-30s %-11s %-10s %-10s %-14s" % (
        "config id", "status", "local ver", "agent ver", "command")))
    print(dim("-" * 78))
    for r in rows:
        kind = r["kind"]
        if kind in ("uptodate", "orphan") and not show_uptodate:
            continue
        colour, label, _ = KIND_LABEL[kind]
        lv = r["local"]["version"] if r["local"] else "-"
        av = r["agent"]["version"] if r["agent"] else "-"
        action = r["action"] or "-"
        print("%-30s %s %-10s %-10s %-14s" % (
            r["id"],
            colour("%-11s" % label),
            lv, av, action,
        ))
    print()


# ----------------------------------------------------------------------------
#   Execution
# ----------------------------------------------------------------------------
def run_one(ycommand, url, jwt, action, cid, path, dry_run):
    cmd_str = "%s id='%s' content64=$$(%s)" % (action, cid, path)
    cmd = ycmd_base(ycommand, url, jwt) + ["-c", cmd_str]
    print(cyan(">> ycommand -c '%s'" % cmd_str))
    if dry_run:
        print(dim("   (dry-run, not executed)"))
        return True
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        print(red("   ERROR: %s" % e))
        return False
    out = (res.stdout or "").strip()
    err = (res.stderr or "").strip()
    if out:
        print(out)
    if err:
        print(dim(err))
    # A resumed sync re-runs create-config for a (id, version) the prior run
    # already stored; the agent answers "... already exists". That is idempotent,
    # not a failure: the config row is already there. Treat it as ok.
    already = "already exists" in out
    ok = res.returncode == 0 and ("ERROR" not in out or already)
    if already:
        print(yellow("   ALREADY PRESENT (idempotent)"))
    else:
        print(green("   OK") if ok else red("   FAILED"))
    return ok


def run_ycmd(ycommand, url, jwt, cmd_str, dry_run, timeout=120):
    """Run one `ycommand -c '<cmd_str>'`, echoing it. Returns (ok, stdout)."""
    cmd = ycmd_base(ycommand, url, jwt) + ["-c", cmd_str]
    print(cyan(">> ycommand -c '%s'" % cmd_str))
    if dry_run:
        print(dim("   (dry-run, not executed)"))
        return True, ""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        print(red("   ERROR: %s" % e))
        return False, ""
    out = (res.stdout or "").strip()
    err = (res.stderr or "").strip()
    if out:
        print(out)
    if err:
        print(dim(err))
    # Idempotent "... already exists" (resumed sync) is not a failure.
    already = "already exists" in out
    ok = res.returncode == 0 and ("ERROR" not in out or already)
    if already:
        print(yellow("   ALREADY PRESENT (idempotent)"))
    else:
        print(green("   OK") if ok else red("   FAILED"))
    return ok, out


def yuno_states_by_id(ycommand, url, jwt):
    """
    Return {yuno_id: record} for every yuno the agent manages, via '*list-yunos'.
    Each record carries yuno_running / yuno_playing. {} on any error.
    """
    cmd = ycmd_base(ycommand, url, jwt) + ["-c", "*list-yunos"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        data = parse_leading_json(res.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}
    if not isinstance(data, list):
        return {}
    out = {}
    for rec in data:
        if isinstance(rec, dict) and rec.get("id") is not None:
            out[str(rec["id"])] = rec
    return out


def wait_until_stopped(ycommand, url, jwt, yid, timeout_s=60.0, poll_s=0.3):
    """
    Poll '*list-yunos id=<yid>' until the yuno is no longer running, so a later
    run-yuno relaunches a fully-exited process. Returns True if it stopped.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        cmd = ycmd_base(ycommand, url, jwt) + ["-c", "*list-yunos id=%s" % yid]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
            data = parse_leading_json(res.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            data = []
        records = data if isinstance(data, list) else []
        if not any(isinstance(r, dict) and r.get("yuno_running") for r in records):
            return True
        time.sleep(poll_s)
    return False


def restart_yuno(ycommand, url, jwt, yid, was_running, was_playing, dry_run):
    """
    Bounce one yuno by id so it re-reads its config, restoring prior run/play
    state. A yuno that was not running is left stopped — it reads the new config
    on its next start. kill-yuno is orderly (SIGQUIT), so the gbmem audit runs.
    Returns False when a step failed: the yuno may be down.
    """
    if not was_running:
        print(dim("   %s not running — left stopped (reads new config on next start)" % yid))
        return True
    ok, _ = run_ycmd(ycommand, url, jwt, "kill-yuno id=%s" % yid, dry_run)
    if not dry_run and not wait_until_stopped(ycommand, url, jwt, yid):
        print(yellow("   ! %s still running after kill" % yid))
    restored, _ = run_ycmd(ycommand, url, jwt, "run-yuno id=%s play=0" % yid, dry_run)
    ok = ok and restored
    if was_playing:
        restored, _ = run_ycmd(ycommand, url, jwt, "play-yuno id=%s" % yid, dry_run)
        ok = ok and restored
    return ok


def sort_pushed_configs(pushed):
    """
    Split the configs pushed with success by what applies them. Returns
    (restart_ids, promote_ids, new_ids):

      * restart_ids  yuno ids using an UPDATEd config (same version, new
                     content): a restart makes them read it.
      * promote_ids  config ids of a BUMP (create-config of a new version).
                     A yuno runs the config version of its OWN row
                     (name_version, see get_yuno_config() in c_agent.c), which
                     only find-new-yunos create=1 + deactivate-snap move:
                     restarting it would bring it back on the old version.
      * new_ids      config ids with no agent record yet (NEW).
    """
    restart_ids = set()
    promote_ids = set()
    new_ids = set()
    for r in pushed:
        if r["kind"] == "update":
            for y in r["agent"].get("yunos", []) or []:
                restart_ids.add(str(y))
        elif r["kind"] == "bump":
            promote_ids.add(r["id"])
        else:
            new_ids.add(r["id"])
    return restart_ids, promote_ids, new_ids


# ----------------------------------------------------------------------------
#   Main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Compare the configs in a directory with the agent and push updates.")
    ap.add_argument("config_dir", nargs="?", default=".",
                    help="directory holding the *.json configs (default: current dir).")
    add_agent_arguments(ap)
    ap.add_argument("-a", "--all", action="store_true",
                    help="apply every candidate without asking per-config.")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="show what would run for every candidate, execute "
                         "nothing, ask nothing.")
    ap.add_argument("--show-uptodate", action="store_true",
                    help="also list configs already in sync and agent-only ones.")
    ap.add_argument("-r", "--restart", action="store_true",
                    help="after pushing a changed config of the SAME version "
                         "(UPDATE), also restart the using yunos to apply it "
                         "(default: push only + print a reminder). Installing a "
                         "config never needs a kill; the restart is optional. A "
                         "new version (BUMP) is applied by 'yunetas upgrade-yunos', "
                         "never by a restart.")
    args = ap.parse_args()
    set_tls_flags(args)

    ycommand = args.ycommand or shutil.which("ycommand")
    if not ycommand:
        print(red("ERROR: ycommand not found in PATH (use --ycommand)."))
        sys.exit(2)

    config_dir = os.path.abspath(args.config_dir)
    if not os.path.isdir(config_dir):
        print(red("ERROR: config dir not found: %s" % config_dir))
        sys.exit(2)

    jwt = obtain_jwt(args)

    print(dim("config dir : %s" % config_dir))
    print(dim("ycommand   : %s%s%s" % (
        ycommand,
        ("  url=" + args.url) if args.url else "",
        "  oauth2=on" if jwt else "")))

    print(dim("\nreading agent configs (*list-configs)..."))
    agent = agent_configs(ycommand, args.url, jwt)
    print(dim("reading installed records (*list-configs-instances)..."))
    instances = agent_config_instances(ycommand, args.url, jwt)
    print(dim("reading local configs (*.json in dir)..."))
    local = local_configs(config_dir)

    if not local:
        print(yellow("\nNo deployable *.json configs found in %s." % config_dir))
        return 0

    return _sync_body(args, ycommand, jwt, local, agent, instances)


def _sync_body(args, ycommand, jwt, local, agent, instances):
    """
    Compare the local configs with the agent's, confirm, and push. Returns
    the exit code: 1 when a push or a restart failed.
    """

    rows = classify(local, agent, instances)
    print_table(rows, show_uptodate=args.show_uptodate or args.dry_run)

    installed = [r for r in rows if r["kind"] == "installed"]
    if installed:
        print(yellow(
            "%d config(s) already installed but NOT primary (pending "
            "promote)." % len(installed)))
        print(dim("Promote the staged version(s) with:  yunetas upgrade-yunos"))

    candidates = [r for r in rows if r["action"]]
    if not candidates:
        if not installed:
            print(green("Everything is up to date. Nothing to do."))
        return 0

    # Summary line.
    by_kind = {}
    for r in candidates:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    summary = ", ".join("%d %s" % (n, k) for k, n in sorted(by_kind.items()))
    print(bold("%d candidate(s): %s" % (len(candidates), summary)))

    downgrades = [r for r in rows if r["kind"] == "downgrade"]
    if downgrades:
        print(red("Note: %d config(s) are OLDER locally than in the agent — reported, NOT pushed:" %
                  len(downgrades)))
        for r in downgrades:
            print(red("   %s  local %s < agent %s" %
                      (r["id"], r["local"]["version"], r["agent"]["version"])))

    # Decide which to apply. A dry run asks nothing: it shows the command of
    # every candidate and runs none. Up to 0.23.0 it asked "Apply [a]ll...?",
    # and over ssh from a background job, whose stdin stays open, it waited
    # for an answer for ever.
    chosen = []
    if args.all or args.dry_run:
        chosen = candidates
    else:
        mode = ask("\nApply [a]ll, [s]elect one by one, or [q]uit? ")
        if mode in ("q", "quit", ""):
            print("Cancelled - no changes made.")
            return 0
        if mode in ("a", "all"):
            chosen = candidates
        else:
            for r in candidates:
                colour, label, _ = KIND_LABEL[r["kind"]]
                ans = ask("  %s  [%s -> %s]  apply? [y/N] " % (
                    r["id"], colour(label), r["action"]))
                if ans in ("y", "yes"):
                    chosen.append(r)

    if not chosen:
        print("Nothing selected.")
        return 0

    if not args.all and not args.dry_run:
        confirm = ask("\nAbout to run %d command(s) against the agent. Proceed? [y/N] "
                      % len(chosen))
        if confirm not in ("y", "yes"):
            print("Cancelled - no changes made.")
            return 0

    print()
    ok, fail = 0, 0
    pushed = []
    for r in chosen:
        if run_one(ycommand, args.url, jwt, r["action"], r["id"], r["local"]["path"], args.dry_run):
            ok += 1
            pushed.append(r)
        else:
            fail += 1
    print()
    print(bold("Done: %s, %s." % (green("%d ok" % ok), red("%d failed" % fail) if fail else dim("0 failed"))))
    if args.dry_run:
        print(dim("(dry run: the commands above were shown, none was executed)"))

    # A yuno reads its config only at (re)start, and only the version of its
    # own row: an UPDATE is applied by a restart, a BUMP only by promoting it.
    # Restarts are scoped by yuno id and keep the prior run/play state. NEW
    # configs have no agent record yet (typically a yuno not created here)
    # -> reminder only.
    affected, promote, new_only = sort_pushed_configs(pushed)

    if affected and args.restart:
        if args.dry_run:
            print(dim("\nThe affected yuno(s) would be restarted to apply the new config(s):"))
        else:
            print(dim("\nRestarting affected yuno(s) to apply the new config(s)..."))
        states = yuno_states_by_id(ycommand, args.url, jwt)

        # Restart in ascending start_priority order (the agent owns this number)
        # so infrastructure comes back before its dependents. Default 5 for
        # yunos that predate the column.
        def _start_priority(yid):
            try:
                return int(states.get(yid, {}).get("start_priority", 5))
            except (TypeError, ValueError):
                return 5

        for yid in sorted(affected, key=lambda y: (_start_priority(y), y)):
            st = states.get(yid, {})
            if not restart_yuno(
                ycommand, args.url, jwt, yid,
                bool(st.get("yuno_running")), bool(st.get("yuno_playing")),
                args.dry_run,
            ):
                print(red("   ! %s: the restart failed, the yuno may be down" % yid))
                fail += 1
    elif affected:
        print(dim("\nNote: a yuno reads its config when it (re)starts. For the change to take"))
        print(dim("effect, restart the yunos that use it: kill-yuno then run-yuno."))
        print(dim("   affected yuno id(s): %s" % ", ".join(sorted(affected))))

    if promote:
        if args.dry_run:
            print(dim("\nNote: create-config would store a NEW version of %s." % ", ".join(sorted(promote))))
        else:
            print(dim("\nNote: create-config stored a NEW version of %s." % ", ".join(sorted(promote))))
        print(dim("A yuno runs the config version of its own row, so a restart changes nothing."))
        print(dim("Promote it with:"))
        print(dim("   yunetas upgrade-yunos              (shoot-snap -> find-new-yunos -> deactivate-snap)"))

    if new_only:
        print(dim("\nNote: NEW config(s) %s — start their yuno(s) when ready." %
                  ", ".join(sorted(new_only))))

    # The exit code is what `yunetas sync` and scripts read.
    if fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
