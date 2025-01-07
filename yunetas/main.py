import typer
from rich import print
from rich.console import Console
from .__version__ import __version__
from .my_venv import app_venv
from typing import Optional
import os
import sys

# Global variable for YUNETAS_BASE_DIR
YUNETAS_BASE_DIR = os.getenv("YUNETAS_BASE", "/yuneta/development/yunetas")

# Create the app.
app = typer.Typer(help="TUI for yunetas SDK")
app.add_typer(app_venv, name="venv")

state = {"verbose": False}
console = Console()


@app.command()
def init_debug():
    """
    Initialize yunetas in Debug mode
    """
    if state["verbose"]:
        print("Initialize yunetas in Debug mode")
    setup_yuneta_environment()

    if state["verbose"]:
        print("Done")


@app.command()
def init_prod():
    """
    Initialize yunetas in Production mode
    """
    if state["verbose"]:
        print("Initialize yunetas in Production mode")
    setup_yuneta_environment()

    if state["verbose"]:
        print("Done")


@app.command()
def build():
    """
    Build yunetas
    """
    if state["verbose"]:
        print("Build yunetas")
    setup_yuneta_environment()

    if state["verbose"]:
        print("Done")


@app.command()
def clean():
    """
    Clean up generated files from yunetas
    """
    if state["verbose"]:
        print("Clean up generated files from yunetas")
    setup_yuneta_environment()

    if state["verbose"]:
        print("Done")


@app.command()
def test():
    """
    Run tests on yunetas
    """
    if state["verbose"]:
        print("Run tests on yunetas")
    setup_yuneta_environment()

    if state["verbose"]:
        print("Done")


@app.command()
def deploy():
    """
    Deploy yunetas
    """
    if state["verbose"]:
        print("Deploy yunetas")
    setup_yuneta_environment()

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

def setup_yuneta_environment():
    """
    Check and configure Yuneta environment variables, and prepare directories for generated files.
    Ensures YUNETAS_BASE_DIR and its required files exist.
    Generates yuneta_version.h and yuneta_config.h using kconfig2include.
    """
    #--------------------------------------------------#
    # Check if YUNETAS_BASE_DIR exists
    #--------------------------------------------------#
    if not os.path.isdir(YUNETAS_BASE_DIR):
        print(f"Error: YUNETAS_BASE_DIR '{YUNETAS_BASE_DIR}' does not exist or is not a directory.")
        sys.exit(1)

    #--------------------------------------------------#
    # Check if YUNETA_VERSION and .config files exist in YUNETAS_BASE_DIR
    #--------------------------------------------------#
    yuneta_version_path = os.path.join(YUNETAS_BASE_DIR, "YUNETA_VERSION")
    yuneta_config_path = os.path.join(YUNETAS_BASE_DIR, ".config")

    if not os.path.isfile(yuneta_version_path):
        print(f"Error: YUNETA_VERSION file not found in '{YUNETAS_BASE_DIR}'.")
        sys.exit(1)

    if not os.path.isfile(yuneta_config_path):
        print(f"Error: .config file not found in '{YUNETAS_BASE_DIR}'.")
        sys.exit(1)

    #--------------------------------------------------#
    # Get parent directory of YUNETAS_BASE_DIR and set up output directories
    #--------------------------------------------------#
    yunetas_parent_base_dir = os.path.dirname(YUNETAS_BASE_DIR)
    outputs_dir = os.path.join(yunetas_parent_base_dir, "outputs")
    inc_dest_dir = os.path.join(outputs_dir, "include")

    try:
        # Create 'outputs/include' directory if it doesn't exist
        os.makedirs(inc_dest_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Unable to create directory '{inc_dest_dir}'. {e}")
        sys.exit(1)

    #--------------------------------------------------#
    # Generate yuneta_version.h from YUNETA_VERSION
    #--------------------------------------------------#
    yuneta_version_h_path = os.path.join(inc_dest_dir, "yuneta_version.h")
    if is_file_outdated(yuneta_version_path, yuneta_version_h_path):
        version_header_content = """\
/*
 *  Yuneta Version
 *  Automatically generated file. DO NOT EDIT.
 *  Set version in YUNETA_VERSION file.
 *
 *  Copyright (c) 2024, ArtGins
 */
#pragma once

"""
        try:
            version_header_content += kconfig2include(yuneta_version_path)

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
        config_header_content = """\
/*
 *  Yuneta Configuration
 *  Automatically generated file. DO NOT EDIT.
 *  Set configuration in .config file.
 *
 *  Copyright (c) 2024, ArtGins
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
    print(f"  - YUNETAS_BASE_DIR: {YUNETAS_BASE_DIR}")
    print(f"  - YUNETA_VERSION: {yuneta_version_path}")
    print(f"  - .config: {yuneta_config_path}")
    print(f"  - Include directory: {inc_dest_dir}")


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
