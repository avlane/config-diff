"""Hide secrets before differences are printed."""
from __future__ import annotations

import re

from .diffing import ADDED, REMOVED, Change
from .paths import parse_pattern

REDACTED = "<redacted>"

# Key names that usually hold secrets, matched case-insensitively at any depth.
SECRET_PATTERNS = [
    "**.*password*", "**.*passwd*", "**.*secret*", "**.*token*", "**.*api_key*",
    "**.*apikey*", "**.*private_key*", "**.*credential*",
]

_URL_PASSWORD = re.compile(r"(?<=://)([^/\s:@]*):[^@/\s]+@")


def secret_patterns():
    return [parse_pattern(p, ignore_case=True) for p in SECRET_PATTERNS]


def mask_url_password(text):
    """postgres://user:pw@host/db -> postgres://user:***@host/db"""
    return _URL_PASSWORD.sub(lambda m: m.group(1) + ":***@", text)


def _redact_value(patterns, mask_urls, path, value):
    if any(p.matches(path) for p in patterns):
        return REDACTED
    if isinstance(value, dict):
        return {k: _redact_value(patterns, mask_urls, path + (k,), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(patterns, mask_urls, path + (i,), v) for i, v in enumerate(value)]
    if mask_urls and isinstance(value, str):
        return mask_url_password(value)
    return value


def redact_changes(changes, patterns, mask_urls=False):
    """Return *changes* with the values at (or below) matching paths replaced.

    The kind and the path of every change are kept, so a changed secret is
    still reported as changed - just without showing either value.
    """
    out = []
    for change in changes:
        old = None if change.kind == ADDED else _redact_value(patterns, mask_urls, change.path, change.old)
        new = None if change.kind == REMOVED else _redact_value(patterns, mask_urls, change.path, change.new)
        out.append(Change(change.kind, change.path, old, new))
    return out
