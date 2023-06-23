import unittest

from configdiff.paths import format_path


class FormatPathTests(unittest.TestCase):
    def test_root(self):
        self.assertEqual(format_path(()), "$")

    def test_keys_and_indexes(self):
        self.assertEqual(format_path(("server", "ports", 1, "name")), "server.ports[1].name")

    def test_leading_index(self):
        self.assertEqual(format_path((0, "a")), "[0].a")


if __name__ == "__main__":
    unittest.main()
