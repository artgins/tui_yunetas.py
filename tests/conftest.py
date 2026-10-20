#
#   conftest.py
#
#   A fake ycommand for the tests of the agent tools: a shell script that
#   answers each `-c <command>` with a canned output and logs the commands it
#   was asked, so a tool runs end to end with no agent behind it.
#
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def shell_quote(text):
    return "'" + text.replace("'", "'\\''") + "'"


@pytest.fixture
def fake_ycommand(tmp_path):
    """
    make(answers, default) -> (path, log): `answers` maps a command to its
    output; any other command answers `default`.
    """
    def make(answers, default="[]"):
        log = tmp_path / "ycommand.log"
        lines = [
            "#!/bin/sh",
            'for a in "$@"; do cmd="$a"; done',
            'echo "$cmd" >> %s' % shell_quote(str(log)),
            'case "$cmd" in',
        ]
        for cmd, out in answers.items():
            lines.append("    %s) echo %s;;" % (shell_quote(cmd), shell_quote(out)))
        lines.append("    *) echo %s;;" % shell_quote(default))
        lines.append("esac")
        path = tmp_path / "ycommand"
        path.write_text("\n".join(lines) + "\n")
        path.chmod(0o755)
        return path, log

    return make


def run_tool(module, args, env=None):
    """Run `python -m yunetas.agent_tools.<module> <args>`; returns CompletedProcess."""
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = str(REPO)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "yunetas.agent_tools.%s" % module] + list(args),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, env=full_env, timeout=60,
    )


def asked(log):
    """The commands the fake ycommand was asked, in order."""
    if not log.exists():
        return []
    return log.read_text().splitlines()
