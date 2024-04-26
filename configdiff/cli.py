"""Command-line interface."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .diffing import Options, diff
from .loaders import ConfigError, load_file
from .paths import PatternError, parse_pattern
from .redact import redact_changes, secret_patterns
from .render import render_json, render_plain

RENDERERS = {"plain": render_plain, "json": render_json}
COLOR_MODES = ("auto", "always", "never")

EXIT_SAME = 0
EXIT_DIFFERENT = 1
EXIT_ERROR = 2


def use_color(mode, stream, environ):
    """Decide whether to emit ANSI colors: --color, then NO_COLOR, then the terminal."""
    if mode == "always":
        return True
    if mode == "never" or environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def _list_key(spec):
    path, sep, name = spec.rpartition("=")
    if not sep or not name:
        raise PatternError("--list-key expects PATH=FIELD, got %r" % spec)
    return parse_pattern(path), name


def build_parser():
    parser = argparse.ArgumentParser(
        prog="config-diff",
        description="Semantic diff of two configuration files.")
    parser.add_argument("old", metavar="OLD", help="the original file")
    parser.add_argument("new", metavar="NEW", help="the changed file")
    parser.add_argument("-i", "--ignore", action="append", default=[], metavar="PATH",
                        help="do not compare PATH, e.g. 'server.port', 'users[*].email' or "
                             "'**.password' (repeatable)")
    parser.add_argument("-k", "--list-key", action="append", default=[], metavar="PATH=FIELD",
                        help="compare the list at PATH by each item's FIELD instead of by "
                             "position, e.g. 'servers=name' (repeatable)")
    parser.add_argument("-u", "--unordered", action="append", default=[], metavar="PATH",
                        help="the list at PATH is a set: ignore the order of its elements "
                             "(repeatable)")
    parser.add_argument("--unordered-lists", action="store_true",
                        help="ignore the order of every list")
    parser.add_argument("--redact", action="append", default=[], metavar="PATH",
                        help="hide the values at PATH in the output (repeatable)")
    parser.add_argument("--redact-secrets", action="store_true",
                        help="hide values of keys named like password, secret, token, "
                             "api_key... and passwords inside URLs")
    parser.add_argument("-o", "--output", choices=sorted(RENDERERS), default="plain",
                        help="how to print the differences (default: plain)")
    parser.add_argument("--color", choices=COLOR_MODES, default="auto",
                        help="colorize plain output (default: auto = only on a terminal "
                             "and when NO_COLOR is not set)")
    parser.add_argument("--version", action="version", version="config-diff " + __version__)
    return parser


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = Options(ignore=[parse_pattern(p) for p in args.ignore],
                          list_keys=[_list_key(spec) for spec in args.list_key],
                          unordered=[parse_pattern(p) for p in
                                     (["**"] if args.unordered_lists else args.unordered)])
    except PatternError as exc:
        parser.error(str(exc))
    try:
        redactions = [parse_pattern(p) for p in args.redact]
    except PatternError as exc:
        parser.error(str(exc))
    if args.redact_secrets:
        redactions += secret_patterns()
    try:
        old = load_file(args.old)
        new = load_file(args.new)
    except ConfigError as exc:
        stderr.write("config-diff: error: %s\n" % exc)
        return EXIT_ERROR
    changes = diff(old, new, options)
    if redactions or args.redact_secrets:
        changes = redact_changes(changes, redactions, mask_urls=args.redact_secrets)
    if args.output == "plain":
        stdout.write(render_plain(changes, use_color(args.color, stdout, os.environ)))
    else:
        stdout.write(RENDERERS[args.output](changes))
    return EXIT_DIFFERENT if changes else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
