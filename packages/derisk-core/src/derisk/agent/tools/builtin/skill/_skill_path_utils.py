"""Shared helpers for resolving a skill directory from a skill name/code.

The canonical skill identifier is the bare, hyphen-normalized name (no random or
repo suffix), which is also the on-disk directory name. These helpers tolerate
callers passing a raw name, a normalized code, or a legacy suffixed code, and try
the matching directory under a base skill directory.

This module is intentionally dependency-free (no derisk-serve import) so the
builtin skill tools stay usable in environments without the serve package.
"""

import os
import re
from typing import Optional


def normalize_skill_name(name: str) -> str:
    """Normalize a skill name into its canonical code / directory name.

    Mirrors ``derisk_serve.skill.service.service.normalize_skill_name`` so the
    tool layer and the service layer agree on the identifier.
    """
    name = (name or "unnamed").lower()
    name = re.sub(r"[^a-z0-9-]", "-", name).strip("-")
    return name or "unnamed"


def resolve_local_skill_dir(base_skill_dir: str, skill_name: str) -> Optional[str]:
    """Resolve an existing skill directory under ``base_skill_dir`` on the local FS.

    Tries, in order: exact name, normalized name, then a single ``{name}-*`` glob
    match (for un-migrated legacy directories with a hash suffix). Returns the
    first existing directory, or None if nothing matches.
    """
    if not base_skill_dir:
        return None

    candidates = [skill_name, normalize_skill_name(skill_name)]
    for cand in candidates:
        if not cand:
            continue
        path = os.path.join(base_skill_dir, cand)
        if os.path.isdir(path):
            return path

    # Legacy fallback: exactly one directory named "{name}-<suffix>"
    try:
        prefix = normalize_skill_name(skill_name) + "-"
        matches = [
            entry.path
            for entry in os.scandir(base_skill_dir)
            if entry.is_dir() and entry.name.startswith(prefix)
        ]
        if len(matches) == 1:
            return matches[0]
    except OSError:
        pass

    return None
