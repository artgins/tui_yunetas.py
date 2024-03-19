import typer

app = typer.Typer()


@app.command()
def create(venv_name: str):
    print(f"Creating venv: {venv_name}")


@app.command()
def delete(venv_name: str):
    print(f"Deleting venv: {venv_name}")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Manage virtual environments
    """
    if ctx.invoked_subcommand is None:
        # No subcommand was provided, so we print the help.
        typer.main.get_command(app).get_help(ctx)
        raise typer.Exit(code=1)
