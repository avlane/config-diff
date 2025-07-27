"""Semantic comparison of two parsed configurations."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .paths import Item, Member

_MISSING = object()

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
    ignore: list = field(default_factory=list)      # Patterns whose paths are skipped
    list_keys: list = field(default_factory=list)   # [(Pattern, field)]: match items by field
    unordered: list = field(default_factory=list)   # Patterns of lists whose order is irrelevant
    only: list = field(default_factory=list)        # if set, compare only these paths

    def in_scope(self, path):
        """With "only" patterns: can anything at or below *path* be selected?"""
        if not self.only:
            return True
        return any(p.matches_prefix(path) or any(p.matches(path[:k]) for k in range(len(path) + 1))
                   for p in self.only)

    def inside_only(self, path):
        """Is *path* selected by an "only" pattern, or inside a selected path?"""
        if not self.only:
            return True
        return any(p.matches(path[:k]) for p in self.only for k in range(len(path) + 1))

    def is_unordered(self, path):
        return any(p.matches(path) for p in self.unordered)

    def key_for_list(self, path):
        for pattern, name in self.list_keys:
            if pattern.matches(path):
                return name
        return None

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


_DROP = object()


def _restrict(options, path, value):
    """Keep only the parts of *value* that "only" selects; _DROP if nothing is left."""
    if options.inside_only(path):
        return value
    if isinstance(value, dict):
        kept = {}
        for key, item in value.items():
            part = _restrict(options, path + (key,), item)
            if part is not _DROP:
                kept[key] = part
        return kept if kept else _DROP
    if isinstance(value, list):
        kept = []
        for index, item in enumerate(value):
            part = _restrict(options, path + (index,), item)
            if part is not _DROP:
                kept.append(part)
        return kept if kept else _DROP
    return _DROP


def _scoped(options, path, value):
    """The part of a value reported whole that survives --ignore and --only."""
    value = _prune(options, path, value)
    return _restrict(options, path, value) if options.only else value


def diff(old, new, options=None):
    """Return the list of Changes that turn *old* into *new*."""
    changes = []
    _diff(options or _NO_OPTIONS, (), old, new, changes)
    return changes


def _diff(options, path, a, b, out):
    if path and (options.is_ignored(path) or not options.in_scope(path)):
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
        name = options.key_for_list(path)
        if name is not None and _keyed(a, name) and _keyed(b, name):
            _diff_keyed(options, path, a, b, name, out)
            return
        if options.is_unordered(path):
            _diff_unordered(options, path, a, b, out)
            return
        for index in range(max(len(a), len(b))):
            if index >= len(b):
                _removed(options, path + (index,), a[index], out)
            elif index >= len(a):
                _added(options, path + (index,), b[index], out)
            else:
                _diff(options, path + (index,), a[index], b[index], out)
    elif not _equal(a, b):
        old, new = _scoped(options, path, a), _scoped(options, path, b)
        if old is not _DROP or new is not _DROP:
            out.append(Change(CHANGED, path, None if old is _DROP else old,
                              None if new is _DROP else new))


def _keyed(items, name):
    """True if every item is a mapping with a distinct, hashable *name* field."""
    if not all(isinstance(i, dict) and name in i for i in items):
        return False
    try:
        return len({i[name] for i in items}) == len(items)
    except TypeError:
        return False


def _diff_keyed(options, path, a, b, name, out):
    """Compare lists of mappings by the value of one field instead of by position."""
    for item in a:
        sub = path + (Item(name, item[name]),)
        other = next((o for o in b if o[name] == item[name]), _MISSING)
        if other is _MISSING:
            _removed(options, sub, item, out)
        else:
            _diff(options, sub, item, other, out)
    for item in b:
        if not any(o[name] == item[name] for o in a):
            _added(options, path + (Item(name, item[name]),), item, out)


def _freeze(value):
    """A hashable stand-in for *value* that follows the same equality as _equal."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("num", value)
    if isinstance(value, dict):
        return ("map", frozenset((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, list):
        return ("list", tuple(_freeze(v) for v in value))
    if value is None or isinstance(value, str):
        return (type(value).__name__, value)
    return ("other", repr(value))


def _diff_unordered(options, path, a, b, out):
    """Compare two lists as multisets: only the elements themselves matter."""
    remaining = Counter(_freeze(v) for v in b)
    unmatched = []
    for value in a:
        key = _freeze(value)
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            unmatched.append(value)
    for value in unmatched:
        _removed(options, path + (Member(value),), value, out)
    for value in b:
        key = _freeze(value)
        if remaining[key] > 0:
            remaining[key] -= 1
            _added(options, path + (Member(value),), value, out)


def _removed(options, path, value, out):
    if options.is_ignored(path):
        return
    value = _scoped(options, path, value)
    if value is not _DROP:
        out.append(Change(REMOVED, path, old=value))


def _added(options, path, value, out):
    if options.is_ignored(path):
        return
    value = _scoped(options, path, value)
    if value is not _DROP:
        out.append(Change(ADDED, path, new=value))
