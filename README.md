# config-diff

A semantic diff for configuration files. Instead of comparing lines it compares
the parsed values, so reordered keys, different indentation and comments do not
show up as changes.

Work in progress. Planned: JSON, INI and `.env` files, ignore paths, lists
compared by key, colored/plain/JSON output and exit codes that work in CI.

    config-diff old.json new.json

Exit status: 0 if the files are equivalent, 1 if they differ, 2 on errors.
Supported formats: JSON (`.json`), INI (`.ini`, `.cfg`), dotenv files (`.env`, `prod.env`,
`.env.local`) and TOML (`.toml`, needs Python 3.11 or newer for `tomllib`).
Use `-o json` for machine-readable output.
Ignore noisy paths with `-i/--ignore` (repeatable):

    config-diff old.json new.json -i version -i 'server.*.port' -i '**.password'

Patterns are dotted paths: `*` matches one segment, `**` any number of
segments, `[0]` / `[*]` list positions, `["a.b"]` a key that contains a dot.
Lists are compared by position unless you say how to identify their items.
`--list-key servers=name` matches the elements of `servers` by their `name`, so
reordering is not a change and differences are reported as `servers[name=web-2].port`.
On a terminal the plain output is colored; use `--color never` or set `NO_COLOR` to turn
it off, `--color always` to force it.
## Secrets

Diffs of `.env` files tend to end up in chat and pull requests. Hide values with
`--redact PATH` (same patterns as `--ignore`) or `--redact-secrets`, which hides keys
named like `password`, `secret`, `token`, `api_key`, `credential` and the password part of
URLs such as `postgres://user:***@host/db`. Changes are still reported, without the values.
