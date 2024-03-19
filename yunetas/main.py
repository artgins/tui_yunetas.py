import sys
import typer
from rich import print
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.console import group

from .my_venv import app as app2
# import .my_venv as my_venv

app = typer.Typer()
app.add_typer(app2, name="venv")

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


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context):
    """
    Manage users in the awesome CLI app.
    """
    # if verbose:
    #     print("Will write verbose output")
    #     state["verbose"] = True
    # print("[bold red]Alert![/bold red] [green]Portal gun[/green] shooting! :boom:")
    #
    # table = Table("Name", "Item")
    # table.add_row("Rick", "Portal Gun")
    # table.add_row("Morty", "Plumbus")
    # console.print(table)
    #
    # data = {
    #     "name": "Rick",
    #     "age": 42,
    #     "items": [{"name": "Portal Gun"}, {"name": "Plumbus"}],
    #     "active": True,
    #     "affiliation": None,
    # }
    # print(data)
    #
    # print(Panel("Hello, [red]World!"))
    # print(Panel.fit("Hello, [red]World!"))
    # print(Panel("Hello, [red]World!", title="Welcome", subtitle="Thank you"))
    #
    # @group()
    # def get_panels():
    #     yield Panel("Hello", style="on blue")
    #     yield Panel("World", style="on red")
    #
    # print(Panel(get_panels()))

    if ctx.invoked_subcommand is None:
        # No subcommand was provided, so we print the help.
        typer.main.get_command(app).get_help(ctx)
        raise typer.Exit(code=1)


def run():
    app()
