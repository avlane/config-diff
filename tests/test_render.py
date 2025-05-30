import unittest

from configdiff.diffing import ADDED, CHANGED, REMOVED, Change
import json

from configdiff.render import (format_value, render_json, render_markdown, render_plain,
                               summary_line)


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


class SummaryLineTests(unittest.TestCase):
    def test_no_changes(self):
        self.assertEqual(summary_line([]), "No differences.")

    def test_singular_and_plural(self):
        self.assertEqual(summary_line([Change(ADDED, ("a",), new=1)]), "1 difference (1 added)")
        changes = [Change(ADDED, ("a",), new=1), Change(CHANGED, ("b",), 1, 2),
                   Change(CHANGED, ("c",), 1, 2)]
        self.assertEqual(summary_line(changes), "3 differences (1 added, 2 changed)")


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


class RenderMarkdownTests(unittest.TestCase):
    def test_table(self):
        changes = [Change(CHANGED, ("server", "port"), 8080, 8443),
                   Change(ADDED, ("tags", 0), new="x"), Change(REMOVED, ("old",), old=True)]
        self.assertEqual(render_markdown(changes).splitlines(), [
            "**3 differences** (1 added, 1 removed, 1 changed)",
            "",
            "| Change | Path | Old | New |",
            "| --- | --- | --- | --- |",
            "| changed | `server.port` | `8080` | `8443` |",
            "| added | `tags[0]` |  | `\"x\"` |",
            "| removed | `old` | `true` |  |",
        ])

    def test_no_changes(self):
        self.assertEqual(render_markdown([]), "No differences.\n")

    def test_pipes_backticks_and_newlines_cannot_break_the_table(self):
        change = Change(CHANGED, ("k",), "a|b", "x`y\nz")
        row = render_markdown([change]).splitlines()[-1]
        self.assertEqual(row, "| changed | `k` | `\"a\\|b\"` | ``\"x`y\\nz\"`` |")
        self.assertEqual(len(row.replace("\\|", "").split("|")), 6)

    def test_code_span_padding_for_edge_backticks(self):
        from configdiff.render import _md_code
        self.assertEqual(_md_code("a"), "`a`")
        self.assertEqual(_md_code("`x"), "`` `x ``")
        self.assertEqual(_md_code("x`"), "`` x` ``")
        self.assertEqual(_md_code("a``b"), "``` a``b ```"[:0] or "```a``b```")


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
