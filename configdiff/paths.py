"""Human-readable names for locations inside a configuration."""
from __future__ import annotations


def format_path(path):
    """Render a path tuple as "server.ports[1].name"; the root is "$"."""
    out = ""
    for segment in path:
        if isinstance(segment, int):
            out += "[%d]" % segment
        else:
            out += ("." if out else "") + str(segment)
    return out or "$"
