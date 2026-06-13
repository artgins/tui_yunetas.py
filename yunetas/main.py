import typer
from rich import print
from rich.console import Console
from .__version__ import __version__
from .my_venv import app_venv
from typing import Optional, List
from pathlib import Path
import json
import os
import socket
import sys
import subprocess
import shutil
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

final_messages = [f"\n[yellow]WARNING:[/yellow] The file [green]'yuneta_config.h'[/green] is created by init or build option but from options selected previously by [blue]menuconfig[/blue] utility \n"]

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

msg = f"Using [green]YUNETAS_BASE[/green] at {YUNETAS_BASE}"
print(msg)
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

    if include_sdk:
        setup_yuneta_environment(True)
        process_directories(DIRECTORIES)
        process_directories(["."])
    else:
        # Ensure outputs/include headers are up to date without wiping outputs
        setup_yuneta_environment(False)

    for project in selected_projects:
        print(f"[cyan]Project: {project['name']} ({project['path']})[/cyan]")
        process_directories([project_yunos_dir(project)])
        final_messages.append(f"Project [cyan]{project['name']}[/cyan] initialized.")

    global compiler
    final_messages.append(f"\n[yellow]Compiler selected[/yellow]: [blue]{compiler}[/blue]\n")
    final_messages.append(f"[yellow]init[/yellow] done: created build directories, got compiler and build type from .config ([blue]menuconfig[/blue])\n")
    print("\n".join(final_messages))

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


@app.command(
    name="sync-binaries",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def sync_binaries(ctx: typer.Context):
    """
    Compare outputs/yunos binaries with the local agent and push updates.
    Wrapper over tools/agent/sync_binaries.py: every argument is forwarded
    (e.g. -n dry-run, -a all, --no-restart, OAuth2 options).
    """
    ret = run_agent_tool("sync_binaries.py", ctx.args)
    raise typer.Exit(code=ret)


@app.command(
    name="sync-configs",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def sync_configs(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(
        None, "--host", help="batches/<host>/ directory to sync (default: this machine's hostname)."
    ),
    project: Optional[List[str]] = typer.Option(
        None, "--project", "-p", help="Restrict to these registered projects (default: all)."
    ),
):
    """
    Sync yuno configs of each registered project (yunos/batches/<host>/) against
    the local agent. Wrapper over tools/agent/sync_configs.py: unknown arguments
    are forwarded (e.g. -n dry-run, -a all, -r restart, OAuth2 options).
    """
    _, selected_projects = resolve_selection(project, False)
    if not selected_projects:
        print("[yellow]No projects registered. Use 'yunetas register-project <path>'.[/yellow]")
        raise typer.Exit(code=1)

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
            chosen = host
        else:
            candidates = {socket.gethostname(), socket.getfqdn()}
            matches = [h for h in hosts if h in candidates]
            if len(matches) != 1:
                print(f"[red]Error: cannot guess the target host for '{proj['name']}'. Pass --host. Available: {', '.join(hosts) or 'none'}[/red]")
                raise typer.Exit(code=1)
            chosen = matches[0]

        config_dir = os.path.join(batches_dir, chosen)
        print(f"[cyan]Syncing configs: {proj['name']} ({config_dir})[/cyan]")
        ret = run_agent_tool("sync_configs.py", list(ctx.args) + [config_dir])
        synced += 1
        if ret != 0:
            exit_code = ret

    if synced == 0:
        print("[yellow]Nothing synced: no registered project has a matching batches/<host>/ directory.[/yellow]")
        raise typer.Exit(code=1)
    raise typer.Exit(code=exit_code)


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


def project_yunos_dir(project):
    """
    Return the buildable yunos/ directory of a registered project.
    """
    return os.path.join(project["path"], "yunos")


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
    """
    if sdk_only and project_names:
        print("[red]Error: --sdk-only and project names are mutually exclusive.[/red]")
        raise typer.Exit(code=1)

    if sdk_only:
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

    return True, registered


def run_agent_tool(script_name, args, cwd=None):
    """
    Run a tool from $YUNETAS_BASE/tools/agent/ forwarding arguments.

    Returns:
        int: the tool's exit code.
    """
    script = os.path.join(YUNETAS_BASE, "tools", "agent", script_name)
    if not os.path.isfile(script):
        print(f"[red]Error: '{script}' not found.[/red]")
        raise typer.Exit(code=1)

    env = os.environ.copy()
    env.setdefault("YUNETAS_BASE", YUNETAS_BASE)
    result = subprocess.run([sys.executable, script] + list(args), cwd=cwd, env=env)
    return result.returncode


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
            print(msg)
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
            print(msg)
            final_messages.append(msg)
        except Exception as e:
            print(f"Error: Unable to generate yuneta_config.h. {e}")
            sys.exit(1)

    msg = f"Setup completed successfully:"
    print(msg)
    final_messages.append(msg)

    msg = f"  - YUNETAS_BASE: {YUNETAS_BASE}"
    print(msg)
    final_messages.append(msg)

    if has_framework_sources:
        msg = f"  - YUNETA_VERSION: {yuneta_version_path2}"
    else:
        msg = f"  - YUNETA_VERSION: (runtime-only SDK, headers shipped in outputs/include)"
    print(msg)
    final_messages.append(msg)

    msg = f"  - [green]'.config'[/green]: {yuneta_config_path}"
    print(msg)
    final_messages.append(msg)

    msg = f"  - Include directory: {inc_dest_dir}"
    print(msg)
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
    """
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
                    ret = -1
                    exit(-1)
            else:
                print(f"[yellow]Skipping {dir_path}: No build directory found[/yellow]")

    return ret
