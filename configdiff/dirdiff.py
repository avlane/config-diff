"""Compare two directories of configuration files."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .loaders import ConfigError, detect_format

SAME = "same"
DIFFERENT = "different"
ONLY_OLD = "only-old"
ONLY_NEW = "only-new"


@dataclass
class FileResult:
    name: str                 # path relative to the directory, with "/" separators
    status: str
    changes: list = field(default_factory=list)


def list_configs(root):
    """Relative names of all files below *root* whose format can be recognised."""
    names = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            full = os.path.join(dirpath, filename)
            try:
                detect_format(full)
            except ConfigError:
                continue
            names.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(names)


def compare_dirs(old_dir, new_dir, compare):
    """Compare same-named files; compare(old_path, new_path) returns the changes."""
    old_names = set(list_configs(old_dir))
    new_names = set(list_configs(new_dir))
    results = []
    for name in sorted(old_names | new_names):
        if name not in new_names:
            results.append(FileResult(name, ONLY_OLD))
        elif name not in old_names:
            results.append(FileResult(name, ONLY_NEW))
        else:
            changes = compare(os.path.join(old_dir, *name.split("/")),
                              os.path.join(new_dir, *name.split("/")))
            results.append(FileResult(name, DIFFERENT if changes else SAME, changes))
    return results
