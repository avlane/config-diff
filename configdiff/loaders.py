"""Read configuration files into plain Python data."""
from __future__ import annotations

import configparser
import json
import os


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


LOADERS = {"json": load_json, "ini": load_ini}
EXTENSIONS = {".json": "json", ".ini": "ini", ".cfg": "ini"}


def detect_format(path):
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
