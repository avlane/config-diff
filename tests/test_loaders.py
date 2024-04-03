import importlib.util
import unittest

from configdiff.loaders import (ConfigError, detect_format, load_env, load_file, load_ini,
                                load_json, load_toml)
from tests.helpers import TempDirTestCase


class JsonTests(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(load_json('{"a": [1, 2, {"b": null}]}'), {"a": [1, 2, {"b": None}]})

    def test_error_mentions_position(self):
        with self.assertRaises(ConfigError) as ctx:
            load_json('{"a": }')
        self.assertIn("invalid JSON", str(ctx.exception))
        self.assertIn("line 1", str(ctx.exception))


class IniTests(unittest.TestCase):
    def test_sections_and_options(self):
        data = load_ini("[a]\nx = 1\ny: two\n\n[b]\nz = 3\n")
        self.assertEqual(data, {"a": {"x": "1", "y": "two"}, "b": {"z": "3"}})

    def test_option_case_is_preserved(self):
        self.assertEqual(load_ini("[a]\nPassWord = x\n"), {"a": {"PassWord": "x"}})

    def test_percent_signs_are_literal(self):
        self.assertEqual(load_ini("[a]\nfmt = %(asctime)s %d%%\n"), {"a": {"fmt": "%(asctime)s %d%%"}})

    def test_option_without_value(self):
        self.assertEqual(load_ini("[a]\nflag\n"), {"a": {"flag": None}})

    def test_comments_are_ignored(self):
        self.assertEqual(load_ini("# c\n; c\n[a]\n# c\nx = 1\n"), {"a": {"x": "1"}})

    def test_duplicate_section_is_an_error(self):
        with self.assertRaises(ConfigError) as ctx:
            load_ini("[a]\nx=1\n[a]\ny=2\n")
        self.assertIn("invalid INI", str(ctx.exception))

    def test_option_before_any_section_is_an_error(self):
        with self.assertRaises(ConfigError):
            load_ini("x = 1\n")


class EnvTests(unittest.TestCase):
    def test_plain_values_and_comments(self):
        data = load_env("# c\nA=1\n\nB = two words \nC=\n")
        self.assertEqual(data, {"A": "1", "B": "two words", "C": ""})

    def test_export_prefix(self):
        self.assertEqual(load_env("export A=1\n"), {"A": "1"})

    def test_single_quotes_are_literal(self):
        self.assertEqual(load_env("A='x $Y \\n #z'\n"), {"A": "x $Y \\n #z"})

    def test_double_quotes_process_escapes(self):
        self.assertEqual(load_env('A="line1\\nline2 \\"q\\" \\\\ #x"\n'),
                         {"A": 'line1\nline2 "q" \\ #x'})

    def test_multiline_double_quoted_value(self):
        self.assertEqual(load_env('KEY="-----BEGIN-----\nabc\n-----END-----"\nNEXT=1\n'),
                         {"KEY": "-----BEGIN-----\nabc\n-----END-----", "NEXT": "1"})

    def test_inline_comment_only_after_whitespace(self):
        self.assertEqual(load_env("A=x#y # comment\n"), {"A": "x#y"})

    def test_equals_inside_value(self):
        self.assertEqual(load_env("URL=http://h/?a=b\n"), {"URL": "http://h/?a=b"})

    def test_text_after_closing_quote_is_an_error(self):
        with self.assertRaises(ConfigError) as ctx:
            load_env('A="x" y\n')
        self.assertIn("line 1", str(ctx.exception))

    def test_unterminated_quote(self):
        for text in ('A="x\n', "A='x\n"):
            with self.assertRaises(ConfigError):
                load_env(text)

    def test_missing_equals_and_bad_names(self):
        for text in ("JUSTAWORD\n", "1A=x\n", "A B=x\n"):
            with self.assertRaises(ConfigError, msg=text):
                load_env(text)


HAS_TOMLLIB = importlib.util.find_spec("tomllib") is not None


@unittest.skipUnless(HAS_TOMLLIB, "tomllib needs Python 3.11")
class TomlTests(unittest.TestCase):
    def test_tables_arrays_and_types(self):
        data = load_toml('a = 1\nb = "x"\nc = [1, 2]\n[t]\nd = true\n[[l]]\ne = 1\n[[l]]\ne = 2\n')
        self.assertEqual(data, {"a": 1, "b": "x", "c": [1, 2], "t": {"d": True},
                                "l": [{"e": 1}, {"e": 2}]})

    def test_dates_are_real_dates(self):
        import datetime
        self.assertEqual(load_toml("d = 2024-04-06\n"), {"d": datetime.date(2024, 4, 6)})

    def test_error(self):
        with self.assertRaises(ConfigError) as ctx:
            load_toml("a = \n")
        self.assertIn("invalid TOML", str(ctx.exception))

    def test_detects_toml(self):
        self.assertEqual(detect_format("pyproject.toml"), "toml")


class LoadFileTests(TempDirTestCase):
    def test_detects_json_by_extension(self):
        self.assertEqual(detect_format("x/y/app.JSON"), "json")

    def test_detects_ini(self):
        self.assertEqual(detect_format("a.ini"), "ini")
        self.assertEqual(detect_format("a.cfg"), "ini")

    def test_detects_env_files(self):
        for name in (".env", "prod.env", ".env.local", "/srv/app/.env.production"):
            self.assertEqual(detect_format(name), "env", name)

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
