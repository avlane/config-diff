import os
import unittest

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None

import configdiff

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PackageTests(unittest.TestCase):
    @unittest.skipIf(tomllib is None, "tomllib needs Python 3.11")
    def test_version_matches_pyproject(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(configdiff.__version__, project["version"])

    @unittest.skipIf(tomllib is None, "tomllib needs Python 3.11")
    def test_console_script_target_exists(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
            scripts = tomllib.load(handle)["project"]["scripts"]
        module, _, function = scripts["config-diff"].partition(":")
        self.assertTrue(callable(getattr(__import__(module, fromlist=[function]), function)))


if __name__ == "__main__":
    unittest.main()
