"""Semantic comparison of two parsed configurations."""
from __future__ import annotations

from dataclasses import dataclass, field

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"


@dataclass(frozen=True)
class Change:
    kind: str
    path: tuple
    old: object = None
    new: object = None


def _equal(a, b):
    """Equality for scalars that does not let Python's quirks hide changes.

    In Python True == 1 and False == 0, so a flag that turned into a number
    would compare equal. Booleans only equal booleans. 1 and 1.0 are the same
    number, but "1" and 1 are different values.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    return a == b


@dataclass
class Options:
    """Knobs for diff(); every field is optional."""
    ignore: list = field(default_factory=list)    # Patterns whose paths are skipped

    def is_ignored(self, path):
        return any(p.matches(path) for p in self.ignore)


_NO_OPTIONS = Options()


def _prune(options, path, value):
    """Drop ignored paths from a value that is reported whole (added/removed)."""
    if not options.ignore:
        return value
    if isinstance(value, dict):
        return {k: _prune(options, path + (k,), v) for k, v in value.items()
                if not options.is_ignored(path + (k,))}
    if isinstance(value, list):
        return [_prune(options, path + (i,), v) for i, v in enumerate(value)
                if not options.is_ignored(path + (i,))]
    return value


def diff(old, new, options=None):
    """Return the list of Changes that turn *old* into *new*."""
    changes = []
    _diff(options or _NO_OPTIONS, (), old, new, changes)
    return changes


def _diff(options, path, a, b, out):
    if path and options.is_ignored(path):
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in a:
            if key not in b:
                _removed(options, path + (key,), a[key], out)
            else:
                _diff(options, path + (key,), a[key], b[key], out)
        for key in b:
            if key not in a:
                _added(options, path + (key,), b[key], out)
    elif isinstance(a, list) and isinstance(b, list):
        for index in range(max(len(a), len(b))):
            if index >= len(b):
                _removed(options, path + (index,), a[index], out)
            elif index >= len(a):
                _added(options, path + (index,), b[index], out)
            else:
                _diff(options, path + (index,), a[index], b[index], out)
    elif not _equal(a, b):
        out.append(Change(CHANGED, path, _prune(options, path, a), _prune(options, path, b)))


def _removed(options, path, value, out):
    if not options.is_ignored(path):
        out.append(Change(REMOVED, path, old=_prune(options, path, value)))


def _added(options, path, value, out):
    if not options.is_ignored(path):
        out.append(Change(ADDED, path, new=_prune(options, path, value)))
