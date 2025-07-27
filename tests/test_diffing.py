import unittest

from configdiff.diffing import ADDED, CHANGED, REMOVED, Change, Options, diff
from configdiff.paths import Item, Member, parse_pattern


class DictDiffTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(diff({"a": 1, "b": {"c": [1, 2]}}, {"b": {"c": [1, 2]}, "a": 1}), [])

    def test_key_order_does_not_matter(self):
        self.assertEqual(diff({"a": 1, "b": 2}, {"b": 2, "a": 1}), [])

    def test_added_removed_changed(self):
        changes = diff({"keep": 1, "gone": 2, "edit": 3}, {"keep": 1, "edit": 4, "new": 5})
        self.assertEqual(changes, [
            Change(REMOVED, ("gone",), old=2),
            Change(CHANGED, ("edit",), 3, 4),
            Change(ADDED, ("new",), new=5),
        ])

    def test_nested_paths(self):
        old = {"db": {"pool": {"max": 10}, "host": "a"}}
        new = {"db": {"pool": {"max": 20}, "host": "a"}}
        self.assertEqual(diff(old, new), [Change(CHANGED, ("db", "pool", "max"), 10, 20)])

    def test_added_subtree_is_reported_once(self):
        changes = diff({}, {"tls": {"enabled": True, "cert": "x.pem"}})
        self.assertEqual(changes, [Change(ADDED, ("tls",), new={"enabled": True, "cert": "x.pem"})])

    def test_dict_replaced_by_scalar(self):
        self.assertEqual(diff({"a": {"b": 1}}, {"a": 5}),
                         [Change(CHANGED, ("a",), {"b": 1}, 5)])

    def test_root_scalars(self):
        self.assertEqual(diff(1, 2), [Change(CHANGED, (), 1, 2)])


class ScalarEqualityTests(unittest.TestCase):
    def test_bool_is_not_a_number(self):
        for old, new in ((True, 1), (False, 0), (1, True), (0, False), (True, 1.0)):
            self.assertEqual(diff({"a": old}, {"a": new}),
                             [Change(CHANGED, ("a",), old, new)], (old, new))

    def test_same_bools_are_equal(self):
        self.assertEqual(diff({"a": True}, {"a": True}), [])

    def test_string_and_number_differ(self):
        self.assertEqual(len(diff({"a": "1"}, {"a": 1})), 1)
        self.assertEqual(len(diff({"a": "true"}, {"a": True})), 1)

    def test_int_and_float_with_equal_value_are_equal(self):
        self.assertEqual(diff({"a": 1}, {"a": 1.0}), [])
        self.assertEqual(len(diff({"a": 1}, {"a": 1.5})), 1)

    def test_none_differs_from_empty_values(self):
        for other in ("", 0, False, [], {}):
            self.assertEqual(len(diff({"a": None}, {"a": other})), 1, other)

    def test_bool_inside_lists(self):
        self.assertEqual(len(diff({"a": [True]}, {"a": [1]})), 1)


def ignoring(*patterns):
    return Options(ignore=[parse_pattern(p) for p in patterns])


class IgnoreTests(unittest.TestCase):
    def test_ignored_change_is_not_reported(self):
        old = {"a": 1, "b": 1}
        new = {"a": 2, "b": 2}
        self.assertEqual(diff(old, new, ignoring("a")), [Change(CHANGED, ("b",), 1, 2)])

    def test_ignored_added_and_removed_keys(self):
        self.assertEqual(diff({"x": 1}, {"y": 1}, ignoring("x", "y")), [])

    def test_ignoring_a_section_ignores_everything_below(self):
        old = {"cache": {"ttl": 1, "size": 2}, "k": 1}
        new = {"cache": {"ttl": 9, "size": 9}, "k": 1}
        self.assertEqual(diff(old, new, ignoring("cache")), [])

    def test_deep_wildcard(self):
        old = {"db": {"password": "a", "host": "h"}, "api": {"deep": {"password": "x"}}}
        new = {"db": {"password": "b", "host": "h2"}, "api": {"deep": {"password": "y"}}}
        self.assertEqual(diff(old, new, ignoring("**.password")),
                         [Change(CHANGED, ("db", "host"), "h", "h2")])

    def test_list_positions(self):
        old = {"u": [{"id": 1, "seen": "a"}, {"id": 2, "seen": "b"}]}
        new = {"u": [{"id": 1, "seen": "c"}, {"id": 2, "seen": "d"}]}
        self.assertEqual(diff(old, new, ignoring("u[*].seen")), [])
        self.assertEqual(len(diff(old, new, ignoring("u[0].seen"))), 1)

    def test_ignored_parts_of_added_values_are_not_leaked(self):
        old = {}
        new = {"db": {"host": "h", "password": "hunter2"}, "list": [{"token": "t", "n": 1}]}
        changes = diff(old, new, ignoring("**.password", "**.token"))
        self.assertEqual(changes, [
            Change(ADDED, ("db",), new={"host": "h"}),
            Change(ADDED, ("list",), new=[{"n": 1}]),
        ])

    def test_ignored_parts_of_replaced_values_are_not_leaked(self):
        changes = diff({"a": {"password": "x", "n": 1}}, {"a": "gone"}, ignoring("**.password"))
        self.assertEqual(changes, [Change(CHANGED, ("a",), {"n": 1}, "gone")])


