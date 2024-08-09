import math
import unittest

from configdiff.yamlsubset import YamlSubsetError, loads


class ScalarTests(unittest.TestCase):
    def test_null_bool_numbers(self):
        data = loads("a: null\nb: ~\nc:\nd: true\ne: False\nf: 12\ng: -3\nh: 1.5\ni: 1e3\n"
                     "j: 0x1F\nk: 0o17\nl: .inf\nm: -.inf\n")
        self.assertEqual(data, {"a": None, "b": None, "c": None, "d": True, "e": False,
                                "f": 12, "g": -3, "h": 1.5, "i": 1000.0, "j": 31, "k": 15,
                                "l": math.inf, "m": -math.inf})

    def test_nan(self):
        self.assertTrue(math.isnan(loads("a: .nan")["a"]))

    def test_yaml_1_2_core_schema_has_no_yes_no(self):
        data = loads("a: yes\nb: no\nc: on\nd: off\ne: 2024-04-06\nf: 1_000\ng: 08\n")
        self.assertEqual(data, {"a": "yes", "b": "no", "c": "on", "d": "off",
                                "e": "2024-04-06", "f": "1_000", "g": 8})

    def test_plain_strings(self):
        data = loads("a: hello world\nb: http://example.com:8080/x#frag\nc: it's fine\n"
                     "d: a:b\ne: 12:30:45\n")
        self.assertEqual(data["a"], "hello world")
        self.assertEqual(data["b"], "http://example.com:8080/x#frag")
        self.assertEqual(data["c"], "it's fine")
        self.assertEqual(data["d"], "a:b")
        self.assertEqual(data["e"], "12:30:45")

    def test_quoted_strings_are_never_converted(self):
        data = loads("a: \"123\"\nb: 'true'\nc: \"null\"\nd: ''\n")
        self.assertEqual(data, {"a": "123", "b": "true", "c": "null", "d": ""})

    def test_single_quote_escape(self):
        self.assertEqual(loads("a: 'it''s'\n"), {"a": "it's"})

    def test_double_quote_escapes(self):
        data = loads(r'a: "tab\there\nline \"q\" \\ \x41 \u00e9 \U0001F600 \/"' + "\n")
        self.assertEqual(data["a"], 'tab\there\nline "q" \\ A \u00e9 \U0001F600 /')

    def test_bad_escapes(self):
        for bad in (r'a: "\q"', r'a: "\x4"', r'a: "\u12"'):
            with self.assertRaises(YamlSubsetError, msg=bad):
                loads(bad)

    def test_comments(self):
        text = "# top\na: 1  # trailing\nb: 'x # not a comment'  # but this is\nc: x#y\n\n# end\n"
        self.assertEqual(loads(text), {"a": 1, "b": "x # not a comment", "c": "x#y"})

    def test_apostrophe_in_plain_scalar_does_not_hide_a_comment(self):
        self.assertEqual(loads("a: don't # comment\n"), {"a": "don't"})

    def test_document_that_is_just_a_scalar(self):
        self.assertEqual(loads("42\n"), 42)
        self.assertEqual(loads("hello\n"), "hello")
        self.assertEqual(loads('"x: y"\n'), "x: y")

    def test_empty_documents(self):
        self.assertIsNone(loads(""))
        self.assertIsNone(loads("# only a comment\n\n"))


class MappingTests(unittest.TestCase):
    def test_nested(self):
        text = "server:\n  host: h\n  ports:\n    http: 80\n    https: 443\nname: n\n"
        self.assertEqual(loads(text), {"server": {"host": "h", "ports": {"http": 80, "https": 443}},
                                       "name": "n"})

    def test_quoted_keys(self):
        self.assertEqual(loads('"a: b": 1\n\'c d\': 2\n'), {"a: b": 1, "c d": 2})

    def test_keys_are_strings(self):
        self.assertEqual(loads("1: a\ntrue: b\n"), {"1": "a", "true": "b"})

    def test_empty_value_followed_by_sibling(self):
        self.assertEqual(loads("a:\nb: 1\n"), {"a": None, "b": 1})
        self.assertEqual(loads("a:\n  b:\nc: 1\n"), {"a": {"b": None}, "c": 1})

    def test_blank_lines_and_comments_between_entries(self):
        self.assertEqual(loads("a: 1\n\n  # indented comment\n\nb:\n\n  c: 2\n"),
                         {"a": 1, "b": {"c": 2}})

    def test_crlf_line_endings(self):
        self.assertEqual(loads("a: 1\r\nb:\r\n  c: x\r\n"), {"a": 1, "b": {"c": "x"}})

    def test_utf8_bom(self):
        self.assertEqual(loads("\ufeffa: 1\n"), {"a": 1})

    def test_duplicate_keys_are_an_error(self):
        with self.assertRaises(YamlSubsetError) as ctx:
            loads("a: 1\nb: 2\na: 3\n")
        self.assertEqual(ctx.exception.line, 3)
        self.assertIn("duplicate key 'a'", str(ctx.exception))

    def test_errors_carry_line_numbers(self):
        cases = {
            "a: 1\n\tb: 2\n": 2,                    # tab indentation
            "a: 1\n   b: 2\n": 2,                   # unexpected indentation
            "a: 'x\n": 1,                           # unterminated
            "a: b: c\n": 1,                         # nested mapping on one line
            "a: 1\nnot a mapping\n": 2,
            "a: 'x' y\n": 1,
            "a: &anchor 1\n": 1,
            "a: *alias\n": 1,
            "a: !!str 1\n": 1,
        }
        for text, line in cases.items():
            with self.assertRaises(YamlSubsetError, msg=text) as ctx:
                loads(text)
            self.assertEqual(ctx.exception.line, line, text)


if __name__ == "__main__":
    unittest.main()
