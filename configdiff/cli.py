"""Command-line interface."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .diffing import diff
from .loaders import ConfigError, load_file
from .render import render_plain

EXIT_SAME = 0
EXIT_DIFFERENT = 1
EXIT_ERROR = 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="config-diff",
        description="Semantic diff of two configuration files.")
    parser.add_argument("old", metavar="OLD", help="the original file")
    parser.add_argument("new", metavar="NEW", help="the changed file")
    parser.add_argument("--version", action="version", version="config-diff " + __version__)
    return parser


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        old = load_file(args.old)
        new = load_file(args.new)
    except ConfigError as exc:
        stderr.write("config-diff: error: %s\n" % exc)
        return EXIT_ERROR
    changes = diff(old, new)
    stdout.write(render_plain(changes))
    return EXIT_DIFFERENT if changes else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
