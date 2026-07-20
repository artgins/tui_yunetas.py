import typer
from rich import print
from rich.console import Console
from .__version__ import __version__
from .my_venv import app_venv
from typing import Optional, List
from pathlib import Path
import json
import os
import re
import socket
import sys
import subprocess
import shutil
import time
import atexit
from datetime import datetime

# # Check if YUNETAS_BASE is set, or derive it from the current directory if YUNETA_VERSION exists
# YUNETAS_BASE = os.getenv("YUNETAS_BASE")
# current_dir = os.getcwd()
# yuneta_version_path = os.path.join(current_dir, "YUNETA_VERSION")
#
# if not YUNETAS_BASE:
#     if os.path.isfile(yuneta_version_path):
#         YUNETAS_BASE = current_dir
#         print(f"[yellow]YUNETAS_BASE not set. Using current directory as YUNETAS_BASE: {YUNETAS_BASE}[/yellow]")
#     else:
#         print("[red]Error: YUNETAS_BASE environment variable is not set and YUNETA_VERSION file not found in the current directory.[/red]")
#         sys.exit(1)
#
# if not os.path.isdir(YUNETAS_BASE):
#     print(f"[red]Error: YUNETAS_BASE '{YUNETAS_BASE}' does not exist or is not a directory.[/red]")
#     sys.exit(1)


# 1) ENV, 2) /yuneta/development/yunetas, 3) /yuneta/development, else fail
env_base = os.environ.get("YUNETAS_BASE")

candidates = []
if env_base:
    candidates.append(env_base)
candidates += ["/yuneta/development/yunetas", "/yuneta/development"]

YUNETAS_BASE = next((p for p in candidates if p and os.path.isdir(p)), None)

# Recap printed at the end of init/build/clean. Informational lines go ONLY
# here (never printed as they happen): the recap is the single place the user
# reads them, and printing both duplicated the whole setup block per command.
# The menuconfig warning is appended by setup_yuneta_environment() when the
# framework sources are present — a runtime-only node has no menuconfig to run.
final_messages = []

compiler = ""

# Warn if ENV was set but invalid
if env_base and (not os.path.isdir(env_base)):
    msg = f"[yellow]Warning: YUNETAS_BASE is set to '{env_base}' but it is not a directory. Falling back...[/yellow]"
    print(msg)
    final_messages.append(msg)

if not YUNETAS_BASE:
    print("[red]Error: Could not determine YUNETAS_BASE. "
          "Set the YUNETAS_BASE environment variable to a valid directory, "
          "or ensure /yuneta/development[/yunetas] exists.[/red]", file=sys.stderr)
    sys.exit(1)

# Don't print here: this module runs on every invocation, including the
# shell-completion one, whose COMPREPLY is captured from the command's stdout —
# a line printed here (stdout or, when redirected, either stream) turns into a
# bogus completion candidate. The base is still recapped by final_messages at
# the end of init/build/clean, which is where it is actually useful.
msg = f"Using [green]YUNETAS_BASE[/green] at {YUNETAS_BASE}"
final_messages.append(msg)

# If you also want to verify a specific file exists (like the CMake case):
# required = os.path.join(YUNETAS_BASE, "tools", "cmake", "project.cmake")
# if not os.path.isfile(required):
#     print(f"[red]Error: Missing required file: {required}[/red]", file=sys.stderr)
#     sys.exit(1)

# Registry of external projects (built after the SDK). This is runtime/usage
# state, NOT part of any source checkout, so it lives in the user's home
# (~/.yuneta/projects.json), independent of YUNETAS_BASE.
# Format: {"projects": [{"name": ..., "path": ...}]}
YUNETA_USER_DIR = os.path.join(os.path.expanduser("~"), ".yuneta")
PROJECTS_REGISTRY_PATH = os.path.join(YUNETA_USER_DIR, "projects.json")

# Nodes this machine deploys to (~/.yuneta/nodes.json), so a deploy is
# `--node <name>` instead of re-typing a url plus four OAuth2 flags.
#
# NO SECRET EVER GOES IN HERE. The registry holds the identity of a node
# (where it is, which issuer and client it trusts, which user we log in as)
# and nothing you would mind reading out loud. Passwords and client secrets
# come from the environment at call time; putting them in a file that exists
# to be listed and shared is how credentials leak.
NODES_REGISTRY_PATH = os.path.join(YUNETA_USER_DIR, "nodes.json")

# Secret overlays, per registered node: ~/.yuneta/secrets/<node>/<config-id>.json
# Holds ONLY the credential fields; the shape of the config stays versioned in
# the project repo, declaring each one as "__SECRET__". This is the one place
# in the deploy path that legitimately holds secrets, so it is 0700/0600 and
# lives outside every git tree.
SECRETS_DIR = os.path.join(YUNETA_USER_DIR, "secrets")

# Env vars consulted for the credentials the registry deliberately omits.
ENV_OAUTH_PASSW = "YUNETA_OAUTH_PASSW"
ENV_OAUTH_CLIENT_SECRET = "YUNETA_OAUTH_CLIENT_SECRET"
ENV_OAUTH_JWT = "YUNETA_OAUTH_JWT"

# Soft migration from the legacy in-tree location ($YUNETAS_BASE/.projects.json).
# Done once: if the old file exists and the new one does not, move it across.
_LEGACY_REGISTRY_PATH = os.path.join(YUNETAS_BASE, ".projects.json")
if os.path.isfile(_LEGACY_REGISTRY_PATH) and not os.path.isfile(PROJECTS_REGISTRY_PATH):
    try:
        os.makedirs(YUNETA_USER_DIR, exist_ok=True)
        shutil.move(_LEGACY_REGISTRY_PATH, PROJECTS_REGISTRY_PATH)
        print(f"[yellow]Migrated project registry: "
              f"{_LEGACY_REGISTRY_PATH} -> {PROJECTS_REGISTRY_PATH}[/yellow]")
    except Exception as e:
        print(f"[yellow]Warning: could not migrate project registry "
              f"from {_LEGACY_REGISTRY_PATH}: {e}[/yellow]")

# Directories to process
DIRECTORIES = [
    "kernel/c/gobj-c",
    "kernel/c/ytls",
    "kernel/c/libjwt",
    "kernel/c/yev_loop",
    "kernel/c/timeranger2",
    "kernel/c/root-linux",
    "kernel/c/root-esp32",
    "modules/c/*",
    "utils/c/*",
    "yunos/c/*",
    "stress/c/*",
    "performance/c/*",
]

# Create the app.
app = typer.Typer(help="TUI for yunetas SDK")
app.add_typer(app_venv, name="venv")

console = Console()


@app.command()
def init(
    projects: Optional[List[str]] = typer.Argument(
        None, help="Initialize only these registered projects (the SDK is skipped)."
    ),
    sdk_only: bool = typer.Option(
        False, "--sdk-only", help="Initialize only the yunetas SDK, skip registered projects."
    ),
):
    """
    Initialize yunetas, create build directories and get compiler and build type from .config (menuconfig).
    Registered projects (see register-project) are initialized after the SDK.
    """
    include_sdk, selected_projects = resolve_selection(projects, sdk_only)

    failed = []

    if include_sdk:
        setup_yuneta_environment(True)
        failed += process_directories(DIRECTORIES)
        failed += process_directories(["."])
    else:
        # Ensure outputs/include headers are up to date without wiping outputs
        setup_yuneta_environment(False)

    for project in selected_projects:
        print(f"[cyan]Project: {project['name']} ({project['path']})[/cyan]")
        project_failed = process_directories([project_yunos_dir(project)])
        failed += project_failed
        if not project_failed:
            final_messages.append(f"Project [cyan]{project['name']}[/cyan] initialized.")

    global compiler
    final_messages.append(f"\n[yellow]Compiler selected[/yellow]: [blue]{compiler}[/blue]\n")

    #
    #   Never claim success on top of a failed cmake. Saying "init done" and
    #   exiting 0 there is what let a glibc mismatch look like a clean run:
    #   the reason scrolls past, the recap contradicts it, and the build only
    #   breaks later with "No rule to make target 'install'".
    #
    if failed:
        final_messages.append(
            f"[red]init[/red] FAILED: cmake did not configure "
            f"{len(failed)} director{'y' if len(failed) == 1 else 'ies'}. "
            f"Read the error above; no build directory is usable until it is fixed.\n"
        )
        for dir_path in failed:
            final_messages.append(f"  [red]-[/red] {dir_path}")
        print("\n".join(final_messages))
        raise typer.Exit(code=1)

    final_messages.append(f"[yellow]init[/yellow] done: created build directories, got compiler and build type from .config ([blue]menuconfig[/blue])\n")
    print("\n".join(final_messages))


