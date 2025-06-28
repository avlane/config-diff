"""Read configuration files into plain Python data."""
from __future__ import annotations

import configparser
import json
import os
import re
from dataclasses import dataclass


class ConfigError(Exception):
    """A file could not be read or parsed."""


_FORMATS = {}
_EXTENSIONS = {}


_STRINGLY = set()  # formats where every value is a string


def register(name, *extensions, stringly=False):
    """Register a loader for format *name* (and file extensions).

    stringly marks formats such as INI and .env that cannot tell 8080 from "8080".
    """
    def decorate(func):
        _FORMATS[name] = func
        if stringly:
            _STRINGLY.add(name)
        for ext in extensions:
            _EXTENSIONS[ext] = name
        return func
    return decorate


def supported_formats():
    return sorted(_FORMATS)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate key %r" % key)
        result[key] = value
    return result


@register("json", ".json")
def load_json(text, allow_duplicates=False):
    try:
        return json.loads(text, object_pairs_hook=None if allow_duplicates
                          else _reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ConfigError("invalid JSON: %s" % exc)


@register("ini", ".ini", ".cfg", stringly=True)
def load_ini(text, allow_duplicates=False):
    """Parse INI text into {section: {option: value}}.

    Option names keep their case (configparser lower-cases them by default),
    "%" is not special, and options without a value are None.
    """
    parser = configparser.ConfigParser(interpolation=None, allow_no_value=True,
                                       strict=not allow_duplicates)
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ConfigError("invalid INI: %s" % exc.message.strip())
    # parser[section] also contains every key of [DEFAULT]; report those once, under
    # their own section, instead of repeating them in every section.
    defaults = dict(parser.defaults())
    result = {}
    if defaults:
        result[parser.default_section] = defaults
    for name in parser.sections():
        own = {k: v for k, v in parser.items(name)
               if not (k in defaults and v == defaults[k])}
        result[name] = own
    return result


_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\Z")
_ENV_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "$": "$"}


@register("env", ".env", stringly=True)
def load_env(text, allow_duplicates=False):
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
        if name in result and not allow_duplicates:
            raise ConfigError("invalid .env: line %d: %s is defined twice" % (number, name))
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


@register("yaml", ".yaml", ".yml")
def load_yaml(text, allow_duplicates=False):
    """Parse the supported subset of YAML (see configdiff.yamlsubset)."""
    from . import yamlsubset
    try:
        return yamlsubset.loads(text, allow_duplicates)
    except yamlsubset.YamlSubsetError as exc:
        raise ConfigError("invalid or unsupported YAML: %s" % exc)


@register("toml", ".toml")
def load_toml(text, allow_duplicates=False):
    """Parse TOML with the standard library (Python 3.11+)."""
    try:
        import tomllib
    except ImportError:
        raise ConfigError("TOML support needs Python 3.11 or newer (tomllib)")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError("invalid TOML: %s" % exc)


def detect_format(path):
    name = os.path.basename(path).lower()
    if name == ".env" or name.startswith(".env."):
        return "env"
    ext = os.path.splitext(path)[1].lower()
    try:
        return _EXTENSIONS[ext]
    except KeyError:
        raise ConfigError("cannot tell the format of %s from its name; "
                          "supported extensions: %s" % (path, ", ".join(sorted(_EXTENSIONS))))


_COERCE_INT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_COERCE_FLOAT = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+\Z")


def coerce_scalar(value):
    """Turn "true", "42" or "1.5" into a bool, int or float; leave other values alone.

    Deliberately conservative: "0755", "1e3", "yes" and "007" stay strings.
    """
    if not isinstance(value, str):
        return value
    if value in ("true", "True", "TRUE"):
        return True
    if value in ("false", "False", "FALSE"):
        return False
    if value == "null":
        return None
    if _COERCE_INT.match(value):
        return int(value)
    if _COERCE_FLOAT.match(value):
        return float(value)
    return value


def coerce_scalars(data):
    if isinstance(data, dict):
        return {k: coerce_scalars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [coerce_scalars(v) for v in data]
    return coerce_scalar(data)


@dataclass(frozen=True)
class LoadOptions:
    """How files are read; the same options apply to every file of a run.

    coerce: read numbers and true/false in string-only formats (INI, .env) as such.
    allow_duplicates: accept repeated keys, the last one wins.
    lowercase_keys: compare keys case-insensitively by lower-casing them.
    """
    coerce: bool = False
    allow_duplicates: bool = False
    lowercase_keys: bool = False


def lowercase_keys(data):
    """Lower-case every mapping key; two keys that collapse into one are an error."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            lowered = key.lower() if isinstance(key, str) else key
            if lowered in result:
                raise ConfigError("keys %r and %r differ only by case" % (lowered, key))
            result[lowered] = lowercase_keys(value)
        return result
    if isinstance(data, list):
        return [lowercase_keys(v) for v in data]
    return data


def load_text(text, fmt, name="<input>", options=None):
    """Parse *text* as format *fmt*; errors mention *name*."""
    options = options or LoadOptions()
    try:
        data = _FORMATS[fmt](text, options.allow_duplicates)
    except ConfigError as exc:
        raise ConfigError("%s: %s" % (name, exc))
    if options.coerce and fmt in _STRINGLY:
        data = coerce_scalars(data)
    if options.lowercase_keys:
        try:
            data = lowercase_keys(data)
        except ConfigError as exc:
            raise ConfigError("%s: %s" % (name, exc))
    return data


def read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc.strerror or exc))
    except UnicodeDecodeError as exc:
        raise ConfigError("%s is not valid UTF-8: %s" % (path, exc))


def load_file(path, fmt=None, options=None):
    """Load *path*; the format comes from the extension unless *fmt* is given."""
    fmt = fmt or detect_format(path)
    return load_text(read_text(path), fmt, path, options)
