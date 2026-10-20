#
#   test_set_start_priorities_command.py
#
#   `yunetas set-start-priorities` runs the bundled tool, forwards the
#   arguments, adds the connection of a registered node, and exits with the
#   tool's code. Up to 0.21.2 the tool shipped in the package with no command
#   to reach it, while the deprecated shim in tools/agent/ sent the operator
#   to this command.
#
from typer.testing import CliRunner

import yunetas.main as m

runner = CliRunner()


def fake_tool(monkeypatch, code):
    seen = []

    def run_agent_tool(script_name, args, cwd=None):
        seen.append((script_name, list(args)))
        return code

    monkeypatch.setattr(m, "run_agent_tool", run_agent_tool)
    return seen


def test_forwards_the_arguments(monkeypatch):
    seen = fake_tool(monkeypatch, 0)
    r = runner.invoke(m.app, ["set-start-priorities", "-n", "--rule", "notifier=2"])
    assert r.exit_code == 0, r.output
    assert seen == [("set_start_priorities.py", ["-n", "--rule", "notifier=2"])]


def test_exits_with_the_tool_code(monkeypatch):
    fake_tool(monkeypatch, 1)
    r = runner.invoke(m.app, ["set-start-priorities", "-a"])
    assert r.exit_code == 1


def test_adds_the_node_connection(monkeypatch):
    seen = fake_tool(monkeypatch, 0)
    monkeypatch.setattr(m, "find_registered_node", lambda name: {"name": name, "url": "ws://127.0.0.1:41000"})
    r = runner.invoke(m.app, ["set-start-priorities", "-N", "prod", "-n"])
    assert r.exit_code == 0, r.output
    assert seen == [("set_start_priorities.py", ["-n", "-u", "ws://127.0.0.1:41000"])]


def test_venv_is_gone():
    r = runner.invoke(m.app, ["venv"])
    assert r.exit_code != 0
    assert "No such command" in r.output
