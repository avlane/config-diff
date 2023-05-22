import unittest

from configdiff.loaders import ConfigError, detect_format, load_file, load_json
from tests.helpers import TempDirTestCase


class JsonTests(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(load_json('{"a": [1, 2, {"b": null}]}'), {"a": [1, 2, {"b": None}]})

    def test_error_mentions_position(self):
        with self.assertRaises(ConfigError) as ctx:
            load_json('{"a": }')
        self.assertIn("invalid JSON", str(ctx.exception))
        self.assertIn("line 1", str(ctx.exception))


class LoadFileTests(TempDirTestCase):
    def test_detects_json_by_extension(self):
        self.assertEqual(detect_format("x/y/app.JSON"), "json")

    def test_unknown_extension(self):
        with self.assertRaises(ConfigError) as ctx:
            detect_format("notes.txt")
        self.assertIn("notes.txt", str(ctx.exception))

    def test_load_file(self):
        path = self.write("a.json", '{"k": "v"}')
        self.assertEqual(load_file(path), {"k": "v"})

    def test_explicit_format_overrides_extension(self):
        path = self.write("settings.conf", '{"k": 1}')
        self.assertEqual(load_file(path, "json"), {"k": 1})

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as ctx:
            load_file(self.tmp + "/nope.json")
        self.assertIn("cannot read", str(ctx.exception))

    def test_parse_errors_name_the_file(self):
        path = self.write("bad.json", "{")
        with self.assertRaises(ConfigError) as ctx:
            load_file(path)
        self.assertIn("bad.json", str(ctx.exception))

    def test_invalid_utf8(self):
        path = self.write("latin.json", '{"a": "caf\xe9"}', encoding="latin-1")
        with self.assertRaises(ConfigError) as ctx:
            load_file(path)
        self.assertIn("UTF-8", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
