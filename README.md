# config-diff

A semantic diff for configuration files. It compares what the files *mean*, not how they
are written, so reordered keys, different indentation, comments and quoting style do not
show up as changes.

Supports **JSON, INI, `.env`, TOML and YAML** (a safe subset, see below), including
comparisons across formats. Pure Python standard library, no dependencies.

    $ config-diff staging.json prod.json
    ~ server.workers: 4 -> 16
    ~ database.pool.max: 10 -> 50
    + database.replica: "db-ro.internal"
    - features.beta_ui: true

    $ echo $?
    1

## Install

    pip install .            # installs the `config-diff` command
    python -m configdiff     # or run from a checkout

Python 3.10 or newer (TOML needs 3.11+ for `tomllib`).

## Usage

    config-diff OLD NEW [options]

`OLD` and `NEW` are files or two directories. The format comes from the extension
(`.json`, `.ini`/`.cfg`, `.env`/`prod.env`/`.env.local`, `.toml`, `.yaml`/`.yml`); override
it with `-f/--format`, `--old-format` or `--new-format`. Use `-` to read one side from
standard input (then a format is required):

    kubectl get configmap app -o json | config-diff - app.json --old-format json

### What counts as a difference

* Mappings are compared by key; order does not matter.
* Lists are compared by position, unless you say otherwise:
  * `-k servers=name` matches the items of `servers` by their `name` field, so reordering is
    not a change and differences read `servers[name=web-2].port: 8002 -> 9002`;
  * `-u tags` (or `--unordered-lists` for all lists) treats a list as a set of values.
* Types matter: `true` is not `1`, and `"1"` is not `1`. `1` and `1.0` are equal.
* Repeated keys in one file are an error (`--allow-duplicates` lets the last one win).
* INI and `.env` files only have strings. `--coerce` reads `8080`, `1.5`, `true`, `false`
  and `null` in them as numbers, booleans and null, so `.env` can be compared with JSON.
  `0755` and `1e3` stay strings.
* `--case-insensitive-keys` lower-cases all keys first.
* Twelve-factor style environment variables can be compared with a nested config file:
  `--env-prefix APP__ --unflatten __` turns `APP__DB__HOST=db1` into `{"DB": {"HOST": "db1"}}`
  (combine with `--case-insensitive-keys --coerce`).

### Choosing paths

Paths are written `server.ports[1].name`. Keys with special characters are bracketed:
`logging["app.module"]`. Items of keyed lists are `servers[name=web-1]`.

| pattern | matches |
| --- | --- |
| `server.port` | exactly that path |
| `*` | any one key or position |
| `**` | any number of segments, including none |
| `db.pass*`, `?` | wildcards inside a key name |
| `users[0]`, `users[*]` | a list position / any position |
| `servers[name=web-1]` | the keyed list item with that value |

    config-diff a.json b.json -i version -i '**.password'       # leave paths out
    config-diff a.json b.json --ignore-file noisy-paths.txt      # same, from a file
    config-diff a.json b.json --only database                    # compare only a subtree

### Output

| option | |
| --- | --- |
| `-o plain` (default) | `+` added, `-` removed, `~` changed; colored on a terminal |
| `-o json` | `{"equal", "summary", "changes": [{"kind", "path", "segments", "old", "new"}]}` |
| `-o markdown` | a table for pull request comments |
| `--color auto\|always\|never` | `NO_COLOR` turns color off, `FORCE_COLOR` forces it, `TERM=dumb` disables it |
| `--summary` | end plain output with `3 differences (1 added, 2 changed)` |
| `-q`, `--quiet` | no output, only the exit status |

### Secrets

Diffs of `.env` files end up in chat and pull requests. `--redact PATH` hides the values at
matching paths. `--redact-secrets` hides values of keys named like `password`, `secret`,
`token`, `api_key`, `credential` and the password in URLs (`postgres://user:***@host/db`).
Changes are still reported, without the values. Ignored paths are also removed from values
that are reported whole, so `--ignore '**.password'` cannot leak through an "added" section.

### Directories

    $ config-diff config/staging config/prod --summary
    + only in new: metrics.toml
    === app.yaml ===
    ~ replicas: 2 -> 5
    - only in old: debug.env
    3 of 12 files differ (1 changed, 1 only in old, 1 only in new)

Files with the same relative name are compared; every option applies to all of them.

### Exit status

| code | meaning |
| --- | --- |
| 0 | no differences (or only kinds not listed in `--fail-on`) |
| 1 | differences |
| 2 | usage error, unreadable or invalid input |

`--fail-on removed,changed` lets a CI job accept new keys but fail when keys disappear or
change; additions are still printed.

## About the YAML support

There is no YAML parser in the Python standard library, so config-diff ships a small
hand-written parser for the **subset** of YAML that configuration files use: block
mappings and sequences, single-line flow collections, quoted and plain scalars, literal and
folded block scalars, comments. It follows the YAML 1.2 core schema (`yes`/`no`/`on`/`off`
are strings; mapping keys are always strings).

It never builds arbitrary objects, and it refuses what it does not implement - anchors and
aliases, merge keys, tags, multiple documents, complex keys, multi-line plain or quoted
scalars - with an error that names the line, rather than guessing. If you need those,
convert the file to JSON first (for example `yq -o=json`) and diff that.

See [CHANGELOG.md](CHANGELOG.md) for what changed between versions.

## Development

    python -m unittest discover
