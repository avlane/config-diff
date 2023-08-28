# config-diff

A semantic diff for configuration files. Instead of comparing lines it compares
the parsed values, so reordered keys, different indentation and comments do not
show up as changes.

Work in progress. Planned: JSON, INI and `.env` files, ignore paths, lists
compared by key, colored/plain/JSON output and exit codes that work in CI.

    config-diff old.json new.json

Exit status: 0 if the files are equivalent, 1 if they differ, 2 on errors.
Supported formats: JSON (`.json`) and INI (`.ini`, `.cfg`).
