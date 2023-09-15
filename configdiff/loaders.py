"""Read configuration files into plain Python data."""
from __future__ import annotations

import configparser
import json
import os
import re


class ConfigError(Exception):
    """A file could not be read or parsed."""


def load_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError("invalid JSON: %s" % exc)


def load_ini(text):
    """Parse INI text into {section: {option: value}}.

    Option names keep their case (configparser lower-cases them by default),
    "%" is not special, and options without a value are None.
    """
    parser = configparser.ConfigParser(interpolation=None, allow_no_value=True, strict=True)
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ConfigError("invalid INI: %s" % exc.message.strip())
    return {name: dict(parser[name]) for name in parser.sections()}


_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\Z")
_ENV_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "$": "$"}


def load_env(text):
    """Parse a dotenv file into {NAME: value}.

    Supports "export NAME=value", comments, single-quoted values (literal),
    double-quoted values (with \\n, \\t, \\" escapes, possibly spanning several
    lines) and unquoted values (an inline " # comment" is dropped). Nothing is
    interpolated.
    """
    result = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        number = index + 1
        line = lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[7:].lstrip()
        name, sep, rest = line.partition("=")
        name = name.strip()
        if not sep:
            raise ConfigError("invalid .env: line %d: expected NAME=value" % number)
        if not _ENV_KEY.match(name):
            raise ConfigError("invalid .env: line %d: bad variable name %r" % (number, name))
        rest = rest.strip()
        if rest.startswith('"'):
            value, index = _double_quoted(rest[1:], lines, index, number)
        elif rest.startswith("'"):
            end = rest.find("'", 1)
            if end < 0:
                raise ConfigError("invalid .env: line %d: unterminated quote" % number)
            _only_comment_after(rest[end + 1:], number)
            value = rest[1:end]
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].rstrip()
        result[name] = value
    return result


def _double_quoted(rest, lines, index, number):
    out = []
    while True:
        i = 0
        while i < len(rest):
            char = rest[i]
            if char == "\\" and i + 1 < len(rest):
                nxt = rest[i + 1]
                out.append(_ENV_ESCAPES.get(nxt, "\\" + nxt))
                i += 2
                continue
            if char == '"':
                _only_comment_after(rest[i + 1:], number)
                return "".join(out), index
            out.append(char)
            i += 1
        if index >= len(lines):
            raise ConfigError("invalid .env: line %d: unterminated quote" % number)
        out.append("\n")
        rest = lines[index]
        index += 1


def _only_comment_after(rest, number):
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise ConfigError("invalid .env: line %d: unexpected text after closing quote" % number)


LOADERS = {"json": load_json, "ini": load_ini, "env": load_env}
EXTENSIONS = {".json": "json", ".ini": "ini", ".cfg": "ini", ".env": "env"}


def detect_format(path):
    name = os.path.basename(path).lower()
    if name == ".env" or name.startswith(".env."):
        return "env"
    ext = os.path.splitext(path)[1].lower()
    try:
        return EXTENSIONS[ext]
    except KeyError:
        raise ConfigError("cannot tell the format of %s from its name; "
                          "supported extensions: %s" % (path, ", ".join(sorted(EXTENSIONS))))


def load_file(path, fmt=None):
    """Load *path*; the format comes from the extension unless *fmt* is given."""
    fmt = fmt or detect_format(path)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc.strerror or exc))
    except UnicodeDecodeError as exc:
        raise ConfigError("%s is not valid UTF-8: %s" % (path, exc))
    try:
        return LOADERS[fmt](text)
    except ConfigError as exc:
        raise ConfigError("%s: %s" % (path, exc))
