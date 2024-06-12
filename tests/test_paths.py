import unittest

from configdiff.paths import Item, PatternError, format_path, parse_pattern


class FormatPathTests(unittest.TestCase):
    def test_root(self):
        self.assertEqual(format_path(()), "$")

    def test_keys_and_indexes(self):
        self.assertEqual(format_path(("server", "ports", 1, "name")), "server.ports[1].name")

    def test_leading_index(self):
        self.assertEqual(format_path((0, "a")), "[0].a")

    def test_keys_with_dots_are_quoted(self):
        self.assertEqual(format_path(("logging", "app.module", "level")),
                         'logging["app.module"].level')
        self.assertEqual(format_path(("a.b",)), '["a.b"]')
        self.assertNotEqual(format_path(("a.b",)), format_path(("a", "b")))

    def test_other_awkward_keys(self):
        self.assertEqual(format_path(("x", "has space", "[0]", "*", "")),
                         'x["has space"]["[0]"]["*"][""]')
        self.assertEqual(format_path(("caf\u00e9",)), '["caf\u00e9"]')
        self.assertEqual(format_path(('say "hi"',)), '["say \\"hi\\""]')

    def test_digits_and_dashes_stay_plain(self):
        self.assertEqual(format_path(("ports", "8080", "my-key_1")), "ports.8080.my-key_1")

    def test_item_values(self):
        self.assertEqual(format_path(("s", Item("name", "web-1"), "p")), "s[name=web-1].p")
        self.assertEqual(format_path(("s", Item("name", "web 1"))), 's[name="web 1"]')
        self.assertEqual(format_path(("s", Item("id", 7))), "s[id=7]")

    def test_formatted_paths_parse_back_to_themselves(self):
        paths = [("a.b", "c"), ("x", 3, "has space"), ("s", Item("name", "web 1"), "port"),
                 ("t", "]"), ("q", '"')]
        for path in paths:
            self.assertTrue(parse_pattern(format_path(path)).matches(path), path)


def m(pattern, path, **kw):
    return parse_pattern(pattern, **kw).matches(tuple(path))


class PatternTests(unittest.TestCase):
    def test_literal_paths(self):
        self.assertTrue(m("a.b", ["a", "b"]))
        self.assertFalse(m("a.b", ["a"]))
        self.assertFalse(m("a.b", ["a", "b", "c"]))
        self.assertFalse(m("a.b", ["x", "b"]))

    def test_single_star_matches_one_segment_of_any_kind(self):
        self.assertTrue(m("a.*.c", ["a", "x", "c"]))
        self.assertTrue(m("a.*.c", ["a", 3, "c"]))
        self.assertFalse(m("a.*.c", ["a", "c"]))
        self.assertFalse(m("a.*.c", ["a", "x", "y", "c"]))

    def test_double_star_matches_any_depth_including_none(self):
        self.assertTrue(m("**.password", ["password"]))
        self.assertTrue(m("**.password", ["db", "password"]))
        self.assertTrue(m("**.password", ["db", "pool", 0, "password"]))
        self.assertFalse(m("**.password", ["db", "password", "x"]))
        self.assertTrue(m("a.**", ["a"]))
        self.assertTrue(m("a.**", ["a", "b", "c"]))
        self.assertTrue(m("**", []))

    def test_wildcards_inside_names(self):
        self.assertTrue(m("db.pass*", ["db", "password"]))
        self.assertTrue(m("db.p?ss", ["db", "pass"]))
        self.assertFalse(m("db.pass*", ["db", "my_password"]))
        self.assertTrue(m("**.*token*", ["a", "access_token_id"]))

    def test_wildcard_names_only_match_keys(self):
        self.assertFalse(m("a.p*", ["a", 0]))

    def test_regex_metacharacters_are_literal(self):
        self.assertTrue(m("a+b.(c)", ["a+b", "(c)"]))
        self.assertFalse(m("a+b", ["aab"]))

    def test_indexes(self):
        self.assertTrue(m("users[0].name", ["users", 0, "name"]))
        self.assertFalse(m("users[0].name", ["users", 1, "name"]))
        self.assertTrue(m("users[*].name", ["users", 7, "name"]))
        self.assertFalse(m("users[*].name", ["users", "x", "name"]))

    def test_quoted_keys(self):
        self.assertTrue(m('["a.b"].c', ["a.b", "c"]))
        self.assertFalse(m('["a.b"].c', ["a", "b", "c"]))
        self.assertTrue(m('x["we*ird"]', ["x", "we*ird"]))
        self.assertFalse(m('x["we*ird"]', ["x", "weird"]))

    def test_ignore_case(self):
        self.assertTrue(m("**.*password*", ["DB", "MyPassword"], ignore_case=True))
        self.assertFalse(m("**.*password*", ["DB", "MyPassword"]))

    def test_item_patterns(self):
        self.assertTrue(m("s[name=web-1].p", ["s", Item("name", "web-1"), "p"]))
        self.assertTrue(m('s[name="web 1"]', ["s", Item("name", "web 1")]))
        self.assertTrue(m("s[id=7]", ["s", Item("id", 7)]))
        self.assertFalse(m("s[id=7]", ["s", Item("id", 8)]))
        self.assertTrue(m("s[*]", ["s", Item("id", 8)]))

    def test_errors(self):
        for bad in ("", "...", "a[", "a[x]", 'a["b', "a[1"):
            with self.assertRaises(PatternError, msg=bad):
                parse_pattern(bad)


if __name__ == "__main__":
    unittest.main()
