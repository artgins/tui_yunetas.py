#
#   test_restart_agents.py
#
#   `yunetas restart-agents`: the main agent first, the spare only once the
#   main one answers, never the spare when the main one fails; an agent in its
#   systemd unit through `sudo -n systemctl restart`, one run by hand with
#   --stop and its own command line; nothing for another user's agents.
#   No process is touched: the state and every action are fakes.
#
import os

import pytest
from typer.testing import CliRunner

import yunetas.main as m

runner = CliRunner()
ME = os.geteuid()


def state(name, role, stale=True, running=True, in_unit=False, uid=ME, readable=True):
    procs = []
    if running:
        cmdline = [f"/yuneta/agent/{name}", f"--config-file=/yuneta/agent/{name}.json", "--start"]
        procs = [
            {"pid": 100, "ppid": 1, "uid": uid, "exe": "x", "stale": stale, "cmdline": cmdline},
            {"pid": 101, "ppid": 100, "uid": uid, "exe": "x", "stale": stale, "cmdline": cmdline},
        ]
    return {
        "name": name, "role": role, "procs": procs, "running": running,
        "readable": readable, "stale": running and stale, "uid": uid,
        "watcher": procs[0] if procs else None, "in_unit": in_unit,
        "cmdline": procs[0]["cmdline"] if procs else None,
    }


@pytest.fixture
def fake(monkeypatch):
    log = []
    states = {}
    answers = {"main": True}
    restart_ok = {}

    monkeypatch.setattr(m, "agent_state", lambda name, role: states[name])
    monkeypatch.setattr(m, "agent_disk_version", lambda name: "7.99.0")
    monkeypatch.setattr(m, "backup_running_agent", lambda s: log.append(("backup", s["name"])) or "/bak")

    def restart_agent(s, dry_run):
        log.append(("restart", s["name"], "unit" if s["in_unit"] else "hand", dry_run))
        return restart_ok.get(s["name"], True)

    def agent_answers():
        log.append(("answers",))
        return answers["main"]

    monkeypatch.setattr(m, "restart_agent", restart_agent)
    monkeypatch.setattr(m, "agent_answers", agent_answers)
    return log, states, answers, restart_ok


def run(*args):
    return runner.invoke(m.app, ["restart-agents", "-y"] + list(args))


def test_main_first_then_the_spare(fake):
    log, states, _, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main")
    states["yuneta_agent22"] = state("yuneta_agent22", "spare")
    r = run()
    assert r.exit_code == 0, r.output
    assert log == [
        ("backup", "yuneta_agent"),
        ("restart", "yuneta_agent", "hand", False),
        ("answers",),
        ("backup", "yuneta_agent22"),
        ("restart", "yuneta_agent22", "hand", False),
    ]


def test_a_failed_main_leaves_the_spare_alone(fake):
    log, states, _, restart_ok = fake
    states["yuneta_agent"] = state("yuneta_agent", "main")
    states["yuneta_agent22"] = state("yuneta_agent22", "spare")
    restart_ok["yuneta_agent"] = False
    r = run()
    assert r.exit_code == 1
    assert ("restart", "yuneta_agent22", "hand", False) not in log
    assert "was NOT touched" in r.output


def test_a_silent_main_leaves_the_spare_alone(fake):
    log, states, answers, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main", stale=False)
    states["yuneta_agent22"] = state("yuneta_agent22", "spare")
    answers["main"] = False
    r = run()
    assert r.exit_code == 1
    assert log == [("answers",)]


def test_only_the_spare_when_the_main_is_current(fake):
    log, states, _, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main", stale=False)
    states["yuneta_agent22"] = state("yuneta_agent22", "spare", in_unit=True)
    r = run()
    assert r.exit_code == 0, r.output
    assert log == [("answers",), ("backup", "yuneta_agent22"), ("restart", "yuneta_agent22", "unit", False)]


def test_nothing_stale_does_nothing(fake):
    log, states, _, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main", stale=False)
    states["yuneta_agent22"] = state("yuneta_agent22", "spare", stale=False)
    r = run()
    assert r.exit_code == 0, r.output
    assert "Nothing to do" in r.output
    assert log == []


def test_main_not_running_is_an_error(fake):
    log, states, _, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main", running=False)
    states["yuneta_agent22"] = state("yuneta_agent22", "spare")
    r = run()
    assert r.exit_code == 1
    assert log == []


def test_another_users_agents_are_refused(fake):
    log, states, _, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main", uid=ME + 1, readable=False)
    states["yuneta_agent22"] = state("yuneta_agent22", "spare")
    r = run()
    assert r.exit_code == 1
    assert "Run this command as" in r.output
    assert log == []


def test_dry_run_runs_nothing(fake):
    log, states, _, _ = fake
    states["yuneta_agent"] = state("yuneta_agent", "main")
    states["yuneta_agent22"] = state("yuneta_agent22", "spare")
    r = runner.invoke(m.app, ["restart-agents", "-n"])
    assert r.exit_code == 0, r.output
    assert all(entry[0] == "restart" and entry[3] is True for entry in log)
    assert "dry-run" in r.output


#
#   The two ways restart_agent() restarts, with subprocess faked
#
def test_restart_in_the_unit_uses_systemctl(monkeypatch):
    calls = []
    monkeypatch.setattr(m.subprocess, "run", lambda cmd, **k: calls.append(cmd) or
                        m.subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(m, "wait_agent_up", lambda name, old: True)
    assert m.restart_agent(state("yuneta_agent", "main", in_unit=True), False)
    assert calls == [["sudo", "-n", "systemctl", "restart", "yuneta_agent"]]


def test_restart_by_hand_stops_then_starts_its_own_command_line(monkeypatch):
    calls = []
    monkeypatch.setattr(m.subprocess, "run", lambda cmd, **k: calls.append(cmd) or
                        m.subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(m, "wait_agent_gone", lambda name, old: True)
    monkeypatch.setattr(m, "wait_agent_up", lambda name, old: True)
    assert m.restart_agent(state("yuneta_agent22", "spare"), False)
    assert calls == [
        ["/yuneta/agent/yuneta_agent22", "--config-file=/yuneta/agent/yuneta_agent22.json", "--stop"],
        ["/yuneta/agent/yuneta_agent22", "--config-file=/yuneta/agent/yuneta_agent22.json", "--start"],
    ]


def test_restart_by_hand_does_not_start_while_the_old_one_runs(monkeypatch):
    calls = []
    monkeypatch.setattr(m.subprocess, "run", lambda cmd, **k: calls.append(cmd) or
                        m.subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(m, "wait_agent_gone", lambda name, old: False)
    assert not m.restart_agent(state("yuneta_agent22", "spare"), False)
    assert len(calls) == 1 and calls[0][-1] == "--stop"


def test_agent_watcher_is_the_process_whose_parent_is_not_one_of_them():
    procs = state("yuneta_agent", "main")["procs"]
    assert m.agent_watcher(list(reversed(procs)))["pid"] == 100


def test_config_file_from_the_command_line():
    assert m.agent_config_file("a", ["/x", "--config-file", "/c.json", "--start"]) == "/c.json"
    assert m.agent_config_file("a", ["/x", "--config-file=/d.json"]) == "/d.json"
    assert m.agent_config_file("a", None) == "/yuneta/agent/a.json"
