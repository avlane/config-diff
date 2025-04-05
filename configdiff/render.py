"""Turn a list of Changes into text."""
from __future__ import annotations

import json

from .diffing import ADDED, CHANGED, REMOVED
from .paths import Item, Member, format_path


def format_value(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def summarize(changes):
    counts = {ADDED: 0, REMOVED: 0, CHANGED: 0}
    for change in changes:
        counts[change.kind] += 1
    return counts


def summary_line(changes):
    """"3 differences (1 added, 2 changed)" or "No differences."."""
    if not changes:
        return "No differences."
    counts = summarize(changes)
    parts = ["%d %s" % (n, kind) for kind, n in counts.items() if n]
    return "%d difference%s (%s)" % (len(changes), "" if len(changes) == 1 else "s",
                                     ", ".join(parts))


def _segment_json(segment):
    if isinstance(segment, Item):
        return {"item": {segment.field: segment.value}}
    if isinstance(segment, Member):
        return {"member": segment.value}
    return segment  # strings for keys, integers for list positions


def change_to_dict(change):
    entry = {
        "kind": change.kind,
        "path": format_path(change.path),
        "segments": [_segment_json(s) for s in change.path],
    }
    if change.kind != ADDED:
        entry["old"] = change.old
    if change.kind != REMOVED:
        entry["new"] = change.new
    return entry


def render_json(changes):
    document = {
        "equal": not changes,
        "summary": summarize(changes),
        "changes": [change_to_dict(c) for c in changes],
    }
    return json.dumps(document, indent=2, ensure_ascii=False, default=_json_default) + "\n"


def _status_counts(results):
    counts = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def directory_summary_line(results):
    counts = _status_counts(results)
    differing = counts.get("different", 0) + counts.get("only-old", 0) + counts.get("only-new", 0)
    if not differing:
        return "No differences in %d file%s." % (len(results), "" if len(results) == 1 else "s")
    parts = ["%d %s" % (counts[s], label) for s, label in
             (("different", "changed"), ("only-old", "only in old"), ("only-new", "only in new"))
             if counts.get(s)]
    return "%d of %d files differ (%s)" % (differing, len(results), ", ".join(parts))


def render_directory_json(results):
    document = {
        "equal": all(r.status == "same" for r in results),
        "summary": _status_counts(results),
        "files": [{
            "name": r.name,
            "status": r.status,
            "summary": summarize(r.changes),
            "changes": [change_to_dict(c) for c in r.changes],
        } for r in results],
    }
    return json.dumps(document, indent=2, ensure_ascii=False, default=_json_default) + "\n"


_RESET = "\x1b[0m"
_COLORS = {"green": "\x1b[32m", "red": "\x1b[31m", "yellow": "\x1b[33m", "bold": "\x1b[1m"}


def _paint(text, color, enabled):
    return "%s%s%s" % (_COLORS[color], text, _RESET) if enabled else text


def render_plain(changes, color=False):
    """One line per change: "+ added", "- removed", "~ old -> new"."""
    lines = []
    for change in changes:
        path = format_path(change.path)
        if change.kind == ADDED:
            lines.append(_paint("+ %s: %s" % (path, format_value(change.new)), "green", color))
        elif change.kind == REMOVED:
            lines.append(_paint("- %s: %s" % (path, format_value(change.old)), "red", color))
        else:
            lines.append("%s %s: %s -> %s" % (
                _paint("~", "yellow", color), _paint(path, "bold", color),
                _paint(format_value(change.old), "red", color),
                _paint(format_value(change.new), "green", color)))
    return "".join(line + "\n" for line in lines)

def render_directory_plain(results, color=False):
    """Per file: a "=== name ===" header and its changes, or an "Only in" line."""
    out = []
    for result in results:
        if result.status == "same":
            continue
        if result.status == "only-old":
            out.append(_paint("- only in old: %s" % result.name, "red", color) + "\n")
        elif result.status == "only-new":
            out.append(_paint("+ only in new: %s" % result.name, "green", color) + "\n")
        else:
            out.append(_paint("=== %s ===" % result.name, "bold", color) + "\n")
            out.append(render_plain(result.changes, color))
    return "".join(out)