def ensure_ext_libs_installed():
    """
    Guard before building: verify the installed external libraries match the
    version declared in configure-libs.sh (its `VERSION="…"` vs the
    `VERSION_INSTALLED.txt` written by the last successful install). A mismatch
    means `kernel/c/linux-ext-libs` was bumped but not rebuilt/reinstalled, so
    the SDK (and projects) would link against a stale `outputs_ext/`.

    Skipped on runtime-only (.deb/.rpm sparse SDK) nodes, which ship prebuilt
    external libs and no `linux-ext-libs` source.
    """
    ext_dir = os.path.join(YUNETAS_BASE, "kernel", "c", "linux-ext-libs")
    configure = os.path.join(ext_dir, "configure-libs.sh")
    installed = os.path.join(ext_dir, "VERSION_INSTALLED.txt")

    if not os.path.isfile(configure):
        return  # runtime-only node: no ext-libs source to check

    required = None
    try:
        with open(configure, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r'^VERSION="([^"]+)"', line)
                if m:
                    required = m.group(1).strip()
                    break
    except OSError:
        return  # unreadable: don't block the build
    if not required:
        return  # couldn't parse the declared version: don't block

    current = None
    if os.path.isfile(installed):
        try:
            with open(installed, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        current = line
                        break
        except OSError:
            current = None

    if current == required:
        return

    if current is None:
        detail = "the external libraries have not been built yet"
    else:
        detail = f"installed [red]{current}[/red] != required [green]{required}[/green]"
    print(
        f"[red]Error: linux-ext-libs is out of date ({detail}).[/red]\n"
        f"[yellow]Rebuild the external libraries before building:[/yellow]\n"
        f"    cd {ext_dir} && ./extrae.sh && ./configure-libs.sh"
    )
    raise typer.Exit(code=1)


@app.command()
def build(
    projects: Optional[List[str]] = typer.Argument(
        None, help="Build only these registered projects (the SDK is skipped)."
    ),
    sdk_only: bool = typer.Option(
        False, "--sdk-only", help="Build only the yunetas SDK, skip registered projects."
    ),
):
    """
    Build and install yunetas, then the registered projects (see register-project).
    """
    include_sdk, selected_projects = resolve_selection(projects, sdk_only)

    # Refuse to build against a stale outputs_ext/ (linux-ext-libs bumped but
    # not reinstalled): configure-libs.sh VERSION must match VERSION_INSTALLED.txt.
    ensure_ext_libs_installed()

    setup_yuneta_environment(False)

    if include_sdk:
        process_build_command(DIRECTORIES, ["make", "install"])

    for project in selected_projects:
        yunos_dir = project_yunos_dir(project)
        if not os.path.isdir(os.path.join(yunos_dir, "build")):
            print(f"[red]Error: '{yunos_dir}/build' not found. Run 'yunetas init {project['name']}' first.[/red]")
            raise typer.Exit(code=1)
        print(f"[cyan]Project: {project['name']} ({project['path']})[/cyan]")
        process_build_command([yunos_dir], ["make", "install"])
        final_messages.append(f"Project [cyan]{project['name']}[/cyan] built.")

    final_messages.append(f"\n[yellow]build[/yellow] done.\n")
    print("\n".join(final_messages))


@app.command()
def clean(
    projects: Optional[List[str]] = typer.Argument(
        None, help="Clean only these registered projects (the SDK is skipped)."
    ),
    sdk_only: bool = typer.Option(
        False, "--sdk-only", help="Clean only the yunetas SDK, skip registered projects."
    ),
):
    """
    Clean up build directories in yunetas and in the registered projects.
    """
    include_sdk, selected_projects = resolve_selection(projects, sdk_only)

    if include_sdk:
        process_build_command(DIRECTORIES, ["make", "clean"])

    for project in selected_projects:
        print(f"[cyan]Project: {project['name']} ({project['path']})[/cyan]")
        process_build_command([project_yunos_dir(project)], ["make", "clean"])

    final_messages.append(f"\n[yellow]clean[/yellow] done.\n")
    print("\n".join(final_messages))


@app.command(name="register-project")
def register_project(
    path: str = typer.Argument(..., help="Project root directory (must contain yunos/CMakeLists.txt)."),
    name: Optional[str] = typer.Option(
        None, "--name", help="Registry name (default: basename of the directory)."
    ),
):
    """
    Register an external project so init/build/clean/sync-configs also process it.
    The registry lives in ~/.yuneta/projects.json (machine-local).
    """
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        print(f"[red]Error: '{abs_path}' does not exist or is not a directory.[/red]")
        raise typer.Exit(code=1)

    cmake_file = os.path.join(abs_path, "yunos", "CMakeLists.txt")
    if not os.path.isfile(cmake_file):
        print(f"[red]Error: '{cmake_file}' not found: not a buildable yuneta project.[/red]")
        raise typer.Exit(code=1)

    project_name = name or os.path.basename(abs_path.rstrip("/"))
    registered = load_registered_projects()
    for p in registered:
        if p["name"] == project_name:
            print(f"[red]Error: project '{project_name}' already registered -> {p['path']}[/red]")
            raise typer.Exit(code=1)
        if p["path"] == abs_path:
            print(f"[red]Error: '{abs_path}' already registered as '{p['name']}'.[/red]")
            raise typer.Exit(code=1)

    registered.append({"name": project_name, "path": abs_path})
    save_registered_projects(registered)
    print(f"[green]Registered project '{project_name}' -> {abs_path}[/green]")


@app.command(name="unregister-project")
def unregister_project(
    name: str = typer.Argument(..., help="Registered project name (or its path)."),
):
    """
    Remove a project from the registry (the project tree is NOT touched).
    """
    registered = load_registered_projects()
    abs_path = os.path.abspath(name)
    remaining = [p for p in registered if p["name"] != name and p["path"] != abs_path]
    if len(remaining) == len(registered):
        known = ", ".join(sorted(p["name"] for p in registered)) or "(none)"
        print(f"[red]Error: project '{name}' is not registered. Registered: {known}[/red]")
        raise typer.Exit(code=1)

    save_registered_projects(remaining)
    print(f"[green]Unregistered project '{name}'.[/green]")


@app.command(name="list-projects")
def list_projects():
    """
    List the registered projects.
    """
    registered = load_registered_projects()
    if not registered:
        print("[yellow]No projects registered. Use 'yunetas register-project <path>'.[/yellow]")
        return

    for p in registered:
        yunos_dir = project_yunos_dir(p)
        if os.path.isfile(os.path.join(yunos_dir, "CMakeLists.txt")):
            state = "[green]ok[/green]"
        else:
            state = "[red]missing yunos/CMakeLists.txt[/red]"
        print(f"  [cyan]{p['name']:<20}[/cyan] {p['path']}  {state}")


@app.command(name="register-node")
def register_node(
    name: str = typer.Argument(..., help="Short name to use with --node (e.g. 'controlador')."),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Agent url reachable from here, e.g. wss://host:1993."
    ),
    ssh: Optional[str] = typer.Option(
        None, "--ssh", help="SSH target (user@host) to tunnel to the node's local agent port."
    ),
    agent_port: int = typer.Option(
        1991, "--agent-port", help="Node-side agent port to tunnel to (default 1991)."
    ),
    issuer: Optional[str] = typer.Option(
        None, "--issuer", "-I", help="OIDC issuer (wss:// nodes only)."
    ),
    client_id: Optional[str] = typer.Option(
        None, "--client-id", "-Z", help="OAuth2 client_id (wss:// nodes only)."
    ),
    user_id: Optional[str] = typer.Option(
        None, "--user-id", "-x", help="OAuth2 username (wss:// nodes only)."
    ),
):
    """
    Register a node so deploys can say '--node <name>' instead of repeating a
    url and four OAuth2 flags. The registry lives in ~/.yuneta/nodes.json.

    Give --url for a node whose agent is reachable from here (typically
    wss:// on 1993), or --ssh for one whose agent listens only on loopback
    (ws:// on 1991, the default and safer posture): the deploy then forwards a
    local port over SSH. With both, --url wins unless the command is given
    --tunnel.

    NO PASSWORD IS STORED. This file records where a node is and which
    identity we present, never a credential. Supply the secret at call time
    via $YUNETA_OAUTH_PASSW, $YUNETA_OAUTH_CLIENT_SECRET or $YUNETA_OAUTH_JWT.
    """
    if not url and not ssh:
        print("[red]Error: give --url (reachable agent) or --ssh (tunnel), or both.[/red]")
        raise typer.Exit(code=1)

    nodes = load_registered_nodes()
    if any(n.get("name") == name for n in nodes):
        print(f"[red]Error: node '{name}' is already registered.[/red]")
        raise typer.Exit(code=1)

    node = {"name": name}
    for key, value in (
        ("url", url),
        ("ssh", ssh),
        ("issuer", issuer),
        ("client_id", client_id),
        ("user_id", user_id),
    ):
        if value:
            node[key] = value
    if ssh and agent_port != 1991:
        node["agent_port"] = agent_port

    nodes.append(node)
    save_registered_nodes(nodes)
    print(f"[green]Registered node '{name}'.[/green]")
    if url and url.startswith("wss://") and not issuer:
        print("[yellow]Note: no --issuer stored; a wss:// agent will need the "
              "OAuth2 flags passed by hand.[/yellow]")


