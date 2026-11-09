"""Path safety and path mapping.

Tailarr may only look at or change files inside the configured Films and TV
folders (and use the work folder for temporary files). The rest of the data
share, such as the downloads folders, is off limits.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath


class PathNotAllowedError(ValueError):
    """Raised when a path is outside the folders Tailarr may use."""


def _real(path: str | os.PathLike[str]) -> str:
    # realpath resolves "..", "." and symlinks, even for paths that don't exist yet.
    return os.path.realpath(os.fspath(path))


def is_inside(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> bool:
    real_path, real_root = _real(path), _real(root)
    try:
        return os.path.commonpath([real_path, real_root]) == real_root
    except ValueError:
        return False


def ensure_inside(path: str | os.PathLike[str], roots: Iterable[str | os.PathLike[str]]) -> str:
    """Return the resolved path, or raise if it is outside every allowed folder."""
    roots = list(roots)
    for root in roots:
        if is_inside(path, root):
            return _real(path)
    raise PathNotAllowedError(
        f"Tailarr isn't allowed to use '{path}'. It can only use files inside: "
        + ", ".join(str(r) for r in roots)
    )


@dataclass(frozen=True)
class PathMapping:
    """'Radarr/Sonarr see this path' -> 'Tailarr sees this path'."""

    remote: str
    local: str


def map_remote_path(path: str, mappings: Iterable[PathMapping]) -> str:
    """Translate a path reported by Radarr/Sonarr into the path Tailarr sees.

    The longest matching folder prefix wins. Matching is per folder, so a mapping
    for '/movies' doesn't affect '/movies-4k'. Paths with no match are returned
    unchanged (with the shared /data mount they normally already match).
    """
    target = PurePosixPath(path)
    best: PathMapping | None = None
    best_len = -1
    for mapping in mappings:
        remote = PurePosixPath(mapping.remote)
        if target == remote or remote in target.parents:
            length = len(remote.parts)
            if length > best_len:
                best, best_len = mapping, length
    if best is None:
        return path
    relative = target.relative_to(PurePosixPath(best.remote))
    mapped = PurePosixPath(best.local) / relative
    return str(mapped)
