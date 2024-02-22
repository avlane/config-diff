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


def render_plain(changes):
    lines = []
    for change in changes:
        path = format_path(change.path)
        if change.kind == ADDED:
            lines.append("+ %s: %s" % (path, format_value(change.new)))
        elif change.kind == REMOVED:
            lines.append("- %s: %s" % (path, format_value(change.old)))
        else:
            lines.append("~ %s: %s -> %s" % (path, format_value(change.old),
                                             format_value(change.new)))
    return "".join(line + "\n" for line in lines)
