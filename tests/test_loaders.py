import importlib.util
import unittest

from configdiff.loaders import (ConfigError, LoadOptions, coerce_scalar, coerce_scalars, detect_format,
                                load_env, load_file, load_ini, load_json, load_text, load_toml,
                                load_yaml, lowercase_keys)
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

    def test_default_section_is_not_copied_into_every_section(self):
        text = "[DEFAULT]\nretries = 3\ntimeout = 10\n\n[a]\nx = 1\ntimeout = 30\n\n[b]\ny = 2\n"
        self.assertEqual(load_ini(text), {
            "DEFAULT": {"retries": "3", "timeout": "10"},
            "a": {"x": "1", "timeout": "30"},
            "b": {"y": "2"},
        })

    def test_no_default_section_means_no_key(self):
        self.assertNotIn("DEFAULT", load_ini("[a]\nx = 1\n"))

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


class YamlLoaderTests(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(load_yaml("a:\n  b: 1\n"), {"a": {"b": 1}})

    def test_unsupported_features_become_config_errors(self):
        with self.assertRaises(ConfigError) as ctx:
            load_yaml("a: &x 1\n")
        self.assertIn("unsupported YAML: line 1", str(ctx.exception))

    def test_detects_yaml(self):
        self.assertEqual(detect_format("a.yaml"), "yaml")
        self.assertEqual(detect_format("a.yml"), "yaml")


class DuplicateKeyTests(unittest.TestCase):
    CASES = {
        "json": '{"a": 1, "b": {"c": 1, "c": 2}}',
        "env": "A=1\nB=2\nA=3\n",
        "ini": "[s]\nk = 1\nk = 2\n",
        "yaml": "a: 1\nb:\n  c: 1\n  c: 2\n",
    }

    def test_duplicates_are_errors_by_default(self):
        for fmt, text in self.CASES.items():
            with self.assertRaises(ConfigError, msg=fmt) as ctx:
                load_text(text, fmt)
            self.assertTrue(any(w in str(ctx.exception) for w in ("duplicate", "twice", "already exists")),
                            (fmt, str(ctx.exception)))

    def test_last_one_wins_when_allowed(self):
        self.assertEqual(load_text(self.CASES["json"], "json", options=LoadOptions(allow_duplicates=True))["b"], {"c": 2})
        self.assertEqual(load_text(self.CASES["env"], "env", options=LoadOptions(allow_duplicates=True))["A"], "3")
        self.assertEqual(load_text(self.CASES["ini"], "ini", options=LoadOptions(allow_duplicates=True)), {"s": {"k": "2"}})
        self.assertEqual(load_text(self.CASES["yaml"], "yaml", options=LoadOptions(allow_duplicates=True))["b"], {"c": 2})

    def test_distinct_keys_in_different_objects_are_fine(self):
        load_text('{"a": {"x": 1}, "b": {"x": 2}, "l": [{"x": 1}, {"x": 2}]}', "json")

    def test_env_message_names_the_line(self):
        with self.assertRaises(ConfigError) as ctx:
            load_env("A=1\nB=2\nA=3\n")
        self.assertIn("line 3", str(ctx.exception))


class LowercaseKeysTests(unittest.TestCase):
    def test_nested_keys_are_lowered_values_are_not(self):
        data = {"Server": {"HOST": "Example.COM", "Ports": [{"HTTP": 80}]}}
        self.assertEqual(lowercase_keys(data),
                         {"server": {"host": "Example.COM", "ports": [{"http": 80}]}})

    def test_collisions_are_errors(self):
        with self.assertRaises(ConfigError) as ctx:
            lowercase_keys({"Port": 1, "PORT": 2})
        self.assertIn("differ only by case", str(ctx.exception))

    def test_via_load_text(self):
        options = LoadOptions(lowercase_keys=True)
        self.assertEqual(load_text("DB_HOST=x\n", "env", options=options), {"db_host": "x"})
        with self.assertRaises(ConfigError) as ctx:
            load_text("A=1\na=2\n", "env", "f.env", options)
        self.assertIn("f.env", str(ctx.exception))


class CoerceTests(unittest.TestCase):
    def test_scalars(self):
        cases = {"true": True, "False": False, "null": None, "42": 42, "-7": -7, "0": 0,
                 "3.14": 3.14, "-0.5": -0.5}
        for text, expected in cases.items():
            self.assertEqual(coerce_scalar(text), expected, text)
            self.assertIs(type(coerce_scalar(text)), type(expected), text)

    def test_conservative(self):
        for text in ("0755", "007", "1e3", "yes", "on", "1.", ".5", "+1", "1_000", "0x10", "",
                     " 1", "True1", "nUll", "http://x"):
            self.assertEqual(coerce_scalar(text), text, text)

    def test_non_strings_pass_through(self):
        self.assertEqual(coerce_scalar(None), None)
        self.assertEqual(coerce_scalar(5), 5)

    def test_nested(self):
        self.assertEqual(coerce_scalars({"a": {"b": "1", "c": ["true", "x"]}}),
                         {"a": {"b": 1, "c": [True, "x"]}})

    def test_only_applies_to_string_only_formats(self):
        self.assertEqual(load_text("PORT=8080\n", "env", options=LoadOptions(coerce=True)), {"PORT": 8080})
        self.assertEqual(load_text("[a]\nx = false\n", "ini", options=LoadOptions(coerce=True)), {"a": {"x": False}})
        self.assertEqual(load_text('{"a": "1"}', "json", options=LoadOptions(coerce=True)), {"a": "1"})
        self.assertEqual(load_text("a: '1'\n", "yaml", options=LoadOptions(coerce=True)), {"a": "1"})
        self.assertEqual(load_text("PORT=8080\n", "env"), {"PORT": "8080"})


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

    def test_byte_order_mark_is_ignored_for_every_format(self):
        samples = {
            "a.json": ('{"k": 1}', {"k": 1}),
            "a.env": ("FIRST=1\nSECOND=2\n", {"FIRST": "1", "SECOND": "2"}),
            "a.ini": ("[s]\nk = v\n", {"s": {"k": "v"}}),
            "a.yaml": ("k: 1\n", {"k": 1}),
            "a.toml": ('k = 1\n', {"k": 1}),
        }
        for name, (text, expected) in samples.items():
            if name.endswith(".toml") and not HAS_TOMLLIB:
                continue
            path = self.write(name, "\ufeff" + text)
            self.assertEqual(load_file(path), expected, name)

    def test_byte_order_mark_on_standard_input_text(self):
        self.assertEqual(load_text("\ufeffFIRST=1\n", "env"), {"FIRST": "1"})

    def test_invalid_utf8(self):
        path = self.write("latin.json", '{"a": "caf\xe9"}', encoding="latin-1")
        with self.assertRaises(ConfigError) as ctx:
            load_file(path)
        self.assertIn("UTF-8", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
