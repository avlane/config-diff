import unittest

from configdiff.diffing import ADDED, CHANGED, REMOVED, Change
import json

from configdiff.render import format_value, render_json, render_plain


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


class RenderColorTests(unittest.TestCase):
    CHANGES = [Change(ADDED, ("a",), new=1), Change(REMOVED, ("b",), old=2),
               Change(CHANGED, ("c",), 3, 4)]

    def test_color_off_is_identical_to_plain(self):
        self.assertEqual(render_plain(self.CHANGES, color=False), render_plain(self.CHANGES))
        self.assertNotIn("\x1b", render_plain(self.CHANGES))

    def test_color_on_wraps_lines_in_escape_codes(self):
        lines = render_plain(self.CHANGES, color=True).splitlines()
        self.assertEqual(lines[0], "\x1b[32m+ a: 1\x1b[0m")
        self.assertEqual(lines[1], "\x1b[31m- b: 2\x1b[0m")
        self.assertIn("\x1b[31m3\x1b[0m -> \x1b[32m4\x1b[0m", lines[2])

    def test_stripping_the_codes_gives_plain_text(self):
        import re
        colored = render_plain(self.CHANGES, color=True)
        self.assertEqual(re.sub(r"\x1b\[\d+m", "", colored), render_plain(self.CHANGES))


class RenderJsonTests(unittest.TestCase):
    def test_document(self):
        changes = [Change(ADDED, ("a", 0), new=1), Change(REMOVED, ("b",), old=None),
                   Change(CHANGED, ("c",), 1, 2)]
        doc = json.loads(render_json(changes))
        self.assertFalse(doc["equal"])
        self.assertEqual(doc["summary"], {"added": 1, "removed": 1, "changed": 1})
        self.assertEqual(doc["changes"][0], {"kind": "added", "path": "a[0]",
                                             "segments": ["a", 0], "new": 1})
        self.assertEqual(doc["changes"][1], {"kind": "removed", "path": "b",
                                             "segments": ["b"], "old": None})
        self.assertEqual(doc["changes"][2]["old"], 1)
        self.assertEqual(doc["changes"][2]["new"], 2)

    def test_equal(self):
        doc = json.loads(render_json([]))
        self.assertEqual(doc, {"equal": True, "summary": {"added": 0, "removed": 0, "changed": 0},
                               "changes": []})

    def test_dates_are_serialisable(self):
        import datetime
        out = render_json([Change(ADDED, ("d",), new=datetime.date(2023, 11, 18))])
        self.assertEqual(json.loads(out)["changes"][0]["new"], "2023-11-18")


if __name__ == "__main__":
    unittest.main()
