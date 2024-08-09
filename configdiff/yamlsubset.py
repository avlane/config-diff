"""A small, safe parser for the commonly used subset of YAML.

It is not a general YAML implementation. It reads the YAML that configuration
files are actually written in and refuses (with a line number) everything else
instead of guessing.

Supported:

* block mappings, nested to any depth, with plain or quoted keys
* plain, 'single-quoted' and "double-quoted" scalars on one line
* comments
* null (``null``, ``~``, empty), booleans (``true``/``false``), integers
  (decimal, ``0x`` and ``0o``) and floats, following the YAML 1.2 core schema:
  ``yes``, ``no``, ``on``, ``off`` and dates are plain strings
"""
from __future__ import annotations

import re


class YamlSubsetError(ValueError):
    """The text is invalid YAML, or uses YAML that this parser does not support."""

    def __init__(self, message, line=None):
        super().__init__("line %d: %s" % (line, message) if line else message)
        self.line = line


class _Line:
    __slots__ = ("no", "indent", "text", "base")

    def __init__(self, no, indent, text, base=None):
        self.no = no
        self.indent = indent
        self.text = text
        self.base = indent if base is None else base


_INT = re.compile(r"[-+]?[0-9]+\Z")
_HEX = re.compile(r"0x[0-9a-fA-F]+\Z")
_OCT = re.compile(r"0o[0-7]+\Z")
_FLOAT = re.compile(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?\Z")

_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
    "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
    "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}


def loads(text):
    """Parse *text* and return dicts, lists and scalars."""
    return _Parser(text).parse()


def _resolve_plain(text):
    if text in ("", "~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if _INT.match(text):
        return int(text)
    if _HEX.match(text):
        return int(text[2:], 16)
    if _OCT.match(text):
        return int(text[2:], 8)
    if _FLOAT.match(text):
        return float(text)
    if text in (".inf", ".Inf", ".INF", "+.inf", "+.Inf", "+.INF"):
        return float("inf")
    if text in ("-.inf", "-.Inf", "-.INF"):
        return float("-inf")
    if text in (".nan", ".NaN", ".NAN"):
        return float("nan")
    return text


class _Parser:
    def __init__(self, text):
        if text.startswith("\ufeff"):
            text = text[1:]
        self.raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.pos = 0          # next unread index in self.raw
        self.current = None   # the logical line that was peeked but not consumed yet

    # ---- line handling -------------------------------------------------

    def _peek(self):
        """Return the next line that is not blank or a comment, without consuming it."""
        if self.current is not None:
            return self.current
        while self.pos < len(self.raw):
            number = self.pos + 1
            raw = self.raw[self.pos].rstrip()
            self.pos += 1
            stripped = raw.lstrip(" \t")
            if not stripped or stripped.startswith("#"):
                continue
            lead = raw[:len(raw) - len(stripped)]
            if "\t" in lead:
                raise YamlSubsetError("tabs are not allowed for indentation", number)
            self.current = _Line(number, len(lead), stripped)
            return self.current
        return None

    def _advance(self):
        self.current = None

    def parse(self):
        first = self._peek()
        if first is None:
            return None
        value = self._parse_block(first.indent)
        extra = self._peek()
        if extra is not None:
            raise YamlSubsetError("unexpected content after the end of the document", extra.no)
        return value

    # ---- block structure -----------------------------------------------

    def _parse_block(self, indent):
        line = self._peek()
        if line is None:
            return None
        if line.text == "-" or line.text.startswith("- "):
            raise YamlSubsetError("block sequences are not supported yet", line.no)
        if self._split_key(line) is not None:
            return self._parse_mapping(line.indent)
        self._advance()
        return self._parse_inline(line.text, line.no, line.base)

    def _parse_mapping(self, indent):
        result = {}
        while True:
            line = self._peek()
            if line is None or line.indent < indent:
                break
            if line.indent > indent:
                raise YamlSubsetError(
                    "unexpected indentation (multi-line plain and quoted scalars are not "
                    "supported)", line.no)
            split = self._split_key(line)
            if split is None:
                raise YamlSubsetError("expected 'key: value'", line.no)
            key, rest = split
            self._advance()
            if key in result:
                raise YamlSubsetError("duplicate key %r" % key, line.no)
            result[key] = self._parse_value(rest, line, indent)
        return result

    def _parse_value(self, rest, line, indent):
        """The value of "key: rest" where the key sits at column *indent*."""
        if rest == "" or rest.startswith("#"):
            following = self._peek()
            if following is not None and following.indent > indent:
                return self._parse_block(following.indent)
            return None
        return self._parse_inline(rest, line.no, indent)

    def _split_key(self, line):
        """Split "key: rest" into (key, rest), or return None if it isn't a mapping entry."""
        text = line.text
        if text[0] in "\"'":
            key, end = self._read_quoted(text, 0, line.no)
            after = text[end:].lstrip(" ")
            if not after.startswith(":") or (len(after) > 1 and after[1] != " "):
                return None
            return key, after[1:].strip()
        if text[0] in "[{":
            return None
        head = re.split(r"\s#", text, maxsplit=1)[0]
        match = re.search(r":(?= |\Z)", head)
        if match is None:
            return None
        key = head[:match.start()].rstrip()
        if not key:
            raise YamlSubsetError("empty key", line.no)
        if key[0] in "&*!":
            raise YamlSubsetError("anchors, aliases and tags are not supported", line.no)
        return key, text[match.end():].strip()

    # ---- scalars ---------------------------------------------------------

    def _parse_inline(self, text, number, parent):
        """Parse the value text that follows "key:" (or stands alone)."""
        first = text[0]
        if first in "\"'":
            value, end = self._read_quoted(text, 0, number)
            self._expect_end(text[end:], number)
            return value
        if first in "[{":
            raise YamlSubsetError("flow collections are not supported yet", number)
        if first in "&*!":
            raise YamlSubsetError("anchors, aliases and tags are not supported", number)
        plain = re.split(r"\s#", text, maxsplit=1)[0].rstrip()
        if re.search(r":(?: |\Z)", plain):
            raise YamlSubsetError("mapping values are not allowed here", number)
        return _resolve_plain(plain)

    @staticmethod
    def _expect_end(rest, number):
        rest = rest.strip()
        if rest and not rest.startswith("#"):
            raise YamlSubsetError("unexpected text after the closing quote", number)

    @staticmethod
    def _read_quoted(text, start, number):
        """Read a quoted scalar starting at text[start]; return (value, end)."""
        quote = text[start]
        out = []
        i = start + 1
        while i < len(text):
            char = text[i]
            if quote == "'":
                if char == "'":
                    if text[i + 1:i + 2] == "'":
                        out.append("'")
                        i += 2
                        continue
                    return "".join(out), i + 1
                out.append(char)
                i += 1
                continue
            if char == '"':
                return "".join(out), i + 1
            if char == "\\":
                i += 1
                if i >= len(text):
                    break
                esc = text[i]
                if esc in "xuU":
                    width = {"x": 2, "u": 4, "U": 8}[esc]
                    digits = text[i + 1:i + 1 + width]
                    try:
                        if len(digits) != width:
                            raise ValueError
                        out.append(chr(int(digits, 16)))
                    except ValueError:
                        raise YamlSubsetError("bad \\%s escape" % esc, number)
                    i += 1 + width
                    continue
                if esc not in _ESCAPES:
                    raise YamlSubsetError("unknown escape sequence \\%s" % esc, number)
                out.append(_ESCAPES[esc])
                i += 1
                continue
            out.append(char)
            i += 1
        raise YamlSubsetError("unterminated quoted scalar (multi-line quoted scalars are not "
                              "supported)", number)
