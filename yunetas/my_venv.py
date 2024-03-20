import typer

app_venv = typer.Typer()


@app_venv.command()
def create(venv_name: str):
    print(f"Creating venv: {venv_name}")


@app_venv.command()
def delete(venv_name: str):
    print(f"Deleting venv: {venv_name}")


@app_venv.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Manage virtual environments
    """
    if ctx.invoked_subcommand is None:
        # No subcommand was provided, so we print the help.
        typer.main.get_command(app_venv).get_help(ctx)
        raise typer.Exit(code=1)