@app.command(name="unregister-node")
def unregister_node(
    name: str = typer.Argument(..., help="Registered node name."),
):
    """
    Remove a node from the registry (the node itself is NOT touched).
    """
    nodes = load_registered_nodes()
    remaining = [n for n in nodes if n.get("name") != name]
    if len(remaining) == len(nodes):
        known = ", ".join(sorted(n.get("name", "?") for n in nodes)) or "(none)"
        print(f"[red]Error: node '{name}' is not registered. Registered: {known}[/red]")
        raise typer.Exit(code=1)

    save_registered_nodes(remaining)
    print(f"[green]Unregistered node '{name}'.[/green]")


@app.command(name="list-nodes")
def list_nodes():
    """
    List the registered deploy targets.
    """
    nodes = load_registered_nodes()
    if not nodes:
        print("[yellow]No nodes registered. Use 'yunetas register-node <name> --url ... | --ssh ...'.[/yellow]")
        return

    for n in nodes:
        access = n.get("url") or f"ssh:{n.get('ssh')}"
        if n.get("url") and n.get("ssh"):
            access += f"  (or ssh:{n['ssh']} with --tunnel)"
        identity = ""
        if n.get("user_id") or n.get("issuer"):
            identity = f"  [dim]{n.get('user_id', '?')} @ {n.get('issuer', '?')}[/dim]"
        print(f"  [cyan]{n.get('name', '?'):<20}[/cyan] {access}{identity}")


@app.command(name="list-secrets")
def list_secrets(
    node: Optional[str] = typer.Option(
        None, "--node", "-N", help="Only this registered node (default: all)."
    ),
):
    """
    List which configs have a secret overlay on this machine, and WHICH FIELDS
    each one supplies. Values are never read or printed.

    There is deliberately no 'set-secret' command: it would put the credential
    in your shell history and in the process table, where every other user of
    the machine can read it. Write the overlay with an editor instead:

      mkdir -p ~/.yuneta/secrets/<node> && chmod 700 ~/.yuneta/secrets/<node>
      $EDITOR ~/.yuneta/secrets/<node>/<config-id>.json   # then chmod 600

    The file holds ONLY the secret fields, in the same shape as the config:

      {"global": {"smtp_password": "…"}}
    """
    nodes = [node] if node else sorted(
        n.get("name") for n in load_registered_nodes() if n.get("name")
    )
    if not nodes:
        print("[yellow]No nodes registered.[/yellow]")
        return

    def field_paths(value, prefix=""):
        if isinstance(value, dict):
            out = []
            for k, v in value.items():
                out += field_paths(v, f"{prefix}.{k}" if prefix else k)
            return out
        return [prefix]

    found_any = False
    for name in nodes:
        directory = node_secrets_dir(name)
        if not directory:
            continue
        entries = sorted(f for f in os.listdir(directory) if f.endswith(".json"))
        if not entries:
            continue
        found_any = True
        print(f"[cyan]{name}[/cyan]  [dim]{directory}[/dim]")
        for entry in entries:
            path = os.path.join(directory, entry)
            mode = oct(os.stat(path).st_mode & 0o777)[2:]
            warn = "" if mode == "600" else f"  [red]mode {mode}, expected 600[/red]"
            try:
                with open(path) as f:
                    data = json.load(f)
                fields = ", ".join(field_paths(data)) or "(empty)"
            except Exception as e:
                fields = f"[red]unreadable: {e}[/red]"
            print(f"    {entry[:-len('.json')]:<30} {fields}{warn}")

    if not found_any:
        print("[yellow]No secret overlays. Configs needing one declare it as "
              '"__SECRET__" and the push refuses until it is supplied.[/yellow]')


