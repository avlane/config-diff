"""Command-line interface."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .dirdiff import DIFFERENT, ONLY_NEW, ONLY_OLD, compare_dirs
from .diffing import ADDED, CHANGED, REMOVED, Options, diff
from .loaders import ConfigError, LoadOptions, load_file, load_text, supported_formats
from .paths import PatternError, parse_pattern, read_pattern_file
from .redact import redact_changes, secret_patterns
from .render import (directory_summary_line, render_directory_json, render_directory_markdown,
                     render_directory_plain, render_json, render_markdown, render_plain,
                     summary_line)

RENDERERS = {"plain": render_plain, "json": render_json, "markdown": render_markdown}
DIRECTORY_RENDERERS = {"json": render_directory_json, "markdown": render_directory_markdown}
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


def _fail_on(text):
    kinds = [part.strip() for part in text.split(",") if part.strip()]
    for kind in kinds:
        if kind not in (ADDED, REMOVED, CHANGED):
            raise argparse.ArgumentTypeError(
                "unknown kind %r (use added, removed and/or changed)" % kind)
    if not kinds:
        raise argparse.ArgumentTypeError("expected at least one of added, removed, changed")
    return frozenset(kinds)


def _list_key(spec):
    path, sep, name = spec.rpartition("=")
    if not sep or not name:
        raise PatternError("--list-key expects PATH=FIELD, got %r" % spec)
    return parse_pattern(path), name


def build_parser():
    parser = argparse.ArgumentParser(
        prog="config-diff",
        description="Semantic diff of two configuration files, or of two directories of them.")
    parser.add_argument("old", metavar="OLD",
                        help="the original file or directory, or - for standard input")
    parser.add_argument("new", metavar="NEW",
                        help="the changed file or directory, or - for standard input")
    formats = ("auto",) + tuple(supported_formats())
    parser.add_argument("-f", "--format", choices=formats, default="auto",
                        help="input format of both files (default: from the extension)")
    parser.add_argument("--old-format", choices=formats, help="input format of OLD only")
    parser.add_argument("--new-format", choices=formats, help="input format of NEW only")
    parser.add_argument("--coerce", action="store_true",
                        help="read numbers and true/false in INI and .env files as such, so "
                             "PORT=8080 equals {\"PORT\": 8080}")
    parser.add_argument("--allow-duplicates", action="store_true",
                        help="accept repeated keys (the last one wins) instead of failing")
    parser.add_argument("--case-insensitive-keys", action="store_true",
                        help="compare keys ignoring case (they are lower-cased before "
                             "comparing, so write PATH patterns in lower case)")
    parser.add_argument("-i", "--ignore", action="append", default=[], metavar="PATH",
                        help="do not compare PATH, e.g. 'server.port', 'users[*].email' or "
                             "'**.password' (repeatable)")
    parser.add_argument("--ignore-file", action="append", default=[], metavar="FILE",
                        help="read paths to ignore from FILE, one per line (# starts a comment)")
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
    parser.add_argument("--fail-on", type=_fail_on, default=frozenset((ADDED, REMOVED, CHANGED)),
                        metavar="KINDS",
                        help="comma-separated kinds of difference that make the exit status 1: "
                             "added, removed, changed (default: all). Other differences are "
                             "still printed.")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--summary", action="store_true",
                           help="end plain output with a count of the differences")
    verbosity.add_argument("-q", "--quiet", action="store_true",
                           help="print nothing; the exit status tells the result")
    parser.add_argument("--color", choices=COLOR_MODES, default="auto",
                        help="colorize plain output (default: auto = only on a terminal "
                             "and when NO_COLOR is not set)")
    parser.add_argument("--version", action="version", version="config-diff " + __version__)
    return parser


def load_source(path, fmt, stdin, options):
    """Load a file, or standard input when *path* is "-"."""
    if path != "-":
        return load_file(path, None if fmt == "auto" else fmt, options)
    if fmt == "auto":
        raise ConfigError("standard input has no file name: say which format it is with "
                          "--format (or --old-format / --new-format)")
    return load_text(stdin.read(), fmt, "<stdin>", options)


def _failing(args, changes):
    return any(c.kind in args.fail_on for c in changes)


def main(argv=None, stdout=None, stderr=None, stdin=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    stdin = stdin or sys.stdin
    parser = build_parser()
    args = parser.parse_args(argv)

    ignored = list(args.ignore)
    for name in args.ignore_file:
        try:
            ignored.extend(read_pattern_file(name))
        except OSError as exc:
            parser.error("cannot read ignore file %s: %s" % (name, exc.strerror or exc))
    try:
        options = Options(ignore=[parse_pattern(p) for p in ignored],
                          list_keys=[_list_key(spec) for spec in args.list_key],
                          unordered=[parse_pattern(p) for p in
                                     (["**"] if args.unordered_lists else args.unordered)])
        redactions = [parse_pattern(p) for p in args.redact]
    except PatternError as exc:
        parser.error(str(exc))
    if args.redact_secrets:
        redactions += secret_patterns()
    if args.old == "-" and args.new == "-":
        parser.error("only one of OLD and NEW can be read from standard input")
    load_options = LoadOptions(coerce=args.coerce, allow_duplicates=args.allow_duplicates,
                                lowercase_keys=args.case_insensitive_keys)

    def compare(old, new):
        changes = diff(old, new, options)
        if redactions:
            changes = redact_changes(changes, redactions, mask_urls=args.redact_secrets)
        return changes

    color = use_color(args.color, stdout, os.environ)
    try:
        if os.path.isdir(args.old) or os.path.isdir(args.new):
            return _compare_directories(parser, args, load_options, compare, stdout, color)
        old = load_source(args.old, args.old_format or args.format, stdin, load_options)
        new = load_source(args.new, args.new_format or args.format, stdin, load_options)
    except ConfigError as exc:
        stderr.write("config-diff: error: %s\n" % exc)
        return EXIT_ERROR

    changes = compare(old, new)
    if args.quiet:
        pass
    elif args.output == "plain":
        stdout.write(render_plain(changes, color))
        if args.summary:
            stdout.write(summary_line(changes) + "\n")
    else:
        stdout.write(RENDERERS[args.output](changes))
    return EXIT_DIFFERENT if _failing(args, changes) else EXIT_SAME


def _compare_directories(parser, args, load_options, compare, stdout, color):
    if not (os.path.isdir(args.old) and os.path.isdir(args.new)):
        parser.error("OLD and NEW must both be directories or both be files")
    if any(f not in (None, "auto") for f in (args.format, args.old_format, args.new_format)):
        parser.error("--format cannot be used when comparing directories: "
                     "files are recognised by their extension")

    def compare_files(old_path, new_path):
        return compare(load_file(old_path, None, load_options),
                       load_file(new_path, None, load_options))

    results = compare_dirs(args.old, args.new, compare_files)
    if args.quiet:
        pass
    elif args.output == "plain":
        stdout.write(render_directory_plain(results, color))
        if args.summary:
            stdout.write(directory_summary_line(results) + "\n")
    else:
        stdout.write(DIRECTORY_RENDERERS[args.output](results))
    failing = False
    for result in results:
        if result.status == ONLY_OLD:
            failing = failing or REMOVED in args.fail_on
        elif result.status == ONLY_NEW:
            failing = failing or ADDED in args.fail_on
        elif result.status == DIFFERENT:
            failing = failing or _failing(args, result.changes)
    return EXIT_DIFFERENT if failing else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