def keyed(spec, name):
    return Options(list_keys=[(parse_pattern(spec), name)])


class KeyedListTests(unittest.TestCase):
    OLD = {"s": [{"n": "a", "p": 1}, {"n": "b", "p": 2}, {"n": "c", "p": 3}]}

    def test_reordering_is_not_a_change(self):
        new = {"s": [{"n": "c", "p": 3}, {"n": "a", "p": 1}, {"n": "b", "p": 2}]}
        self.assertEqual(diff(self.OLD, new, keyed("s", "n")), [])
        self.assertEqual(len(diff(self.OLD, new)), 6)  # by position it is noisy

    def test_added_removed_and_changed_items(self):
        new = {"s": [{"n": "b", "p": 20}, {"n": "d", "p": 4}, {"n": "a", "p": 1}]}
        changes = diff(self.OLD, new, keyed("s", "n"))
        self.assertEqual(changes, [
            Change(CHANGED, ("s", Item("n", "b"), "p"), 2, 20),
            Change(REMOVED, ("s", Item("n", "c")), old={"n": "c", "p": 3}),
            Change(ADDED, ("s", Item("n", "d")), new={"n": "d", "p": 4}),
        ])

    def test_path_rendering(self):
        from configdiff.paths import format_path
        self.assertEqual(format_path(("s", Item("n", "b"), "p")), "s[n=b].p")

    def test_integer_keys(self):
        old = {"u": [{"id": 1, "v": "x"}, {"id": 2, "v": "y"}]}
        new = {"u": [{"id": 2, "v": "y"}, {"id": 1, "v": "z"}]}
        self.assertEqual(diff(old, new, keyed("u", "id")),
                         [Change(CHANGED, ("u", Item("id", 1), "v"), "x", "z")])

    def test_wildcard_in_the_list_path(self):
        old = {"g": {"x": [{"n": 1, "v": 1}], "y": [{"n": 1, "v": 1}, {"n": 2, "v": 2}]}}
        new = {"g": {"x": [{"n": 1, "v": 1}], "y": [{"n": 2, "v": 2}, {"n": 1, "v": 1}]}}
        self.assertEqual(diff(old, new, keyed("g.*", "n")), [])

    def test_falls_back_to_positions_when_keys_are_missing_or_duplicated(self):
        for bad in ([{"n": "a"}, {"p": 1}], [{"n": "a"}, {"n": "a"}], [1, 2], [{"n": ["x"]}]):
            old, new = {"s": bad}, {"s": list(reversed(bad))}
            result = diff(old, new, keyed("s", "n"))
            self.assertEqual(result, diff(old, new), bad)

    def test_ignore_applies_inside_keyed_items(self):
        old = {"s": [{"n": "a", "seen": 1}]}
        new = {"s": [{"n": "a", "seen": 2}]}
        opts = Options(ignore=[parse_pattern("s[*].seen")], list_keys=[(parse_pattern("s"), "n")])
        self.assertEqual(diff(old, new, opts), [])

    def test_item_pattern(self):
        old = {"s": [{"n": "a", "p": 1}, {"n": "b", "p": 1}]}
        new = {"s": [{"n": "b", "p": 2}, {"n": "a", "p": 2}]}
        opts = Options(ignore=[parse_pattern("s[n=a].p")], list_keys=[(parse_pattern("s"), "n")])
        self.assertEqual(diff(old, new, opts), [Change(CHANGED, ("s", Item("n", "b"), "p"), 1, 2)])


def unordered(*specs):
    return Options(unordered=[parse_pattern(s) for s in specs])


