#
#   Tests of the yuno role collision check of `yunetas build`
#
#   Two builds (the SDK, registered projects) that install a yuno of the
#   same role overwrite each other in outputs/yunos. The check reads the
#   install_manifest.txt of each build tree; here the trees are made up in
#   a temporary YUNETAS_BASE. Run with the Python that has the CLI
#   installed (typer, rich):
#
#       python -m unittest discover -s tests
#
import os
import tempfile
import unittest

from yunetas import main


class RoleCollisions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        self.saved = (main.YUNETAS_BASE, main.DIRECTORIES)
        main.YUNETAS_BASE = self.base
        main.DIRECTORIES = ["yunos/c/emailsender"]

    def tearDown(self):
        main.YUNETAS_BASE, main.DIRECTORIES = self.saved
        self.tmp.cleanup()

    def install(self, tree, roles):
        build = os.path.join(tree, "build")
        os.makedirs(build, exist_ok=True)
        yunos = os.path.join(self.base, "outputs", "yunos")
        with open(os.path.join(build, "install_manifest.txt"), "w") as f:
            for role in roles:
                f.write(os.path.join(yunos, role) + "\n")
            f.write(os.path.join(self.base, "outputs", "lib", "libx.a") + "\n")

    def project(self, name, roles):
        path = os.path.join(self.base, "projects", name)
        self.install(os.path.join(path, "yunos"), roles)
        return {"name": name, "path": path}

    def test_same_role_in_two_projects(self):
        self.install(os.path.join(self.base, "yunos/c/emailsender"), ["emailsender"])
        hidraulia = self.project("hidraulia", ["gate_caudal", "db_history"])
        yunovatios = self.project("yunovatios", ["gate_caudal", "db_tracks_co"])
        got = main.find_yuno_role_collisions([hidraulia, yunovatios])
        self.assertEqual(got, {"gate_caudal": {"hidraulia", "yunovatios"}})

    def test_project_role_of_the_sdk(self):
        self.install(os.path.join(self.base, "yunos/c/emailsender"), ["emailsender"])
        mine = self.project("mine", ["emailsender"])
        got = main.find_yuno_role_collisions([mine])
        self.assertEqual(got, {"emailsender": {"yunetas", "mine"}})

    def test_no_collision_and_trees_never_installed(self):
        self.install(os.path.join(self.base, "yunos/c/emailsender"), ["emailsender"])
        a = self.project("a", ["gate_a"])
        b = {"name": "b", "path": os.path.join(self.base, "projects", "b")}  # no manifest
        self.assertEqual(main.find_yuno_role_collisions([a, b]), {})


if __name__ == "__main__":
    unittest.main()
