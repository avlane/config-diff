"""Semantic comparison of two parsed configurations."""
from __future__ import annotations

from dataclasses import dataclass

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"


@dataclass(frozen=True)
class Change:
    kind: str
    path: tuple
    old: object = None
    new: object = None


def diff(old, new):
    """Return the list of Changes that turn *old* into *new*."""
    changes = []
    _diff((), old, new, changes)
    return changes


def _diff(path, a, b, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in a:
            if key not in b:
                out.append(Change(REMOVED, path + (key,), old=a[key]))
            else:
                _diff(path + (key,), a[key], b[key], out)
        for key in b:
            if key not in a:
                out.append(Change(ADDED, path + (key,), new=b[key]))
    elif a != b:
        out.append(Change(CHANGED, path, a, b))