class UnorderedListTests(unittest.TestCase):
    def test_reordering_is_not_a_change(self):
        self.assertEqual(diff({"t": ["a", "b", "c"]}, {"t": ["c", "a", "b"]}, unordered("t")), [])

    def test_added_and_removed_elements(self):
        changes = diff({"t": ["a", "b"]}, {"t": ["b", "c"]}, unordered("t"))
        self.assertEqual(changes, [
            Change(REMOVED, ("t", Member("a")), old="a"),
            Change(ADDED, ("t", Member("c")), new="c"),
        ])

    def test_duplicates_are_counted(self):
        changes = diff({"t": [1, 1, 2]}, {"t": [1, 2]}, unordered("t"))
        self.assertEqual(changes, [Change(REMOVED, ("t", Member(1)), old=1)])

    def test_elements_may_be_mappings(self):
        old = {"t": [{"a": 1}, {"b": 2}]}
        new = {"t": [{"b": 2}, {"a": 1}, {"c": 3}]}
        self.assertEqual(diff(old, new, unordered("t")),
                         [Change(ADDED, ("t", Member({"c": 3})), new={"c": 3})])

    def test_types_still_matter(self):
        self.assertEqual(len(diff({"t": [True]}, {"t": [1]}, unordered("t"))), 2)
        self.assertEqual(len(diff({"t": ["1"]}, {"t": [1]}, unordered("t"))), 2)
        self.assertEqual(diff({"t": [1]}, {"t": [1.0]}, unordered("t")), [])

    def test_only_the_selected_lists_are_unordered(self):
        old = {"a": [1, 2], "b": [1, 2]}
        new = {"a": [2, 1], "b": [2, 1]}
        self.assertEqual(len(diff(old, new, unordered("a"))), 2)  # b still differs

    def test_member_rendering(self):
        from configdiff.paths import format_path
        self.assertEqual(format_path(("t", Member("beta"))), 't[="beta"]')
        self.assertEqual(format_path(("t", Member(3))), "t[=3]")

    def test_list_key_wins_over_unordered(self):
        opts = Options(list_keys=[(parse_pattern("s"), "n")], unordered=[parse_pattern("s")])
        old = {"s": [{"n": "a", "p": 1}]}
        new = {"s": [{"n": "a", "p": 2}]}
        self.assertEqual(diff(old, new, opts), [Change(CHANGED, ("s", Item("n", "a"), "p"), 1, 2)])


def only(*patterns, **kw):
    return Options(only=[parse_pattern(p) for p in patterns], **kw)


class OnlyTests(unittest.TestCase):
    OLD = {"server": {"port": 1, "host": "a"}, "db": {"pool": {"max": 1}, "url": "x"}, "n": 1}
    NEW = {"server": {"port": 2, "host": "b"}, "db": {"pool": {"max": 2}, "url": "y"}, "n": 2}

    def test_only_a_subtree(self):
        self.assertEqual(diff(self.OLD, self.NEW, only("server")), [
            Change(CHANGED, ("server", "port"), 1, 2), Change(CHANGED, ("server", "host"), "a", "b")])

    def test_only_a_leaf_deep_inside(self):
        self.assertEqual(diff(self.OLD, self.NEW, only("db.pool.max")),
                         [Change(CHANGED, ("db", "pool", "max"), 1, 2)])

    def test_several_paths(self):
        paths = [c.path for c in diff(self.OLD, self.NEW, only("n", "server.port"))]
        self.assertEqual(paths, [("server", "port"), ("n",)])

    def test_wildcards(self):
        paths = [c.path for c in diff(self.OLD, self.NEW, only("*.port", "**.max"))]
        self.assertEqual(paths, [("server", "port"), ("db", "pool", "max")])

    def test_combined_with_ignore(self):
        opts = only("server", ignore=[parse_pattern("server.host")])
        self.assertEqual(diff(self.OLD, self.NEW, opts), [Change(CHANGED, ("server", "port"), 1, 2)])

    def test_added_and_removed_values_are_cut_down_to_the_scope(self):
        changes = diff({}, {"db": {"host": "h", "password": "p"}, "other": 1}, only("db.host"))
        self.assertEqual(changes, [Change(ADDED, ("db",), new={"host": "h"})])

    def test_paths_outside_the_scope_that_are_added_are_skipped(self):
        self.assertEqual(diff({"a": 1}, {"a": 1, "b": 2}, only("a")), [])

    def test_nothing_in_scope(self):
        self.assertEqual(diff(self.OLD, self.NEW, only("missing.path")), [])

    def test_list_items(self):
        old, new = {"u": [{"id": 1, "v": 1}, {"id": 2, "v": 1}]}, {"u": [{"id": 1, "v": 2}, {"id": 2, "v": 2}]}
        self.assertEqual(diff(old, new, only("u[1].v")), [Change(CHANGED, ("u", 1, "v"), 1, 2)])


class ListDiffTests(unittest.TestCase):
    def test_lists_are_compared_by_position(self):
        self.assertEqual(diff({"x": [1, 2, 3]}, {"x": [1, 5, 3]}),
                         [Change(CHANGED, ("x", 1), 2, 5)])

    def test_longer_and_shorter_lists(self):
        self.assertEqual(diff({"x": [1]}, {"x": [1, 2]}), [Change(ADDED, ("x", 1), new=2)])
        self.assertEqual(diff({"x": [1, 2]}, {"x": [1]}), [Change(REMOVED, ("x", 1), old=2)])

    def test_nested_inside_list_items(self):
        old = {"s": [{"n": "a", "p": 1}]}
        new = {"s": [{"n": "a", "p": 2}]}
        self.assertEqual(diff(old, new), [Change(CHANGED, ("s", 0, "p"), 1, 2)])

    def test_list_replaced_by_dict(self):
        self.assertEqual(diff({"a": [1]}, {"a": {"b": 1}}),
                         [Change(CHANGED, ("a",), [1], {"b": 1})])


if __name__ == "__main__":
    unittest.main()
