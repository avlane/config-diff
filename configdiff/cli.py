"""Command-line interface."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .diffing import Options, diff
from .loaders import ConfigError, load_file
from .paths import PatternError, parse_pattern
from .render import render_json, render_plain

RENDERERS = {"plain": render_plain, "json": render_json}

EXIT_SAME = 0
EXIT_DIFFERENT = 1
EXIT_ERROR = 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="config-diff",
        description="Semantic diff of two configuration files.")
    parser.add_argument("old", metavar="OLD", help="the original file")
    parser.add_argument("new", metavar="NEW", help="the changed file")
    parser.add_argument("-i", "--ignore", action="append", default=[], metavar="PATH",
                        help="do not compare PATH, e.g. 'server.port', 'users[*].email' or "
                             "'**.password' (repeatable)")
    parser.add_argument("-o", "--output", choices=sorted(RENDERERS), default="plain",
                        help="how to print the differences (default: plain)")
    parser.add_argument("--version", action="version", version="config-diff " + __version__)
    return parser


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = Options(ignore=[parse_pattern(p) for p in args.ignore])
    except PatternError as exc:
        parser.error(str(exc))
    try:
        old = load_file(args.old)
        new = load_file(args.new)
    except ConfigError as exc:
        stderr.write("config-diff: error: %s\n" % exc)
        return EXIT_ERROR
    changes = diff(old, new, options)
    stdout.write(RENDERERS[args.output](changes))
    return EXIT_DIFFERENT if changes else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