@app.command(
    name="sync-binaries",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def sync_binaries(
    ctx: typer.Context,
    node: Optional[str] = typer.Option(
        None, "--node", "-N", help="Registered node to deploy to (see 'yunetas list-nodes')."
    ),
    tunnel: bool = typer.Option(
        False, "--tunnel", help="Force the node's SSH tunnel even if it also has a url."
    ),
):
    """
    Compare outputs/yunos binaries with an agent and push updates.

    Targets the local agent by default; '--node <name>' resolves a registered
    node's url and OAuth2 identity (and opens its SSH tunnel when that is how
    it is reached). Wrapper over tools/agent/sync_binaries.py: every other
    argument is forwarded (e.g. -n dry-run, -a all, --no-restart).
    """
    with resolve_node_connection(node, None, tunnel) as conn:
        extra = conn.args() if node else []
        ret = run_agent_tool("sync_binaries.py", list(ctx.args) + extra)
    if ret == 0 and not ({"-n", "--dry-run"} & set(ctx.args)):
        print("[dim]Reminder: now sync the matching configs ('yunetas sync-configs', "
              "or 'yunetas sync' to push both) — a new binary against a stale config "
              "is the verify-by-default footgun.[/dim]")
    raise typer.Exit(code=ret)


@app.command(
    name="sync-configs",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def sync_configs(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(
        None, "--host", help="Sync only this batches/<host>/ directory (overrides realm auto-match)."
    ),
    project: Optional[List[str]] = typer.Option(
        None, "--project", "-p", help="Restrict to these registered projects (default: all)."
    ),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="ycommand url (default: ws://127.0.0.1:1991), used for realm auto-match and forwarded to the sync."
    ),
    node: Optional[str] = typer.Option(
        None, "--node", "-N", help="Registered node to deploy to (see 'yunetas list-nodes')."
    ),
    tunnel: bool = typer.Option(
        False, "--tunnel", help="Force the node's SSH tunnel even if it also has a url."
    ),
):
    """
    Sync yuno configs of each registered project (yunos/batches/<host>/) against
    the local agent.

    Without --host, each project's batches/<host>/ directories are matched
    against the realm_ids the local agent manages ('*list-realms'): every dir
    whose name is a (non-disabled) realm_id is synced automatically. Since a
    batches dir is named after its realm_id (the deploy FQDN), a node running
    several realms syncs all the relevant ones in one go. If the agent can't be
    reached, it falls back to the legacy single-hostname guess.

    Wrapper over tools/agent/sync_configs.py: unknown arguments are forwarded
    (e.g. -n dry-run, -a all, -r restart, OAuth2 options).
    """
    _, selected_projects = resolve_selection(project, False)
    if not selected_projects:
        print("[yellow]No projects registered. Use 'yunetas register-project <path>'.[/yellow]")
        raise typer.Exit(code=1)

    with resolve_node_connection(node, url, tunnel) as conn:
        forwarded = list(ctx.args)
        if node:
            forwarded += conn.args()
            secrets = node_secrets_dir(node)
            if secrets:
                forwarded += ["--secrets-dir", secrets]
        elif url:
            forwarded += ["-u", url]

        # The realm auto-match queries the SAME agent we are about to push to,
        # so it must go through the tunnel too, not to the local default.
        exit_code, synced = push_configs(selected_projects, host, conn.url, forwarded)

    if synced == 0:
        print("[yellow]Nothing synced: no registered project has a matching batches/<host>/ directory.[/yellow]")
        raise typer.Exit(code=1)
    raise typer.Exit(code=exit_code)


@app.command(
    name="sync",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def sync(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(
        None, "--host", help="Sync configs only for this batches/<host>/ directory (overrides realm auto-match)."
    ),
    project: Optional[List[str]] = typer.Option(
        None, "--project", "-p", help="Restrict to these registered projects (default: all)."
    ),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="ycommand url (default: ws://127.0.0.1:1991)."
    ),
    node: Optional[str] = typer.Option(
        None, "--node", "-N", help="Registered node to deploy to (see 'yunetas list-nodes')."
    ),
    tunnel: bool = typer.Option(
        False, "--tunnel", help="Force the node's SSH tunnel even if it also has a url."
    ),
):
    """
    Push binaries AND configs together against the local agent.

    A binary bump must never ship without its matching config bump: a new
    runtime against a stale config is exactly what broke OIDC under
    verify-by-default (new fail-closed binary, old no-CA config). 'sync'
    couples the two steps so neither is forgotten.

    Runs 'sync-binaries' then 'sync-configs'. Shared extra args (e.g. -n
    dry-run, -a all, OAuth2 options) are forwarded to BOTH tools; use the
    individual commands for tool-specific flags (--no-restart, -r, --yunos-dir).
    After 'sync', run 'upgrade-yunos' to promote the new releases.
    """
    _, selected_projects = resolve_selection(project, False)
    if not selected_projects:
        print("[yellow]No projects registered. Use 'yunetas register-project <path>'.[/yellow]")
        raise typer.Exit(code=1)

    # One connection for BOTH pushes: with a tunnelled node this also means a
    # single SSH session, and — more importantly — binaries and configs cannot
    # end up aimed at different agents.
    with resolve_node_connection(node, url, tunnel) as conn:
        forwarded = list(ctx.args)
        if node:
            forwarded += conn.args()
        elif url:
            forwarded += ["-u", url]

        # Binaries have no secret overlay; only the config push takes one.
        config_args = list(forwarded)
        secrets = node_secrets_dir(node)
        if secrets:
            config_args += ["--secrets-dir", secrets]

        # 1) Binaries first. If the push fails, do NOT proceed to configs: that
        #    would leave binaries and configs out of step — the very thing 'sync'
        #    exists to prevent.
        print("[cyan]== sync binaries ==[/cyan]")
        ret = run_agent_tool("sync_binaries.py", forwarded)
        if ret != 0:
            print("[red]sync-binaries failed; not syncing configs (would leave binaries and configs out of step).[/red]")
            raise typer.Exit(code=ret)

        # 2) Then configs.
        print("[cyan]== sync configs ==[/cyan]")
        exit_code, synced = push_configs(selected_projects, host, conn.url, config_args)

    if synced == 0:
        print("[yellow]Binaries synced, but no matching batches/<host>/ directory to sync configs from.[/yellow]")
    raise typer.Exit(code=exit_code)


@app.command(name="upgrade-yunos")
def upgrade_yunos(
    snap_name: Optional[str] = typer.Option(
        None, "--snap-name", help="Rollback snap name (default: pre-upgrade-<YYYYMMDD>)."
    ),
    no_snap: bool = typer.Option(
        False, "--no-snap", help="Skip the rollback snapshot step entirely."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Don't prompt before creating the new yuno rows."
    ),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="ycommand url (default: ws://127.0.0.1:1991)."
    ),
    node: Optional[str] = typer.Option(
        None, "--node", "-N", help="Registered node to promote on (see 'yunetas list-nodes')."
    ),
    tunnel: bool = typer.Option(
        False, "--tunnel", help="Force the node's SSH tunnel even if it also has a url."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Print the agent commands without running them."
    ),
):
    """
    Promote freshly installed binaries/configs to primary on the local agent.

    Run this after 'sync-binaries' / 'sync-configs' have pushed the new
    artifacts. The flow is:

      1. Rollback snapshot (idempotent by name): shoot-snap only if no snap
         named like the default 'pre-upgrade-<YYYYMMDD>' (or --snap-name)
         already exists. Skipped with --no-snap.
      2. find-new-yunos (preview): list the create-yuno rows that would be
         registered, then ask for confirmation (skip the prompt with --yes).
      3. find-new-yunos create=1: register the new yuno-instance rows.
      4. deactivate-snap: triggers restart_nodes() on the agent (SIGKILL +
         treedb reload), promoting the newest release of every yuno.
    """
    ycommand = ycommand_path()
    if not ycommand:
        print("[red]Error: ycommand not found in PATH.[/red]")
        raise typer.Exit(code=1)

    if node:
        # The tunnel has to outlive this block (every step below talks to the
        # agent), and the body uses `url` in a dozen places. Rather than wrap
        # ~60 lines in a with-statement, tie the teardown to process exit:
        # atexit runs on normal return and on the SystemExit that typer.Exit
        # raises, which is every way this command finishes.
        conn = resolve_node_connection(node, url, tunnel).__enter__()
        atexit.register(conn.__exit__, None, None, None)
        url = conn.url
        if conn.url.startswith("wss://"):
            print("[yellow]Note: upgrade-yunos talks to the agent directly and does "
                  "not forward OAuth2 credentials; use --tunnel for a wss:// node.[/yellow]")

    # 1) Rollback snapshot. Never stack a new snap on an already-active one:
    #    if a snap is active (e.g. a prior activate-snap rollback in progress),
    #    reuse it as the rollback point instead of shooting another. Otherwise
    #    fall back to the by-name idempotency check.
    if not no_snap:
        active = active_snap_name(ycommand, url)
        if active:
            print(f"[yellow]Snap '{active}' is already active; reusing it as the rollback point "
                  f"(not shooting a new one).[/yellow]")
        else:
            name = snap_name or f"pre-upgrade-{datetime.now():%Y%m%d}"
            exists = snap_exists(ycommand, url, name)
            if exists:
                print(f"[yellow]Snap '{name}' already exists; reusing it as the rollback point.[/yellow]")
            else:
                ok, _ = run_ycommand(
                    ycommand, url,
                    f"shoot-snap name={name} description=before-upgrade-yunos",
                    dry_run,
                )
                if not ok and not dry_run:
                    print("[red]Error: shoot-snap failed; aborting before any change.[/red]")
                    raise typer.Exit(code=1)

    # 2) find-new-yunos preview. Suppress the raw JSON echo; we render our
    #    own formatted list from the parsed preview below.
    ok, out = run_ycommand(ycommand, url, "find-new-yunos", dry_run, echo_output=False)
    if not ok and not dry_run:
        print("[red]Error: find-new-yunos failed.[/red]")
        raise typer.Exit(code=1)
    if not dry_run:
        try:
            preview = _parse_leading_json(out)
        except (ValueError, json.JSONDecodeError):
            preview = []
        if not isinstance(preview, list) or not preview:
            print("[green]No new yunos to activate. Nothing to do.[/green]")
            raise typer.Exit(code=0)
        print(f"[cyan]{len(preview)} new yuno row(s) would be created:[/cyan]")
        for line in preview:
            print(f"  {line}")

        # 3) Confirm + create.
        if not yes and not typer.confirm("Create these new yuno rows?", default=False):
            print("[yellow]Aborted: no rows created, no snap consumed, no restart.[/yellow]")
            raise typer.Exit(code=1)

    # Suppress the verbose created-node table; print a one-line summary instead.
    ok, out = run_ycommand(ycommand, url, "find-new-yunos create=1", dry_run, echo_output=False)
    # Resumed upgrade: a prior run already registered the new yuno rows but never
    # promoted them (deactivate-snap missing). The preview still lists them because
    # the OLD primary rows survive and a newer binary is found for each, so create=1
    # re-runs create-yuno and the agent answers "Yuno already exists" (result<0).
    # That is idempotent: the rows are already there. Don't abort — fall through to
    # deactivate-snap, the step that actually promotes them. Only a non-idempotent
    # failure aborts, so a genuine create-yuno error still fails closed.
    already = out is not None and "already exists" in out
    if not ok and not dry_run and out:
        # Surface the agent's comments (suppressed above) so a mixed or genuine
        # failure is never hidden behind the idempotent fall-through.
        print(f"[dim]{out}[/dim]")
    if not ok and not already and not dry_run:
        print("[red]Error: find-new-yunos create=1 failed; aborting before restart.[/red]")
        raise typer.Exit(code=1)
    if not dry_run:
        if already:
            print("[yellow]New yuno row(s) already registered by a prior run; "
                  "proceeding to promote.[/yellow]")
        else:
            print(f"[green]Created {len(preview)} new yuno row(s).[/green]")

    # 4) deactivate-snap -> restart_nodes() on the agent.
    ok, _ = run_ycommand(ycommand, url, "deactivate-snap", dry_run)
    if not ok and not dry_run:
        print("[red]Error: deactivate-snap failed.[/red]")
        raise typer.Exit(code=1)

    print("[green]upgrade-yunos done: new releases promoted and nodes restarted.[/green]")


