"""Turn a list of Changes into text."""
from __future__ import annotations

import json

from .diffing import ADDED, REMOVED
from .paths import format_path


def format_value(value):
    return json.dumps(value, ensure_ascii=False, default=str)


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
