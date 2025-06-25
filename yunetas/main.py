import typer
from rich import print
from rich.console import Console
from .__version__ import __version__
from .my_venv import app_venv
from typing import Optional, List
from pathlib import Path
import os
import sys
import subprocess
import shutil
from datetime import datetime

# Check if YUNETAS_BASE is set, or derive it from the current directory if YUNETA_VERSION exists
YUNETAS_BASE = os.getenv("YUNETAS_BASE")
current_dir = os.getcwd()
yuneta_version_path = os.path.join(current_dir, "YUNETA_VERSION")

if not YUNETAS_BASE:
    if os.path.isfile(yuneta_version_path):
        YUNETAS_BASE = current_dir
        print(f"[yellow]YUNETAS_BASE not set. Using current directory as YUNETAS_BASE: {YUNETAS_BASE}[/yellow]")
    else:
        print("[red]Error: YUNETAS_BASE environment variable is not set and YUNETA_VERSION file not found in the current directory.[/red]")
        sys.exit(1)

if not os.path.isdir(YUNETAS_BASE):
    print(f"[red]Error: YUNETAS_BASE '{YUNETAS_BASE}' does not exist or is not a directory.[/red]")
    sys.exit(1)


# Directories to process
DIRECTORIES = [
    "kernel/c/gobj-c",
    "kernel/c/libjwt",
    "kernel/c/ytls",
    "kernel/c/yev_loop",
    "kernel/c/timeranger2",
    "kernel/c/root-linux",
    "kernel/c/root-esp32",
    "modules/c/*",
    "stress/c/*",
    "utils/c/*",
    "yunos/c/*",
]

# Create the app.
app = typer.Typer(help="TUI for yunetas SDK")
app.add_typer(app_venv, name="venv")

state = {"verbose": False}
console = Console()


@app.command()
def init():
    """
    Initialize yunetas, create build directories and get compiler and build type from .config (menuconfig)
    """
    if state["verbose"]:
        print("Initialize yunetas in Production mode")
    setup_yuneta_environment(True)
    process_directories(DIRECTORIES)
    process_directories(["."])

    if state["verbose"]:
        print("Done")


# TODO need to compile with musl
# sudo ln -s /usr/include/x86_64-linux-gnu/asm /usr/include/x86_64-linux-musl
# sudo ln -s /usr/include/linux /usr/include/x86_64-linux-musl
# sudo ln -s /usr/include/asm-generic /usr/include/x86_64-linux-musl


@app.command()
def build():
    """
    Build and install yunetas.
    """
    if state["verbose"]:
        print("Building and installing yunetas")
    setup_yuneta_environment(False)
    process_build_command(DIRECTORIES, ["make", "install"])
    if state["verbose"]:
        print("Done")


@app.command()
def clean():
    """
    Clean up build directories in yunetas.
    """
    if state["verbose"]:
        print("Cleaning up build directories in yunetas")
    process_build_command(DIRECTORIES, ["make", "clean"])
    if state["verbose"]:
        print("Done")


@app.command()
def test():
    """
    Run ctest in yunetas
    """
    if state["verbose"]:
        print("Run ctest in yunetas in debug mode")

    process_build_command(DIRECTORIES, ["make", "install"])
    ret = process_build_command(["."], ["make", "install"])
    if ret == 0:
        process_build_command(["."], ["ctest"])

    if state["verbose"]:
        print("Done")


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

    if not os.path.isfile(yuneta_version_path2):
        print(f"Error: YUNETA_VERSION file not found in '{YUNETAS_BASE}'.")
        sys.exit(1)

    if not os.path.isfile(yuneta_config_path):
        print(f"Error: .config file not found in '{YUNETAS_BASE}'.")
        sys.exit(1)


    #--------------------------------------------------#
    #   Detect compiler from .config (Clang, GCC, musl)
    #--------------------------------------------------#
    compiler = get_compiler_from_config()
    as_static = False
    if compiler == "musl":
        as_static = True

    #--------------------------------------------------#
    # Get parent directory of YUNETAS_BASE and set up output directories
    #--------------------------------------------------#
    yunetas_parent_base_dir = os.path.dirname(YUNETAS_BASE)
    if as_static:
        outputs_dir = os.path.join(yunetas_parent_base_dir, "outputs_static")
    else:
        outputs_dir = os.path.join(yunetas_parent_base_dir, "outputs")
    inc_dest_dir = os.path.join(outputs_dir, "include")
    lib_dest_dir = os.path.join(outputs_dir, "lib")
    bin_dest_dir = os.path.join(outputs_dir, "bin")
    yunos_dest_dir = os.path.join(outputs_dir, "yunos")

    try:
        if reset_outputs:
            if os.path.isdir(inc_dest_dir):
                shutil.rmtree(inc_dest_dir)
            if os.path.isdir(lib_dest_dir):
                shutil.rmtree(lib_dest_dir)
            if os.path.isdir(bin_dest_dir):
                shutil.rmtree(bin_dest_dir)
            if os.path.isdir(yunos_dest_dir):
                shutil.rmtree(yunos_dest_dir)
        # Create 'outputs/include' directory if it doesn't exist
        os.makedirs(inc_dest_dir, exist_ok=True)
        os.makedirs(lib_dest_dir, exist_ok=True)
        os.makedirs(bin_dest_dir, exist_ok=True)
        os.makedirs(yunos_dest_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Unable to create directory '{inc_dest_dir}'. {e}")
        sys.exit(1)

    #--------------------------------------------------#
    # Generate yuneta_version.h from YUNETA_VERSION
    #--------------------------------------------------#
    yuneta_version_h_path = os.path.join(inc_dest_dir, "yuneta_version.h")
    if is_file_outdated(yuneta_version_path2, yuneta_version_h_path):
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
            print(f"Generated 'yuneta_version.h' at {yuneta_version_h_path}")
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
            print(f"Generated 'yuneta_config.h' at {yuneta_config_h_path}")
        except Exception as e:
            print(f"Error: Unable to generate yuneta_config.h. {e}")
            sys.exit(1)

    print(f"Setup completed successfully:")
    print(f"  - YUNETAS_BASE: {YUNETAS_BASE}")
    print(f"  - YUNETA_VERSION: {yuneta_version_path2}")
    print(f"  - .config: {yuneta_config_path}")
    print(f"  - Include directory: {inc_dest_dir}")


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
            elif line == "CONFIG_USE_COMPILER_MUSL=y":
                return "musl"

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
                return "RelWithDebInfo"
            elif line == "CONFIG_BUILD_TYPE_DEBUG=y":
                return "Debug"
            else:
                return "RelWithDebInfo"

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

    musl_toolchain = f"{base_path}/tools/cmake/musl-toolchain.cmake"

    #--------------------------------------------------#
    #   Detect compiler from .config (Clang, GCC, musl)
    #--------------------------------------------------#
    compiler = get_compiler_from_config()
    build_type = get_build_type_from_config()
    CC = None
    as_static = False
    if compiler == "clang":
        CC = "/usr/bin/clang"
        as_static = False
    elif compiler == "gcc":
        CC = "/usr/bin/gcc"
        as_static = False
    elif compiler == "musl":
        CC = "/usr/bin/musl-gcc"
        as_static = True

    for directory in directories:
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
                    if as_static:
                        cmake_command.append(f"-DCMAKE_TOOLCHAIN_FILE={musl_toolchain}")
                    cmake_command.append("..")

                    print(f"[blue]Running cmake command in {build_dir}[/blue]")
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
