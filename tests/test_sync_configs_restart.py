#
#   test_sync_configs_restart.py
#
#   `sync-configs -r` restarts the yunos of an UPDATE only. A yuno runs the
#   config version of its own row (name_version), which only find-new-yunos
#   create=1 + deactivate-snap move, so restarting it after a BUMP brought it
#   back on the old version: the tool points at `yunetas upgrade-yunos`
#   instead.
#
import json

from conftest import asked, run_tool
from yunetas.agent_tools import sync_configs


def test_sort_pushed_configs():
    pushed = [
        {"id": "a.1", "kind": "update", "agent": {"yunos": ["7", 8]}},
        {"id": "b.1", "kind": "bump", "agent": {"yunos": ["9"]}},
        {"id": "c.1", "kind": "new", "agent": None},
    ]
    restart, promote, new = sync_configs.sort_pushed_configs(pushed)
    assert restart == {"7", "8"}
    assert promote == {"b.1"}
    assert new == {"c.1"}


def configs_setup(tmp_path, fake_ycommand, local_version, agent_content):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "foo.1.json").write_text(json.dumps({"__version__": local_version, "x": 2}))
    ycommand, log = fake_ycommand({
        "*list-configs": json.dumps([{
            "id": "foo.1", "version": "1", "zcontent": agent_content, "yunos": ["7"],
        }]),
        "*list-configs-instances": json.dumps([{"id": "foo.1", "version": "1"}]),
        "*list-yunos": json.dumps([{"id": "7", "yuno_running": True, "yuno_playing": True}]),
        "*list-yunos id=7": "[]",
    })
    return ["--ycommand", str(ycommand), "-a", "-r", str(cfg)], log


def test_restart_follows_an_update(tmp_path, fake_ycommand):
    args, log = configs_setup(tmp_path, fake_ycommand, "1", {"__version__": "1", "x": 1})
    r = run_tool("sync_configs", args)
    assert r.returncode == 0, r.stdout + r.stderr
    commands = asked(log)
    assert any(c.startswith("update-config id='foo.1'") for c in commands)
    assert "kill-yuno id=7" in commands
    assert "run-yuno id=7 play=0" in commands
    assert "play-yuno id=7" in commands


def test_no_restart_after_a_bump(tmp_path, fake_ycommand):
    args, log = configs_setup(tmp_path, fake_ycommand, "2", {"__version__": "1", "x": 1})
    r = run_tool("sync_configs", args)
    assert r.returncode == 0, r.stdout + r.stderr
    commands = asked(log)
    assert any(c.startswith("create-config id='foo.1'") for c in commands)
    assert not any(c.startswith(("kill-yuno", "run-yuno", "play-yuno")) for c in commands)
    assert "yunetas upgrade-yunos" in r.stdout


def test_a_failed_restart_is_a_failure(tmp_path, fake_ycommand):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "foo.1.json").write_text(json.dumps({"__version__": "1", "x": 2}))
    ycommand, log = fake_ycommand({
        "*list-configs": json.dumps([{
            "id": "foo.1", "version": "1", "zcontent": {"__version__": "1", "x": 1}, "yunos": ["7"],
        }]),
        "*list-configs-instances": "[]",
        "*list-yunos": json.dumps([{"id": "7", "yuno_running": True, "yuno_playing": False}]),
        "*list-yunos id=7": "[]",
        "run-yuno id=7 play=0": "ERROR: cannot run",
    })
    r = run_tool("sync_configs", ["--ycommand", str(ycommand), "-a", "-r", str(cfg)])
    assert r.returncode == 1, r.stdout + r.stderr
    assert "the restart failed" in r.stdout
