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


if __name__ == "__main__":
    unittest.main()
