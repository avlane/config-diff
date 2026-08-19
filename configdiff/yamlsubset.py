"""A small, safe parser for the commonly used subset of YAML.

It is not a general YAML implementation. It reads the YAML that configuration
files are actually written in and refuses (with a line number) everything else
instead of guessing.

Supported:

* block mappings and block sequences, nested to any depth, with plain or quoted keys
* flow collections on a single line: ``[a, b]`` and ``{a: 1, b: [2, 3]}``
* plain, 'single-quoted' and "double-quoted" scalars on one line
* literal (``|``) and folded (``>``) block scalars, with ``-`` / ``+`` chomping
* comments
* null (``null``, ``~``, empty), booleans (``true``/``false``), integers
  (decimal, ``0x`` and ``0o``) and floats, following the YAML 1.2 core schema:
  ``yes``, ``no``, ``on``, ``off`` and dates are plain strings

Not supported, and reported as errors: anchors and aliases (``&a``, ``*a``,
``<<``), tags (``!!str``), multiple documents, directives, complex keys
(``? key``), explicit indentation indicators for block scalars, and scalars or
flow collections that continue on the next line. Mapping keys are always
strings.
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


def loads(text, allow_duplicates=False, empty=None):
    """Parse *text* and return dicts, lists and scalars.

    Duplicate mapping keys are an error unless *allow_duplicates* is set, in
    which case the last one wins. A document without any content (empty, or
    only comments) gives *empty*.
    """
    return _Parser(text, allow_duplicates, empty).parse()


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
    def __init__(self, text, allow_duplicates=False, empty=None):
        self.allow_duplicates = allow_duplicates
        self.empty = empty
        if text.startswith("\ufeff"):
            text = text[1:]
        self.raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.pos = 0          # next unread index in self.raw
        self.current = None   # the logical line that was peeked but not consumed yet
        self.seen_marker = False
        self.seen_content = False

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
            if stripped == "..." and not raw.startswith(" "):
                self.pos = len(self.raw)  # end of document
                return None
            if stripped == "---" and not raw.startswith(" "):
                if self.seen_marker or self.seen_content:
                    raise YamlSubsetError("multiple documents are not supported", number)
                self.seen_marker = True
                continue
            if raw.startswith("--- ") or raw.startswith("%"):
                raise YamlSubsetError("document markers with content and directives are not "
                                      "supported", number)
            self.seen_content = True
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
            return self.empty
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
            return self._parse_sequence(line.indent)
        if line.text.startswith("? "):
            raise YamlSubsetError("complex mapping keys are not supported", line.no)
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
            if key == "<<":
                raise YamlSubsetError("merge keys (<<) are not supported", line.no)
            self._advance()
            if key in result and not self.allow_duplicates:
                raise YamlSubsetError("duplicate key %r" % key, line.no)
            result[key] = self._parse_value(rest, line, indent)
        return result

    def _parse_sequence(self, indent):
        result = []
        while True:
            line = self._peek()
            if line is None or line.indent < indent:
                break
            if line.indent > indent:
                raise YamlSubsetError("unexpected indentation", line.no)
            if not (line.text == "-" or line.text.startswith("- ")):
                break  # e.g. the next key of a mapping that holds this sequence
            rest = line.text[1:]
            content = rest.lstrip(" ")
            if not content or content.startswith("#"):
                self._advance()
                following = self._peek()
                if following is not None and following.indent > indent:
                    result.append(self._parse_block(following.indent))
                else:
                    result.append(None)
                continue
            # "- key: value" and "- - item": re-read the rest of the line as if it
            # started at the column where the content begins.
            column = indent + 1 + (len(rest) - len(content))
            self.current = _Line(line.no, column, content, base=indent)
            result.append(self._parse_block(column))
        return result

    def _parse_value(self, rest, line, indent):
        """The value of "key: rest" where the key sits at column *indent*."""
        if rest == "" or rest.startswith("#"):
            following = self._peek()
            if following is not None:
                if following.indent > indent:
                    return self._parse_block(following.indent)
                if following.indent == indent and (following.text == "-"
                                                   or following.text.startswith("- ")):
                    return self._parse_sequence(indent)  # "key:\n- a\n- b" is allowed
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
        if first in "|>":
            return self._parse_block_scalar(text, number, parent)
        if first in "\"'":
            value, end = self._read_quoted(text, 0, number)
            self._expect_end(text[end:], number)
            return value
        if first in "[{":
            value, end = self._parse_flow(text, 0, number)
            self._expect_end(text[end:], number)
            return value
        if first in "&*!":
            raise YamlSubsetError("anchors, aliases and tags are not supported", number)
        plain = re.split(r"\s#", text, maxsplit=1)[0].rstrip()
        if re.search(r":(?: |\Z)", plain):
            raise YamlSubsetError("mapping values are not allowed here", number)
        return _resolve_plain(plain)

    def _parse_block_scalar(self, header, number, parent):
        """Read a | or > scalar; its lines follow, indented deeper than *parent*."""
        match = re.fullmatch(r"([|>])([+-]?)\s*(?:#.*)?", header)
        if match is None:
            raise YamlSubsetError("unsupported block scalar header %r (indentation indicators "
                                  "are not supported)" % header, number)
        style, chomp = match.group(1), match.group(2)
        lines = []
        block_indent = None
        while self.pos < len(self.raw):
            raw = self.raw[self.pos].rstrip("\r")
            if not raw.strip():
                lines.append("")
                self.pos += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if block_indent is None:
                if indent <= parent:
                    break
                block_indent = indent
            elif indent < block_indent:
                break
            lines.append(raw[block_indent:])
            self.pos += 1
        trailing = 0
        while lines and lines[-1] == "":
            lines.pop()
            trailing += 1
        body = "\n".join(lines) if style == "|" else self._fold(lines)
        if chomp == "-":
            return body
        if chomp == "+":
            return body + "\n" * (trailing + 1) if lines else "\n" * trailing
        return body + "\n" if lines else ""

    @staticmethod
    def _fold(lines):
        """Folded style: single line breaks become spaces, blank lines become breaks."""
        out = []
        for i, line in enumerate(lines):
            if i == 0:
                out.append(line)
                continue
            previous = lines[i - 1]
            if line == "":
                out.append("\n")
            elif previous == "":
                out.append(line)
            elif line[0] in " \t" or previous[0] in " \t":
                out.append("\n" + line)  # more-indented lines keep their line breaks
            else:
                out.append(" " + line)
        return "".join(out)

    # ---- flow collections (single line only) -------------------------

    def _parse_flow(self, text, i, number):
        """Parse one flow node at text[i]; return (value, index after it)."""
        i = self._skip_spaces(text, i)
        if i >= len(text):
            raise YamlSubsetError("unexpected end of flow collection (multi-line flow "
                                  "collections are not supported)", number)
        char = text[i]
        if char == "[":
            return self._parse_flow_sequence(text, i + 1, number)
        if char == "{":
            return self._parse_flow_mapping(text, i + 1, number)
        if char in "\"'":
            return self._read_quoted(text, i, number)
        if char in "&*!":
            raise YamlSubsetError("anchors, aliases and tags are not supported", number)
        end = self._flow_plain_end(text, i)
        return _resolve_plain(text[i:end].strip()), end

    def _parse_flow_sequence(self, text, i, number):
        items = []
        while True:
            i = self._skip_spaces(text, i)
            if i < len(text) and text[i] == "]":
                return items, i + 1
            value, i = self._parse_flow(text, i, number)
            items.append(value)
            i = self._skip_spaces(text, i)
            if i < len(text) and text[i] == ",":
                i += 1
            elif i < len(text) and text[i] == "]":
                return items, i + 1
            else:
                raise YamlSubsetError("expected ',' or ']' in flow sequence", number)

    def _parse_flow_mapping(self, text, i, number):
        result = {}
        while True:
            i = self._skip_spaces(text, i)
            if i < len(text) and text[i] == "}":
                return result, i + 1
            if i >= len(text):
                raise YamlSubsetError("unterminated flow mapping (multi-line flow collections "
                                      "are not supported)", number)
            if text[i] in "\"'":
                key, i = self._read_quoted(text, i, number)
            elif text[i] in "[{":
                raise YamlSubsetError("collections cannot be mapping keys", number)
            else:
                end = self._flow_plain_end(text, i)
                key = text[i:end].strip()
                i = end
            i = self._skip_spaces(text, i)
            value = None
            if i < len(text) and text[i] == ":":
                value, i = self._parse_flow(text, i + 1, number)
                i = self._skip_spaces(text, i)
            if key in result and not self.allow_duplicates:
                raise YamlSubsetError("duplicate key %r" % key, number)
            result[key] = value
            if i < len(text) and text[i] == ",":
                i += 1
            elif i < len(text) and text[i] == "}":
                return result, i + 1
            else:
                raise YamlSubsetError("expected ',' or '}' in flow mapping", number)

    @staticmethod
    def _skip_spaces(text, i):
        while i < len(text) and text[i] in " \t":
            i += 1
        return i

    @staticmethod
    def _flow_plain_end(text, i):
        j = i
        while j < len(text):
            char = text[j]
            if char in ",[]{}":
                break
            if char == ":" and (j + 1 >= len(text) or text[j + 1] in " ,]}"):
                break
            if char == "#" and j > i and text[j - 1] == " ":
                break
            j += 1
        return j

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
