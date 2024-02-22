"""Names for locations inside a configuration, and patterns that select them."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


def format_path(path):
    """Render a path tuple as "server.ports[1].name"; the root is "$"."""
    out = ""
    for segment in path:
        if isinstance(segment, int):
            out += "[%d]" % segment
        elif isinstance(segment, Item):
            out += "[%s=%s]" % (segment.field, segment.value)
        elif isinstance(segment, Member):
            out += "[=%s]" % json.dumps(segment.value, ensure_ascii=False, default=str)
        else:
            out += ("." if out else "") + str(segment)
    return out or "$"


@dataclass(frozen=True)
class Item:
    """A list element identified by one of its fields: users[id=7]."""
    field: str
    value: object


@dataclass(frozen=True)
class Member:
    """An element of an unordered list: tags[="beta"]."""
    value: object


class PatternError(ValueError):
    pass


class _Token:
    """One step of a pattern. kind is key, index, any, anyindex or deep."""

    def __init__(self, kind, value=None):
        self.kind = kind
        self.value = value

    def matches(self, segment):
        if self.kind == "any":
            return True
        if self.kind == "index":
            return isinstance(segment, int) and segment == self.value
        if self.kind == "anyindex":
            return isinstance(segment, (int, Item))
        if self.kind == "member":
            return isinstance(segment, Member)
        if self.kind == "item":
            return (isinstance(segment, Item) and segment.field == self.value[0]
                    and str(segment.value) == self.value[1])
        if self.kind == "key":
            return isinstance(segment, str) and self.value.match(segment) is not None
        raise AssertionError(self.kind)


def _glob(text, ignore_case):
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in text)
    return re.compile(regex + r"\Z", re.IGNORECASE if ignore_case else 0)


class Pattern:
    """A compiled path pattern such as "database.*.password" or "**.token".

    Syntax: segments separated by dots; "*" matches any one segment, "**" any
    number of segments (including none); a name may contain * and ? wildcards;
    [3] is a list position, [*] any list position and [id=7] the list element
    whose "id" is 7 (see --list-key) and [=*] any element of an unordered list; ["a.b"] is a key written
    literally.
    """

    def __init__(self, text, tokens):
        self.text = text
        self.tokens = tokens

    def __repr__(self):
        return "Pattern(%r)" % self.text

    def matches(self, path):
        return self._match(0, path, 0)

    def _match(self, ti, path, pi):
        tokens = self.tokens
        while ti < len(tokens):
            token = tokens[ti]
            if token.kind == "deep":
                return any(self._match(ti + 1, path, k) for k in range(pi, len(path) + 1))
            if pi >= len(path) or not token.matches(path[pi]):
                return False
            ti += 1
            pi += 1
        return pi == len(path)


def parse_pattern(text, ignore_case=False):
    tokens = []
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == ".":
            i += 1
        elif char == "[":
            i = _bracket(text, i, tokens)
        else:
            j = i
            while j < n and text[j] not in ".[":
                j += 1
            name = text[i:j]
            if name == "**":
                tokens.append(_Token("deep"))
            elif name == "*":
                tokens.append(_Token("any"))
            else:
                tokens.append(_Token("key", _glob(name, ignore_case)))
            i = j
    if not tokens:
        raise PatternError("empty path pattern")
    return Pattern(text, tokens)


def _bracket(text, i, tokens):
    n = len(text)
    if text.startswith('["', i):
        j = i + 2
        while j < n and text[j] != '"':
            j += 2 if text[j] == "\\" else 1
        if not text.startswith('"]', j):
            raise PatternError("unterminated quoted key in pattern %r" % text)
        try:
            key = json.loads(text[i + 1:j + 1])
        except ValueError:
            raise PatternError("bad quoted key in pattern %r" % text)
        tokens.append(_Token("key", re.compile(re.escape(key) + r"\Z")))
        return j + 2
    close = text.find("]", i)
    if close < 0:
        raise PatternError("missing ] in pattern %r" % text)
    inner = text[i + 1:close]
    if inner == "*":
        tokens.append(_Token("anyindex"))
    elif inner.isdigit():
        tokens.append(_Token("index", int(inner)))
    elif inner == "=*":
        tokens.append(_Token("member"))
    elif "=" in inner:
        field, _, value = inner.partition("=")
        tokens.append(_Token("item", (field, value)))
    else:
        raise PatternError("bad index %r in pattern %r" % (inner, text))
    return close + 1
