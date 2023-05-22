"""Read configuration files into plain Python data."""
from __future__ import annotations

import json
import os


class ConfigError(Exception):
    """A file could not be read or parsed."""


def load_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError("invalid JSON: %s" % exc)


LOADERS = {"json": load_json}
EXTENSIONS = {".json": "json"}


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
