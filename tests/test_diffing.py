import unittest

from configdiff.diffing import ADDED, CHANGED, REMOVED, Change, diff


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
