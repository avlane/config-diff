import unittest

from configdiff.diffing import ADDED, CHANGED, REMOVED, Change
from configdiff.render import format_value, render_plain


class RenderPlainTests(unittest.TestCase):
    def test_one_line_per_change(self):
        changes = [
            Change(ADDED, ("a", "new"), new=[1, 2]),
            Change(REMOVED, ("gone",), old="x"),
            Change(CHANGED, ("n", 0), 1, "1"),
        ]
        self.assertEqual(render_plain(changes),
                         '+ a.new: [1, 2]\n- gone: "x"\n~ n[0]: 1 -> "1"\n')

    def test_no_changes_is_empty(self):
        self.assertEqual(render_plain([]), "")

    def test_values_keep_unicode(self):
        self.assertEqual(format_value("café"), '"café"')

    def test_none_and_bools(self):
        self.assertEqual(format_value(None), "null")
        self.assertEqual(format_value(True), "true")


if __name__ == "__main__":
    unittest.main()
