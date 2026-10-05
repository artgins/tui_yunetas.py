"""
`yunetas test` and `yunetas build`: the commands they run, with
process_build_command replaced (nothing is built).
"""
import os

import pytest
from typer.testing import CliRunner

import yunetas.main as m

runner = CliRunner()


@pytest.fixture
def calls(monkeypatch, tmp_path):
    seen = []

    def fake(directories, command):
        seen.append((list(directories), list(command)))
        return 0

    monkeypatch.setattr(m, "process_build_command", fake)
    monkeypatch.setattr(m, "ensure_ext_libs_installed", lambda: None)
    monkeypatch.setattr(m, "setup_yuneta_environment", lambda *a, **k: None)
    monkeypatch.setattr(m, "find_yuno_role_collisions", lambda *a, **k: {})
    monkeypatch.setattr(m, "load_registered_projects", lambda: [])
    monkeypatch.setattr(m, "YUNETAS_BASE", str(tmp_path))
    return seen, tmp_path


def write_version(base, version):
    with open(os.path.join(base, "YUNETA_VERSION"), "w") as f:
        f.write(f"YUNETA_VERSION={version}\n")


def ctest_of(seen):
    return [c for d, c in seen if c[0] == "ctest"][0]


def test_parallel_on_an_sdk_that_passes_it(calls):
    seen, base = calls
    write_version(base, "7.26.3")
    r = runner.invoke(m.app, ["test", "-j", "4"])
    assert r.exit_code == 0, r.output
    assert seen[0][1] == ["make", "-j4", "install"]
    assert ["make", "clean"] not in [c for d, c in seen]
    c = ctest_of(seen)
    assert c[:2] == ["ctest", "-j4"]
    assert c[-1].endswith(".j4.txt") and m.CTEST_LOG_NAME.match(c[-1])


@pytest.mark.parametrize("version", ["7.26.0", "7.26.2"])
def test_serial_on_an_older_sdk(calls, version):
    seen, base = calls
    write_version(base, version)
    r = runner.invoke(m.app, ["test", "-j", "4"])
    assert r.exit_code == 0, r.output
    assert ctest_of(seen)[:2] == ["ctest", "-j1"]
    assert "passes in parallel only since 7.26.3" in r.output


def test_serial_and_clean(calls):
    seen, base = calls
    r = runner.invoke(m.app, ["test", "-j", "3", "--serial", "--clean"])
    assert r.exit_code == 0, r.output
    assert ["make", "clean"] in [c for d, c in seen]
    assert ctest_of(seen)[:2] == ["ctest", "-j1"]
    assert "YUNETA_VERSION" not in r.output     # not read when serial


@pytest.mark.parametrize("jobs", ["0", "-3"])
def test_jobs_below_one_refused(calls, jobs):
    seen, base = calls
    r = runner.invoke(m.app, ["test", "-j", jobs])
    assert r.exit_code != 0
    assert seen == []


def test_build_jobs(calls):
    seen, base = calls
    write_version(base, "7.26.3")
    r = runner.invoke(m.app, ["build", "--sdk-only", "-j", "5"])
    assert r.exit_code == 0, r.output
    assert seen and all(c == ["make", "-j5", "install"] for d, c in seen)


def test_sdk_version(calls):
    seen, base = calls
    write_version(base, "7.26.3")
    assert m.sdk_version() == (7, 26, 3)
    with open(os.path.join(base, "YUNETA_VERSION"), "w") as f:
        f.write("nothing\n")
    assert m.sdk_version() is None
    os.remove(os.path.join(base, "YUNETA_VERSION"))
    assert m.sdk_version() is None


def test_log_name_of_older_runs_still_kept():
    assert m.CTEST_LOG_NAME.match("2026-10-03T23-17-44.624823.txt")
    assert m.CTEST_LOG_NAME.match("2026-10-05T06-14-36.253611.j8.txt")
    assert not m.CTEST_LOG_NAME.match("CMakeCache.txt")
