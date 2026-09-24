#
#   Tests of `yunetas upgrade-yunos`
#
#   The agent is not reached: run_ycommand() is replaced by a fake that
#   answers each ycommand line with a canned output and records what was
#   asked. Run with the Python that has the CLI installed (typer, rich):
#
#       python -m unittest discover -s tests
#
import json
import unittest

from typer.testing import CliRunner

from yunetas import main


#
#   A fake agent
#
CREATE = "create-yuno id=gate^one realm_id=r yuno_role=gate yuno_name=one role_version=1.2.0 name_version=1"
REGISTERED = ("already registered, pending promotion (deactivate-snap): "
              "create-yuno id=gate^two realm_id=r yuno_role=gate yuno_name=two role_version=1.2.0 name_version=1")


class FakeAgent:
    def __init__(self, preview, create_out="[]", create_ok=True):
        self.preview = preview
        self.create_out = create_out
        self.create_ok = create_ok
        self.asked = []

    def run_ycommand(self, ycommand, url, cmd_str, dry_run=False, timeout=300, echo_output=True):
        self.asked.append(cmd_str)
        if cmd_str == "find-new-yunos":
            return True, json.dumps(self.preview)
        if cmd_str == "find-new-yunos create=1":
            return self.create_ok, self.create_out
        return True, ""


class UpgradeYunosTest(unittest.TestCase):
    def setUp(self):
        self.saved = {
            name: getattr(main, name)
            for name in ("run_ycommand", "ycommand_path", "active_snap_name", "snap_exists")
        }
        main.ycommand_path = lambda: "/usr/bin/true"
        main.active_snap_name = lambda ycommand, url: None
        main.snap_exists = lambda ycommand, url, name: False

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(main, name, value)

    def run_upgrade(self, agent):
        main.run_ycommand = agent.run_ycommand
        return CliRunner().invoke(main.app, ["upgrade-yunos", "-y", "--no-snap"])

    def test_split_preview(self):
        to_create, registered = main.split_find_new_yunos_preview([CREATE, REGISTERED])
        self.assertEqual(to_create, [CREATE])
        self.assertEqual(registered, [REGISTERED])

    def test_counts_created_and_registered_apart(self):
        agent = FakeAgent([CREATE, REGISTERED])
        result = self.run_upgrade(agent)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("1 new yuno row(s) would be created", result.output)
        self.assertIn("1 yuno row(s) already registered, pending promotion", result.output)
        self.assertIn("1 created, 1 already registered", result.output)
        self.assertNotIn("Created 2", result.output)
        self.assertEqual(
            agent.asked,
            ["find-new-yunos", "find-new-yunos create=1", "deactivate-snap"]
        )

    def test_only_registered_rows_go_on_to_promote(self):
        agent = FakeAgent([REGISTERED])
        result = self.run_upgrade(agent)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("0 created, 1 already registered", result.output)
        self.assertEqual(agent.asked, ["find-new-yunos", "deactivate-snap"])

    def test_empty_preview_does_nothing(self):
        agent = FakeAgent([])
        result = self.run_upgrade(agent)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Nothing to do", result.output)
        self.assertEqual(agent.asked, ["find-new-yunos"])

    def test_old_agent_already_exists_still_promotes(self):
        agent = FakeAgent([CREATE], create_out="ERROR: Yuno already exists", create_ok=False)
        result = self.run_upgrade(agent)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("already registered by a prior run", result.output)
        self.assertEqual(agent.asked[-1], "deactivate-snap")

    def test_create_failure_aborts_before_restart(self):
        agent = FakeAgent([CREATE], create_out="ERROR: binary not found", create_ok=False)
        result = self.run_upgrade(agent)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertNotIn("deactivate-snap", agent.asked)


if __name__ == "__main__":
    unittest.main()
