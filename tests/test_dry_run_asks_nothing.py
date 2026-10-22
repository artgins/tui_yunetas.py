#
#   test_dry_run_asks_nothing.py
#
#   `-n` asks nothing: it shows the command of every candidate and runs none.
#   Up to 0.23.0 it ended with "Apply [a]ll, [s]elect one by one, or [q]uit?".
#   With stdin at EOF that answered itself ("Cancelled"), but over ssh from a
#   background job stdin is an open channel, and the dry run waited for an
#   answer for ever (34 minutes on two nodes, 2026-10-21). The tests hold
#   stdin open, as that channel did. Its closing notes say what WOULD happen:
#   up to 0.23.1 they said that the yunos were killed, the slots made and the
#   configs stored.
#
import json
import os
import subprocess
import sys

from conftest import REPO, asked

PUSHES = ("install-binary", "update-binary", "create-config", "update-config",
          "kill-yuno", "run-yuno", "play-yuno")


def run_with_open_stdin(module, args, tmp_path):
    """
    Run a tool with its stdin a pipe that is never written nor closed until
    the tool ends (communicate() would close it at once: an EOF, which
    answers a question with "Cancelled").
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    out_path = tmp_path / ("%s.out" % module)
    with open(out_path, "w") as out_file:
        p = subprocess.Popen(
            [sys.executable, "-m", "yunetas.agent_tools.%s" % module] + list(args),
            stdin=subprocess.PIPE, stdout=out_file, stderr=subprocess.STDOUT,
            text=True, env=env,
        )
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            raise AssertionError("the dry run waited for an answer:\n" + out_path.read_text())
        finally:
            p.stdin.close()
    return p.returncode, out_path.read_text()


def test_sync_binaries_dry_run_asks_nothing(tmp_path, fake_ycommand):
    yunos = tmp_path / "yunos"
    yunos.mkdir()
    for role, version in (("gate", "1.1.0"), ("db", "1.0.0")):
        b = yunos / role
        b.write_text(
            "#!/bin/sh\n"
            "echo '{\"role\": \"%s\", \"version\": \"%s\", \"date\": \"2026-10-21T00:00:00Z\"}'\n"
            % (role, version)
        )
        b.chmod(0o755)
    ycommand, log = fake_ycommand({
        "*list-binaries": json.dumps([
            {"id": "gate", "version": "1.0.0", "size": 1, "time": 1},   # a BUMP
            {"id": "db", "version": "1.0.0", "size": 1, "time": 1},     # a REBUILD
        ]),
        "*list-binaries-instances": "[]",
        "*list-yunos": "[]",
    })
    code, out = run_with_open_stdin(
        "sync_binaries", ["--ycommand", str(ycommand), "--yunos-dir", str(yunos), "-n"], tmp_path)
    assert code == 0, out
    assert "Apply [a]ll" not in out
    assert ">> ycommand -c 'install-binary id=gate" in out
    assert ">> ycommand -c 'update-binary id=db" in out
    assert "none was executed" in out
    assert "would be kill-yuno'd" in out and "were kill-yuno'd" not in out
    assert "would create NEW slot" in out and "created NEW slot" not in out
    note = out[out.index("would create NEW slot"):]
    assert "yunetas upgrade-yunos" in note
    assert "ycommand -c 'find-new-yunos create=1'" in note
    assert "ycommand -c 'deactivate-snap'" in note
    assert not any(c.startswith(PUSHES) for c in asked(log))


def test_sync_configs_dry_run_asks_nothing(tmp_path, fake_ycommand):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "foo.1.json").write_text(json.dumps({"__version__": "2", "x": 2}))
    (cfg / "bar.1.json").write_text(json.dumps({"__version__": "1", "x": 1}))
    ycommand, log = fake_ycommand({
        "*list-configs": json.dumps([{
            "id": "foo.1", "version": "1", "zcontent": {"__version__": "1", "x": 1}, "yunos": ["7"],
        }]),
        "*list-configs-instances": json.dumps([{"id": "foo.1", "version": "1"}]),
        "*list-yunos": json.dumps([{"id": "7", "yuno_running": True, "yuno_playing": True}]),
    })
    code, out = run_with_open_stdin(
        "sync_configs", ["--ycommand", str(ycommand), "-n", "-r", str(cfg)], tmp_path)
    assert code == 0, out
    assert "Apply [a]ll" not in out
    assert "create-config id='foo.1'" in out
    assert "create-config id='bar.1'" in out
    assert "none was executed" in out
    assert "would store a NEW version" in out and "stored a NEW version" not in out
    assert not any(c.startswith(PUSHES) for c in asked(log))