@app.command()
def test():
    """
    Run ctest in yunetas
    """
    process_build_command(DIRECTORIES, ["make", "install"])
    process_build_command(["."], ["make", "install"])
    process_build_command(["."], ["make", "clean"])
    ret = process_build_command(["."], ["make", "install"])
    if ret == 0:
        filename = datetime.now().isoformat().replace(":", "-") + ".txt"
        process_build_command(["."], ["ctest", "--output-log", filename])


def version_callback(value: bool):
    if value:
        print(f"{__version__}")
        raise typer.Exit()


@app.command()
def version():
    """
    Print version information
    """
    version_callback(True)


@app.callback(invoke_without_command=True)
def app_main(
    ctx: typer.Context,
    version_: Optional[bool] = typer.Option(
        None,
        "-v",
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print version and exit",
    )
):
    # Silence warning
    _ = version_
    if ctx.invoked_subcommand is None:
        # No subcommand was provided, so we print the help.
        typer.main.get_command(app).get_help(ctx)
        raise typer.Exit(code=1)


def run():
    app()


#--------------------------------------------------#
#   Project registry helpers
#--------------------------------------------------#
def load_registered_projects():
    """
    Load the project registry (~/.yuneta/projects.json).

    Returns:
        list: list of {"name": str, "path": str} dicts (empty if no registry).
    """
    if not os.path.isfile(PROJECTS_REGISTRY_PATH):
        return []
    try:
        with open(PROJECTS_REGISTRY_PATH, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[red]Error: cannot read project registry '{PROJECTS_REGISTRY_PATH}': {e}[/red]")
        raise typer.Exit(code=1)

    projects = data.get("projects", []) if isinstance(data, dict) else None
    if not isinstance(projects, list):
        print(f"[red]Error: malformed project registry '{PROJECTS_REGISTRY_PATH}'.[/red]")
        raise typer.Exit(code=1)
    return projects


def save_registered_projects(projects):
    """
    Save the project registry (~/.yuneta/projects.json).
    """
    try:
        os.makedirs(YUNETA_USER_DIR, exist_ok=True)
        with open(PROJECTS_REGISTRY_PATH, "w") as f:
            json.dump({"projects": projects}, f, indent=4)
            f.write("\n")
    except Exception as e:
        print(f"[red]Error: cannot write project registry '{PROJECTS_REGISTRY_PATH}': {e}[/red]")
        raise typer.Exit(code=1)


def load_registered_nodes():
    """
    Load the node registry (~/.yuneta/nodes.json).

    Returns:
        list: list of node dicts (empty if no registry).
    """
    if not os.path.isfile(NODES_REGISTRY_PATH):
        return []
    try:
        with open(NODES_REGISTRY_PATH, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[red]Error: cannot read node registry '{NODES_REGISTRY_PATH}': {e}[/red]")
        raise typer.Exit(code=1)

    nodes = data.get("nodes", []) if isinstance(data, dict) else None
    if not isinstance(nodes, list):
        print(f"[red]Error: malformed node registry '{NODES_REGISTRY_PATH}'.[/red]")
        raise typer.Exit(code=1)
    return nodes


def save_registered_nodes(nodes):
    """
    Save the node registry (~/.yuneta/nodes.json), owner-readable only.
    """
    try:
        os.makedirs(YUNETA_USER_DIR, exist_ok=True)
        with open(NODES_REGISTRY_PATH, "w") as f:
            json.dump({"nodes": nodes}, f, indent=4)
            f.write("\n")
        # It carries no secret by design, but it does map out the deploy
        # surface of this machine. No reason for anyone else to read it.
        os.chmod(NODES_REGISTRY_PATH, 0o600)
    except Exception as e:
        print(f"[red]Error: cannot write node registry '{NODES_REGISTRY_PATH}': {e}[/red]")
        raise typer.Exit(code=1)


def find_registered_node(name):
    """
    Resolve a node by registry name, or exit with the list of known ones.
    """
    nodes = load_registered_nodes()
    for n in nodes:
        if n.get("name") == name:
            return n
    known = ", ".join(sorted(n.get("name", "?") for n in nodes)) or "(none)"
    print(f"[red]Error: node '{name}' is not registered. Registered: {known}[/red]")
    print("[yellow]Add it with 'yunetas register-node <name> --url ... | --ssh ...'.[/yellow]")
    raise typer.Exit(code=1)


def _free_local_port():
    """
    Ask the OS for a free port, then hand it to ssh. There is a race here
    (the port is released before ssh binds it) but it is the standard trick
    and the window is microseconds on a machine that is not port-scanning
    itself.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class NodeConnection:
    """
    Resolve a registered node into the arguments the agent tools need, and
    own the SSH tunnel when the node is reached that way.

    Two access modes:

      direct  the node's agent is reachable from here (typically wss:// on
              1993 with OAuth2). `url` is used as-is.
      tunnel  only the node's LOCAL agent port is open (ws:// on 1991 bound
              to 127.0.0.1, which is the default and the safer posture). We
              forward a local port over SSH and talk to that.

    Used as a context manager so the tunnel dies with the command, including
    on failure — a leaked `ssh -N` would silently keep a port open.
    """

    def __init__(self, node, force_tunnel=False):
        self.node = node
        self.force_tunnel = force_tunnel
        self.proc = None
        self.url = None

    def __enter__(self):
        node = self.node
        url = node.get("url")
        ssh_target = node.get("ssh")

        use_tunnel = bool(ssh_target) and (self.force_tunnel or not url)
        if use_tunnel:
            remote_port = int(node.get("agent_port", 1991))
            local_port = _free_local_port()
            print(f"[cyan]Tunnelling {ssh_target}:{remote_port} -> 127.0.0.1:{local_port}[/cyan]")
            self.proc = subprocess.Popen(
                [
                    "ssh", "-N",
                    "-o", "ConnectTimeout=20",
                    "-o", "ExitOnForwardFailure=yes",
                    "-L", f"{local_port}:127.0.0.1:{remote_port}",
                    ssh_target,
                ]
            )
            if not self._wait_for_port(local_port):
                self.__exit__(None, None, None)
                print(f"[red]Error: SSH tunnel to '{ssh_target}' did not come up.[/red]")
                raise typer.Exit(code=1)
            self.url = f"ws://127.0.0.1:{local_port}"
        elif url:
            self.url = url
        else:
            print(f"[red]Error: node '{node.get('name')}' has neither 'url' nor 'ssh'.[/red]")
            raise typer.Exit(code=1)

        return self

    def _wait_for_port(self, port, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False    # ssh died (bad host, auth, port in use)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return True
            time.sleep(0.2)
        return False

    def args(self):
        """
        The flags to forward to sync_binaries.py / sync_configs.py.

        Credentials are read from the environment, never from the registry.
        Only the OAuth2 identity (issuer/client/user) is stored.
        """
        out = ["-u", self.url]

        # A tunnelled ws:// agent needs no OAuth2: the SSH session already
        # authenticated us, and the agent trusts its own loopback.
        if self.url.startswith("wss://"):
            node = self.node
            for flag, key in (("-I", "issuer"), ("-Z", "client_id"), ("-x", "user_id")):
                value = node.get(key)
                if value:
                    out += [flag, value]

            jwt = os.environ.get(ENV_OAUTH_JWT)
            if jwt:
                out += ["-j", jwt]
            else:
                passw = os.environ.get(ENV_OAUTH_PASSW)
                if passw:
                    out += ["-X", passw]
                secret = os.environ.get(ENV_OAUTH_CLIENT_SECRET)
                if secret:
                    out += ["--client-secret", secret]

        return out

    def __exit__(self, exc_type, exc, tb):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
        return False


def resolve_node_connection(node_name, url, force_tunnel=False):
    """
    Turn the --node/--url pair into a context manager yielding the connection.

    --url alone keeps working exactly as before (no registry involved), so
    nothing that scripts the old flags breaks.
    """
    if node_name and url:
        print("[red]Error: use --node or --url, not both.[/red]")
        raise typer.Exit(code=1)

    if node_name:
        return NodeConnection(find_registered_node(node_name), force_tunnel)

    # No node: behave as before. A bare url (or the tool's own default) with
    # no tunnel to manage.
    return NodeConnection({"name": "(none)", "url": url or "ws://127.0.0.1:1991"})


def node_secrets_dir(node_name):
    """
    The secret-overlay directory for a node, or None if it has none.

    Absence is normal: most configs carry no credential. It is the presence of
    a "__SECRET__" placeholder in a committed config that makes an overlay
    mandatory, and sync_configs refuses the push when one is missing — so a
    forgotten overlay fails loudly rather than shipping an empty password.
    """
    if not node_name:
        return None
    path = os.path.join(SECRETS_DIR, node_name)
    return path if os.path.isdir(path) else None


def project_yunos_dir(project):
    """
    Return the buildable yunos/ directory of a registered project.
    """
    return os.path.join(project["path"], "yunos")


def sdk_has_sources():
    """
    True when YUNETAS_BASE holds the framework sources (a development node).

    A runtime-only node (.deb/.rpm sparse SDK) ships outputs/, outputs_ext/,
    tools/ and .config but no sources and no YUNETA_VERSION: there is nothing
    to init/build/clean there, only the registered projects.
    """
    return os.path.isfile(os.path.join(YUNETAS_BASE, "YUNETA_VERSION"))


def resolve_selection(project_names, sdk_only):
    """
    Decide what init/build/clean must process.

    Args:
        project_names (list|None): positional project names (None/empty = not given).
        sdk_only (bool): --sdk-only flag.

    Returns:
        tuple: (include_sdk: bool, projects: list)
            - no names, no flag  -> SDK + every registered project
            - names given        -> only those projects (SDK skipped)
            - --sdk-only         -> only the SDK

    On a runtime-only node the SDK is never selectable: with no names the
    command silently narrows to the registered projects, and --sdk-only is an
    error (it asks for the one thing that cannot be done there).
    """
    if sdk_only and project_names:
        print("[red]Error: --sdk-only and project names are mutually exclusive.[/red]")
        raise typer.Exit(code=1)

    runtime_only = not sdk_has_sources()

    if sdk_only:
        if runtime_only:
            print(f"[red]Error: no YUNETA_VERSION in '{YUNETAS_BASE}' (runtime-only SDK): "
                  f"there are no framework sources to build.[/red]")
            raise typer.Exit(code=1)
        return True, []

    registered = load_registered_projects()
    if project_names:
        by_name = {p["name"]: p for p in registered}
        selected = []
        for name in project_names:
            if name not in by_name:
                known = ", ".join(sorted(by_name)) or "(none)"
                print(f"[red]Error: project '{name}' is not registered. Registered: {known}[/red]")
                raise typer.Exit(code=1)
            selected.append(by_name[name])
        return False, selected

    if runtime_only:
        if not registered:
            print(f"[red]Error: runtime-only SDK in '{YUNETAS_BASE}' and no registered project: "
                  f"nothing to do. Register one with 'yunetas register-project <path>'.[/red]")
            raise typer.Exit(code=1)
        print("[yellow]Runtime-only SDK: skipping the framework, "
              "processing the registered projects.[/yellow]")
        return False, registered

    return True, registered


def run_agent_tool(script_name, args, cwd=None):
    """
    Run one of the bundled agent tools, forwarding arguments.

    They ship inside this package (``yunetas.agent_tools``) rather than being
    read from ``$YUNETAS_BASE/tools/agent/``, so the CLI and the tools it
    drives are always the same version. When they were released separately, a
    ``pipx install --upgrade yunetas`` could hand a new flag to a script from
    an older SDK and die with "unrecognized arguments".

    Still a subprocess, not an import: the tools own their exit codes and
    install their own signal handlers (sync_configs wipes its plaintext
    workdir on SIGINT/SIGTERM), and running them in-process would put both
    under typer's control.

    Returns:
        int: the tool's exit code.
    """
    module = "yunetas.agent_tools.%s" % script_name[:-len(".py")] \
        if script_name.endswith(".py") else "yunetas.agent_tools.%s" % script_name

    env = os.environ.copy()
    env.setdefault("YUNETAS_BASE", YUNETAS_BASE)
    result = subprocess.run(
        [sys.executable, "-m", module] + list(args), cwd=cwd, env=env
    )
    return result.returncode


def push_configs(selected_projects, host, url, forwarded):
    """
    Realm-match each selected project's batches/<host>/ directories and run
    sync_configs.py on every match. Shared by the 'sync-configs' and 'sync'
    commands. Returns (exit_code, synced_count).

    Without `host`, batches dirs are matched against the realm_ids the local
    agent manages ('*list-realms'); with `host`, only that dir is targeted; if
    the agent is unreachable it falls back to the legacy single-hostname guess.
    """
    # Without --host, auto-match batches dirs against the agent's realm_ids.
    realm_ids = None
    if not host:
        realm_ids = local_realm_ids(url)
        if realm_ids is None:
            print("[yellow]Could not query the agent for realms (*list-realms); falling back to "
                  "hostname match. Pass --host to target a specific batches dir.[/yellow]")
        elif not realm_ids:
            print("[yellow]The agent reports no enabled realms to match against.[/yellow]")

    exit_code = 0
    synced = 0
    for proj in selected_projects:
        batches_dir = os.path.join(project_yunos_dir(proj), "batches")
        if not os.path.isdir(batches_dir):
            print(f"[yellow]Skipping {proj['name']}: no '{batches_dir}'.[/yellow]")
            continue

        hosts = sorted(
            d for d in os.listdir(batches_dir)
            if os.path.isdir(os.path.join(batches_dir, d))
        )

        if host:
            if host not in hosts:
                print(f"[yellow]Skipping {proj['name']}: no batches for host '{host}' (available: {', '.join(hosts) or 'none'}).[/yellow]")
                continue
            chosen_hosts = [host]
        elif realm_ids is not None:
            chosen_hosts = [h for h in hosts if h in realm_ids]
            if not chosen_hosts:
                print(f"[yellow]Skipping {proj['name']}: no batches/<host>/ matches a local realm_id "
                      f"(batches: {', '.join(hosts) or 'none'}; realms: {', '.join(sorted(realm_ids)) or 'none'}).[/yellow]")
                continue
        else:
            # Fallback: legacy single-hostname guess (agent unreachable).
            candidates = {socket.gethostname(), socket.getfqdn()}
            chosen_hosts = [h for h in hosts if h in candidates]
            if len(chosen_hosts) != 1:
                print(f"[red]Error: cannot guess the target host for '{proj['name']}'. Pass --host. Available: {', '.join(hosts) or 'none'}[/red]")
                raise typer.Exit(code=1)

        for chosen in chosen_hosts:
            config_dir = os.path.join(batches_dir, chosen)
            print(f"[cyan]Syncing configs: {proj['name']} -> {chosen} ({config_dir})[/cyan]")
            ret = run_agent_tool("sync_configs.py", forwarded + [config_dir])
            synced += 1
            if ret != 0:
                exit_code = ret

    return exit_code, synced


#--------------------------------------------------#
#   ycommand helpers (talk to the local agent)
#--------------------------------------------------#
# ycommand wraps a JSON payload with a leading blank line and a coloured footer.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _parse_leading_json(text):
    """
    Decode the first JSON value found in ycommand's stdout (ANSI stripped),
    ignoring whatever trails it. Raises ValueError if none is present.
    """
    clean = _ANSI_RE.sub("", text or "")
    start = next((i for i, ch in enumerate(clean) if ch in "[{"), None)
    if start is None:
        raise ValueError("no JSON value found")
    obj, _ = json.JSONDecoder().raw_decode(clean[start:])
    return obj


def ycommand_path():
    """Resolve the ycommand binary, or None if not on PATH."""
    return shutil.which("ycommand")


def run_ycommand(ycommand, url, cmd_str, dry_run=False, timeout=300, echo_output=True):
    """
    Run one `ycommand -c '<cmd_str>'`, echoing it. Returns (ok, stdout).
    `ok` is False on a non-zero exit or an "ERROR" in the response.

    With echo_output=False the captured stdout is still returned but not
    printed — used when the caller renders its own concise summary instead
    of dumping ycommand's verbose table (e.g. find-new-yunos).
    """
    cmd = [ycommand]
    if url:
        cmd += ["-u", url]
    cmd += ["-c", cmd_str]
    print(f"[cyan]>> ycommand -c '{cmd_str}'[/cyan]")
    if dry_run:
        print("   [dim](dry-run, not executed)[/dim]")
        return True, ""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[red]   ERROR: {e}[/red]")
        return False, ""
    out = (res.stdout or "").strip()
    if out and echo_output:
        print(out)
    err = (res.stderr or "").strip()
    if err:
        print(f"[dim]{err}[/dim]")
    ok = res.returncode == 0 and "ERROR" not in out
    return ok, out


def local_realm_ids(url=None):
    """
    Realm ids the local agent manages, via '*list-realms'.

    Returns a set of enabled realm_id strings, or None if the agent can't be
    queried (binary missing, connection refused, unparsable answer).
    """
    ycommand = ycommand_path()
    if not ycommand:
        return None
    cmd = [ycommand]
    if url:
        cmd += ["-u", url]
    cmd += ["-c", "*list-realms"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        data = _parse_leading_json(res.stdout)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    ids = set()
    for r in data:
        if isinstance(r, dict) and r.get("id") and not r.get("realm_disabled"):
            ids.add(r["id"])
    return ids


def snap_exists(ycommand, url, name):
    """
    True/False whether a snap named `name` exists on the agent; None if the
    snap list can't be read. The 'snaps' command renders a table whose Name
    column holds the name quoted, so an exact quoted match is unambiguous.
    """
    cmd = [ycommand]
    if url:
        cmd += ["-u", url]
    cmd += ["-c", "snaps"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    text = _ANSI_RE.sub("", res.stdout or "")
    return f'"{name}"' in text


def active_snap_name(ycommand, url):
    """
    Name of the currently active snap on the agent, or None if none is active.
    Returns None too if the snap list can't be read (the caller then falls back
    to the by-name idempotency check). Uses '*snaps' (the leading '*' makes
    ycommand emit raw JSON); the agent keeps at most one snap active (treedb
    activates a single tag), so the first record flagged active wins.
    """
    cmd = [ycommand]
    if url:
        cmd += ["-u", url]
    cmd += ["-c", "*snaps"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    try:
        data = _parse_leading_json(res.stdout)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    for snap in data:
        if isinstance(snap, dict) and snap.get("active"):
            return snap.get("name") or "(unnamed)"
    return None


def kconfig2include(config_file_path):
    """
    Convert a Kconfig-style configuration file into a C-style header content.

    Args:
        config_file_path (str): Path to the configuration file.

    Returns:
        str: Generated C header content.
    """
    header_content = ""

    try:
        with open(config_file_path, "r") as config_file:
            for line in config_file:
                line = line.strip()  # Remove leading and trailing whitespace
                if not line or line.startswith("#"):
                    continue  # Skip comments and empty lines

                # Split configuration line into key and value
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Process value
                    if value == "y":
                        header_content += f"#define {key} 1\n"
                    elif value.isdigit():
                        header_content += f"#define {key} {value}\n"
                    else:
                        value = value.strip('"')  # Remove quotes if present
                        header_content += f"#define {key} \"{value}\"\n"

    except Exception as e:
        raise RuntimeError(f"Error processing configuration file {config_file_path}: {e}")

    return header_content

def is_file_outdated(source_file, target_file):
    """
    Check if the source file is newer than the target file.

    Args:
        source_file (str): Path to the source file.
        target_file (str): Path to the target file.

    Returns:
        bool: True if the source file is newer, or the target file does not exist.
    """
    if not os.path.isfile(target_file):
        return True  # Target file doesn't exist, needs to be created
    return os.path.getmtime(source_file) > os.path.getmtime(target_file)

def setup_yuneta_environment(reset_outputs=False):
    """
    Check and configure Yuneta environment variables, and prepare directories for generated files.
    Ensures YUNETAS_BASE and its required files exist.
    Generates yuneta_version.h and yuneta_config.h using kconfig2include.
    """
    #--------------------------------------------------#
    # Check if YUNETA_VERSION and .config files exist in YUNETAS_BASE
    #--------------------------------------------------#
    yuneta_version_path2 = os.path.join(YUNETAS_BASE, "YUNETA_VERSION")
    yuneta_config_path = os.path.join(YUNETAS_BASE, ".config")

    # A runtime-only node (.deb/.rpm sparse SDK) has outputs/, outputs_ext/,
    # tools/ and .config but NO framework sources and NO YUNETA_VERSION:
    # the generated headers are shipped inside outputs/include.
    has_framework_sources = os.path.isfile(yuneta_version_path2)

    if not os.path.isfile(yuneta_config_path):
        print(f"Error: .config file not found in '{YUNETAS_BASE}'.")
        sys.exit(1)

    if reset_outputs and not has_framework_sources:
        print(f"Error: no YUNETA_VERSION in '{YUNETAS_BASE}' (runtime-only SDK): "
              f"refusing to reset outputs/. Use 'yunetas init <project>'.")
        sys.exit(1)

    if has_framework_sources:
        # Only meaningful where menuconfig can be run: a runtime-only node gets
        # its .config from the .deb/.rpm and has no Kconfig tree to re-run.
        final_messages.append(
            f"\n[yellow]WARNING:[/yellow] The file [green]'yuneta_config.h'[/green] is created "
            f"by init or build option but from options selected previously by "
            f"[blue]menuconfig[/blue] utility \n"
        )


    #--------------------------------------------------#
    #   Detect compiler from .config (Clang, GCC)
    #--------------------------------------------------#
    global compiler
    compiler = get_compiler_from_config()

    #--------------------------------------------------#
    # Get parent directory of YUNETAS_BASE and set up output directories
    #--------------------------------------------------#
    # yunetas_parent_base_dir = os.path.dirname(YUNETAS_BASE)
    outputs_dir = os.path.join(YUNETAS_BASE, "outputs")
    inc_dest_dir = os.path.join(outputs_dir, "include")
    lib_dest_dir = os.path.join(outputs_dir, "lib")
    bin_dest_dir = os.path.join(outputs_dir, "bin")
    yunos_dest_dir = os.path.join(outputs_dir, "yunos")

    try:
        if reset_outputs:
            if os.path.isdir(outputs_dir):
                shutil.rmtree(outputs_dir)
        # Create 'outputs/include' directory if it doesn't exist
        os.makedirs(outputs_dir, exist_ok=True)
        os.makedirs(inc_dest_dir, exist_ok=True)
        os.makedirs(lib_dest_dir, exist_ok=True)
        os.makedirs(bin_dest_dir, exist_ok=True)
        os.makedirs(yunos_dest_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Unable to create directories '{outputs_dir}'. {e}")
        sys.exit(1)

    #--------------------------------------------------#
    # Generate yuneta_version.h from YUNETA_VERSION
    #--------------------------------------------------#
    yuneta_version_h_path = os.path.join(inc_dest_dir, "yuneta_version.h")
    if not has_framework_sources:
        # Runtime-only SDK: the header must have been shipped in outputs/include
        if not os.path.isfile(yuneta_version_h_path):
            print(f"Error: neither YUNETA_VERSION nor a shipped '{yuneta_version_h_path}' found.")
            sys.exit(1)
    elif is_file_outdated(yuneta_version_path2, yuneta_version_h_path):
        year = datetime.now().year
        version_header_content = f"""\
