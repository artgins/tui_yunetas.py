#
#   test_agent_tools_exit_code.py
#
#   A tool that failed a push must exit non-zero. Up to 0.21.2 the three
#   tools printed "Done: 0 ok, 1 failed" and exited 0, so `yunetas sync` went
#   on to push the configs after the binaries had failed, and no script could
#   tell.
#
import json

import pytest

from conftest import asked, run_tool

FAIL = "ERROR: simulated failure"


#
#   sync_binaries: one BUMP (local 1.1.0 over the agent's 1.0.0)
#
def binaries_setup(tmp_path, fake_ycommand, push_answer):
    yunos = tmp_path / "yunos"
    yunos.mkdir()
    gate = yunos / "gate"
    gate.write_text(
        "#!/bin/sh\n"
        "echo '{\"role\": \"gate\", \"version\": \"1.1.0\", \"date\": \"2026-10-20T00:00:00Z\"}'\n"
    )
    gate.chmod(0o755)
    ycommand, log = fake_ycommand(
        {
            "*list-binaries": json.dumps([{"id": "gate", "version": "1.0.0", "size": 1, "time": 1}]),
            "*list-binaries-instances": "[]",
            "*list-yunos": "[]",
        },
        default=push_answer,
    )
    return ["--ycommand", str(ycommand), "--yunos-dir", str(yunos), "-a"], log


@pytest.mark.parametrize("answer,code", [(FAIL, 1), ("[]", 0)])
def test_sync_binaries_exit_code(tmp_path, fake_ycommand, answer, code):
    args, log = binaries_setup(tmp_path, fake_ycommand, answer)
    r = run_tool("sync_binaries", args)
    assert r.returncode == code, r.stdout + r.stderr
    assert any(c.startswith("install-binary id=gate") for c in asked(log))


#
#   sync_configs: one NEW config
#
@pytest.mark.parametrize("answer,code", [(FAIL, 1), ("[]", 0)])
def test_sync_configs_exit_code(tmp_path, fake_ycommand, answer, code):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "foo.1.json").write_text('{"__version__": "1", "__description__": "x"}')
    ycommand, log = fake_ycommand(
        {"*list-configs": "[]", "*list-configs-instances": "[]"},
        default=answer,
    )
    r = run_tool("sync_configs", ["--ycommand", str(ycommand), "-a", str(cfg)])
    assert r.returncode == code, r.stdout + r.stderr
    assert any(c.startswith("create-config id='foo.1'") for c in asked(log))


#
#   set_start_priorities: one logcenter to move from 5 to 1
#
@pytest.mark.parametrize("answer,code", [(FAIL, 1), ("[]", 0)])
def test_set_start_priorities_exit_code(fake_ycommand, answer, code):
    ycommand, log = fake_ycommand(
        {"*list-yunos": json.dumps([{"id": "1", "yuno_role": "logcenter", "start_priority": 5}])},
        default=answer,
    )
    r = run_tool("set_start_priorities", ["--ycommand", str(ycommand), "-a"])
    assert r.returncode == code, r.stdout + r.stderr
    assert any("command=update-node" in c for c in asked(log))


#
#   sync_binaries --role: only those roles are candidates
#
def test_sync_binaries_role_keeps_only_that_role(tmp_path, fake_ycommand):
    yunos = tmp_path / "yunos"
    yunos.mkdir()
    for role in ("gate", "dba"):
        f = yunos / role
        f.write_text(
            "#!/bin/sh\n"
            "echo '{\"role\": \"%s\", \"version\": \"1.1.0\", \"date\": \"2026-10-20T00:00:00Z\"}'\n" % role
        )
        f.chmod(0o755)
    ycommand, log = fake_ycommand({
        "*list-binaries": json.dumps([
            {"id": "gate", "version": "1.0.0", "size": 1, "time": 1},
            {"id": "dba", "version": "1.0.0", "size": 1, "time": 1},
        ]),
        "*list-binaries-instances": "[]",
        "*list-yunos": "[]",
    })
    base = ["--ycommand", str(ycommand), "--yunos-dir", str(yunos), "-a"]

    r = run_tool("sync_binaries", base + ["--role", "gate"])
    assert r.returncode == 0, r.stdout + r.stderr
    pushed = [c for c in asked(log) if c.startswith("install-binary")]
    assert len(pushed) == 1 and pushed[0].startswith("install-binary id=gate")

    r = run_tool("sync_binaries", base + ["--role", "nope"])
    assert r.returncode == 2
    assert "not a binary installed in this agent" in r.stdout


def test_sync_binaries_role_without_a_local_build_is_an_error(tmp_path, fake_ycommand):
    yunos = tmp_path / "yunos"
    yunos.mkdir()
    ycommand, log = fake_ycommand({
        "*list-binaries": json.dumps([{"id": "gate", "version": "1.0.0", "size": 1, "time": 1}]),
        "*list-binaries-instances": "[]",
        "*list-yunos": "[]",
    })
    r = run_tool("sync_binaries", ["--ycommand", str(ycommand), "--yunos-dir", str(yunos),
                                   "-a", "--role", "gate"])
    assert r.returncode == 2, r.stdout + r.stderr
    assert "no local build" in r.stdout
    assert "up to date" not in r.stdout
    assert not any(c.startswith(("install-binary", "update-binary")) for c in asked(log))
