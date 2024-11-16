# config-diff

A semantic diff for configuration files. Instead of comparing lines it compares
the parsed values, so reordered keys, different indentation and comments do not
show up as changes.

Work in progress. Planned: JSON, INI and `.env` files, ignore paths, lists
compared by key, colored/plain/JSON output and exit codes that work in CI.

    config-diff old.json new.json

Exit status: 0 if the files are equivalent, 1 if they differ, 2 on errors.
Supported formats: JSON (`.json`), INI (`.ini`, `.cfg`), dotenv files (`.env`, `prod.env`,
`.env.local`), TOML (`.toml`, needs Python 3.11 or newer for `tomllib`) and YAML
(`.yaml`, `.yml`).

### About the YAML support

There is no YAML parser in the Python standard library and config-diff has no
dependencies, so it ships a small hand-written parser for the **subset** of YAML that
configuration files use: block mappings and sequences, single-line flow collections,
quoted and plain scalars, literal and folded block scalars, comments. It follows the
YAML 1.2 core schema (`yes`/`no`/`on`/`off` are strings, mapping keys are always strings).

It never builds arbitrary objects, and it refuses what it does not implement - anchors
and aliases, merge keys, tags, multiple documents, complex keys, multi-line plain or
quoted scalars - with an error that names the line, rather than guessing. If you need
those, convert the file to JSON first (for example `yq -o=json`) and diff that.
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
Read one side from standard input with `-` (say which format it is):

    kubectl get cm app -o json | config-diff - app.json --old-format json

Force a format with `-f/--format`, or `--old-format` / `--new-format`; the two
files do not have to be in the same format.
## Comparing across formats

INI and `.env` files only have strings. `--coerce` reads `8080`, `1.5`, `true`, `false` and
`null` in those files as numbers, booleans and null so they can be compared with JSON,
TOML or YAML: `config-diff .env config.json --coerce`. Values such as `0755` or `1e3` stay
strings.
