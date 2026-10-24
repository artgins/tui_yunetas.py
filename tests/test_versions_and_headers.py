#
#   Tests of two things a yuno's version depends on:
#
#   - version_tuple() / cmp_versions() of the agent tools split at '.' AND
#     '-', as version_cmp() of the SDK does: a yuno built with the SDK
#     carries it after a '-' (`"1.9.1" "-" YUNETA_VERSION`);
#   - the generated headers (yuneta_version.h, yuneta_config.h) are written
#     when their TEXT changes, not when their source is newer.
#
#       python -m unittest discover -s tests
#
import os
import tempfile
import unittest

from yunetas import main
from yunetas.agent_tools.common import (
    cmp_versions, version_has_a_comparable_shape, version_tuple,
)


class Versions(unittest.TestCase):
    def test_the_sdk_after_a_dash_is_compared(self):
        self.assertEqual(version_tuple("1.9.1-7.27.11"), (1, 9, 1, 7, 27, 11))
        ordered = [
            "1.9.1.0",          # the form before the SDK was in the version
            "1.9.1-7.27.11",
            "1.9.1-7.27.19",
            "1.9.1-7.27.20",
            "1.9.1-7.28.0",
            "1.9.1-8.0.0",      # split at '.' alone, "1-8" read as 1
            "1.9.2-7.27.11",
        ]
        for older, newer in zip(ordered, ordered[1:]):
            self.assertEqual(cmp_versions(older, newer), -1, f"{older} < {newer}")
            self.assertEqual(cmp_versions(newer, older), 1, f"{newer} > {older}")
        self.assertEqual(cmp_versions("1.9.1-7.27.11", "1.9.1-7.27.11"), 0)

    def test_plain_versions_as_before(self):
        self.assertEqual(cmp_versions("7.27.10", "7.27.11"), -1)
        self.assertEqual(cmp_versions("7.11", "7.11.0"), 0)
        self.assertEqual(cmp_versions("12", "13"), -1)


class VersionShapes(unittest.TestCase):
    #   The same table as the agent's test (c_agent_find_new_yunos)
    def test_the_shapes_that_compare_in_order(self):
        for v in ("7.27.11", "1.9.1-7.27.11", "1.9.1.0"):
            self.assertTrue(version_has_a_comparable_shape(v), v)

    def test_the_shapes_that_do_not(self):
        for v in ("1.0-7.27.11", "1.0.0.1-7.27.11", "1.9.1-7.27", "1.9.1-7.27.11-2",
                  "1.9", "1.9.1.", "v1.9.1", "", "?"):
            self.assertFalse(version_has_a_comparable_shape(v), v)

    def test_why_two_own_numbers_are_refused(self):
        #   1.0 is older than 1.0.1, but with the SDK after it the 7 lands
        #   where the 1 is: the agent would take 1.0-7.27.11 for the newer
        self.assertEqual(cmp_versions("1.0-7.27.11", "1.0.1-7.27.11"), 1)


class GeneratedHeaders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "yuneta_version.h")

    def tearDown(self):
        self.tmp.cleanup()

    def test_written_when_the_text_changes(self):
        self.assertTrue(main.write_generated_header(self.path, "A\n"))
        self.assertFalse(main.write_generated_header(self.path, "A\n"))
        self.assertTrue(main.write_generated_header(self.path, "B\n"))
        with open(self.path) as f:
            self.assertEqual(f.read(), "B\n")

    def test_the_same_text_keeps_the_file_untouched(self):
        main.write_generated_header(self.path, "A\n")
        os.utime(self.path, (1000, 1000))
        self.assertFalse(main.write_generated_header(self.path, "A\n"))
        self.assertEqual(os.path.getmtime(self.path), 1000)

    def test_a_source_older_than_the_header_still_moves_it(self):
        #   The old rule (source newer than header) kept "7.27.10" here
        main.write_generated_header(self.path, '#define YUNETA_VERSION "7.27.10"\n')
        os.utime(self.path, (2000000000, 2000000000))
        self.assertTrue(main.write_generated_header(self.path, '#define YUNETA_VERSION "7.27.11"\n'))


if __name__ == "__main__":
    unittest.main()
