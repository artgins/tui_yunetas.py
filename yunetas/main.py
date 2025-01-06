import typer
from rich import print
from rich.console import Console
from .__version__ import __version__
from .my_venv import app_venv
from typing import Optional

# Create the app.
app = typer.Typer(help="TUI for yunetas SDK")
app.add_typer(app_venv, name="venv")

state = {"verbose": False}
console = Console()


@app.command()
def create(username: str):
    if state["verbose"]:
        print("About to create a user")
    print(f"Creating user: {username}")
    if state["verbose"]:
        print("Just created a user")


@app.command()
def delete(username: str):
    if state["verbose"]:
        print("About to delete a user")
    print(f"Deleting user: {username}")
    if state["verbose"]:
        print("Just deleted a user")


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