/*
 *  Yuneta Version
 *  Automatically generated file. DO NOT EDIT.
 *  Set version in YUNETA_VERSION file.
 *
 *  Copyright (c) {year} ArtGins
 */
#pragma once

"""
        try:
            version_header_content += kconfig2include(yuneta_version_path2)

            # Write the yuneta_version.h file
            with open(yuneta_version_h_path, "w") as header_file:
                header_file.write(version_header_content)
            msg = f"Generated 'yuneta_version.h' at {yuneta_version_h_path}"
            final_messages.append(msg)

        except Exception as e:
            print(f"Error: Unable to generate yuneta_version.h. {e}")
            sys.exit(1)

    #--------------------------------------------------#
    # Generate yuneta_config.h from .config
    #--------------------------------------------------#
    yuneta_config_h_path = os.path.join(inc_dest_dir, "yuneta_config.h")
    if is_file_outdated(yuneta_config_path, yuneta_config_h_path):
        year = datetime.now().year

        config_header_content = f"""\
/*
 *  Yuneta Configuration
 *  Automatically generated file. DO NOT EDIT.
 *  Set configuration in .config file. 
 *  Modify with `menuconfig` command in yunetas root directory.
 *
 *  Copyright (c) {year} ArtGins
 */
#pragma once

"""
        try:
            config_header_content += kconfig2include(yuneta_config_path)

            # Write the yuneta_config.h file
            with open(yuneta_config_h_path, "w") as header_file:
                header_file.write(config_header_content)
            msg = f"Generated 'yuneta_config.h' at {yuneta_config_h_path}"
            final_messages.append(msg)
        except Exception as e:
            print(f"Error: Unable to generate yuneta_config.h. {e}")
            sys.exit(1)

    msg = f"Setup completed successfully:"
    final_messages.append(msg)

    msg = f"  - YUNETAS_BASE: {YUNETAS_BASE}"
    final_messages.append(msg)

    if has_framework_sources:
        msg = f"  - YUNETA_VERSION: {yuneta_version_path2}"
    else:
        msg = f"  - YUNETA_VERSION: (runtime-only SDK, headers shipped in outputs/include)"
    final_messages.append(msg)

    msg = f"  - [green]'.config'[/green]: {yuneta_config_path}"
    final_messages.append(msg)

    msg = f"  - Include directory: {inc_dest_dir}"
    final_messages.append(msg)


#--------------------------------------------------#
#   Detect compiler from .config
#--------------------------------------------------#
def get_compiler_from_config():
    """
    Parse .config and return CC (C compiler) based on CONFIG_USE_COMPILER_*
    """
    config_path = os.path.join(YUNETAS_BASE, ".config")
    if not os.path.isfile(config_path):
        return None

    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line == "CONFIG_USE_COMPILER_CLANG=y":
                return "clang"
            elif line == "CONFIG_USE_COMPILER_GCC=y":
                return "gcc"

    return None


#--------------------------------------------------#
#   Detect build type from .config
#--------------------------------------------------#
def get_build_type_from_config():
    """
    Parse .config and return build type based on CONFIG_BUILD_TYPE_*
    """
    config_path = os.path.join(YUNETAS_BASE, ".config")
    if not os.path.isfile(config_path):
        return None

    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line == "CONFIG_BUILD_TYPE_RELEASE=y":
                return "Release"
            elif line == "CONFIG_BUILD_TYPE_DEBUG=y":
                return "Debug"
            elif line == "CONFIG_BUILD_TYPE_RELWITHDEBINFO=y":
                return "RelWithDebInfo"
            elif line == "CONFIG_BUILD_TYPE_MINSIZEREL=y":
                return "MinSizeRel"

    return None


#--------------------------------------------------#
#   Process directories and run cmake
#--------------------------------------------------#
def process_directories(directories: List[str]):
    """
    Process directories and execute cmake with build type and detected compiler

    Args:
        directories (List[str]): List of directories to process.

    Returns:
        List of directories whose cmake failed. Empty means every one
        configured. Callers MUST NOT report success without checking it: a
        cmake that fails here (a glibc mismatch caught by libc_guard.cmake, a
        missing dependency) leaves no Makefile behind, so the later build
        breaks with an unrelated-looking error.
    """
    failed = []

    base_path = Path(YUNETAS_BASE)
    if not base_path.is_dir():
        print(f"[red]Error: YUNETAS_BASE '{YUNETAS_BASE}' does not exist or is not a directory.[/red]")
        raise typer.Exit(code=1)

    #--------------------------------------------------#
    #   Detect compiler from .config (Clang, GCC)
    #--------------------------------------------------#
    global compiler
    compiler = get_compiler_from_config()
    if compiler is None:
        print(f"[red]Error: No compiler found [/red]")
        raise typer.Exit(code=1)
    build_type = get_build_type_from_config()
    if build_type is None:
        print(f"[red]Error: No build type found [/red]")
        raise typer.Exit(code=1)

    CC = None
    if compiler == "clang":
        CC = "/usr/bin/clang"
    elif compiler == "gcc":
        CC = "/usr/bin/gcc"
    else:
        print(f"[red]Error: Compiler found [/red]")
        raise typer.Exit(code=1)

    for directory in directories:
        # Registered projects come as absolute paths; SDK entries are YUNETAS_BASE-relative
        if os.path.isabs(directory):
            path_pattern = Path(directory)
        else:
            path_pattern = base_path / directory
        for dir_path in path_pattern.parent.glob(path_pattern.name):  # Support wildcard directories
            if dir_path.is_dir():
                print(f"[cyan]Processing directory: {dir_path}[/cyan]")

                build_dir = dir_path / "build"

                try:
                    # Remove build directory if it exists
                    if build_dir.exists():
                        print(f"[yellow]Removing existing build directory: {build_dir}[/yellow]")
                        subprocess.run(["rm", "-rf", str(build_dir)], check=True)

                    # Create a new build directory
                    print(f"[green]Creating build directory: {build_dir}[/green]")
                    build_dir.mkdir(parents=True, exist_ok=True)

                    # Run cmake with build type and optional compiler
                    cmake_command = [
                        "cmake",
                        f"-DCMAKE_BUILD_TYPE={build_type}",
                        f"-DCMAKE_C_COMPILER={CC}",
                    ]
                    cmake_command.append("..")

                    print(f"[blue]Running cmake command '{cmake_command}' in '{build_dir}'[/blue]")
                    subprocess.run(cmake_command, cwd=build_dir, check=True)

                except subprocess.CalledProcessError as e:
                    print(f"[red]Error occurred while processing {dir_path}: {e}[/red]")
                    failed.append(dir_path)

    return failed


def process_build_command(directories: List[str], command: List[str]):
    """
    Process build commands (e.g., ["make", "install"], ["ninja", "clean"]) in specified directories.

    Args:
        directories (List[str]): List of directories to process.
        command (List[str]): The build command to execute as a list (e.g., ["make", "install"]).
    """

    ret = 0
    base_path = Path(YUNETAS_BASE)
    if not base_path.is_dir():
        print(f"[red]Error: YUNETAS_BASE '{YUNETAS_BASE}' does not exist or is not a directory.[/red]")
        raise typer.Exit(code=1)

    for directory in directories:
        # Registered projects come as absolute paths; SDK entries are YUNETAS_BASE-relative
        if os.path.isabs(directory):
            path_pattern = Path(directory)
        else:
            path_pattern = base_path / directory
        for dir_path in path_pattern.parent.glob(path_pattern.name):  # Support wildcard directories
            if not dir_path.is_dir():
                continue

            cmake_file = dir_path / "CMakeLists.txt"
            if not cmake_file.exists():
                print(f"[yellow]Skipping {dir_path}: No CMakeLists.txt found[/yellow]")
                continue

            build_dir = dir_path / "build"
            if build_dir.is_dir():
                print(f"[cyan]Processing build directory: {build_dir}[/cyan]")
                try:
                    # Execute the specified build command
                    print(f"[blue]Running '{' '.join(command)}' in {build_dir}[/blue]")
                    subprocess.run(command, cwd=build_dir, check=True) #, env=env)
                except subprocess.CalledProcessError as e:
                    print(f"[red]Error occurred while running '{' '.join(command)}' in {build_dir}: {e}[/red]")
                    # typer.Exit, not the bare `exit()`: that one is installed
                    # by `site` and is absent under `python -S`, and it exits
                    # 255 instead of a plain 1.
                    raise typer.Exit(code=1)
            else:
                print(f"[yellow]Skipping {dir_path}: No build directory found[/yellow]")

    return ret
