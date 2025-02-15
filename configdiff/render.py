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
