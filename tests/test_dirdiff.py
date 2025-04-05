import unittest

from configdiff.dirdiff import (DIFFERENT, ONLY_NEW, ONLY_OLD, SAME, compare_dirs,
                                list_configs)
from tests.helpers import TempDirTestCase, fixture


class ListConfigsTests(TempDirTestCase):
    def test_only_recognised_files_in_sorted_relative_form(self):
        self.write("b.json", "{}")
        self.write("a/z.yaml", "")
        self.write("a/notes.txt", "x")
        self.write("prod.env", "")
        self.assertEqual(list_configs(self.tmp), ["a/z.yaml", "b.json", "prod.env"])


class CompareDirsTests(unittest.TestCase):
    def test_statuses(self):
        seen = []

        def compare(old, new):
            seen.append((old.endswith("app.json"), new.endswith("app.json")))
            return ["change"] if old.endswith("app.json") else []

        results = compare_dirs(fixture("envs/old"), fixture("envs/new"), compare)
        self.assertEqual([(r.name, r.status) for r in results], [
            ("added.ini", ONLY_NEW),
            ("app.json", DIFFERENT),
            ("db.env", SAME),
            ("nested/cache.yaml", SAME),
            ("removed.toml", ONLY_OLD),
        ])
        self.assertEqual(results[1].changes, ["change"])


if __name__ == "__main__":
    unittest.main()
