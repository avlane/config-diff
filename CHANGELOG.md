# Changelog

## 1.0.0

First stable release. The command line, the exit codes and the JSON output
(`equal`, `summary`, `changes[].kind/path/segments/old/new`) are now stable.

Highlights of the 0.x series:

- Formats: JSON, INI, `.env`, TOML (`tomllib`) and a safe hand-written YAML subset.
- Semantic comparison: key order ignored, types respected (`true` is not `1`), lists by
  position, by key field (`--list-key`) or as sets (`--unordered`).
- Path patterns for `--ignore`, `--only`, `--redact` and `--list-key`, with wildcards.
- Output: plain (colored), JSON, Markdown; `--summary`, `--quiet`, `--fail-on`.
- Secrets: `--redact`, `--redact-secrets`.
- Cross-format comparison: `--coerce`, `--case-insensitive-keys`, `--env-prefix`, `--unflatten`.
- Directory comparison; standard input.
- Requires Python 3.10 or newer (3.9 until late 2025).
