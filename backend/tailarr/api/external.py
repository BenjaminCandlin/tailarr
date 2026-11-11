"""Pictures saved from Radarr/Sonarr, used when a folder has no artwork of its own."""

from __future__ import annotations

import os
from pathlib import Path

from ..connections.models import ExternalInfo
from ..core.config import AppConfig
from ..core.paths import is_inside


def artwork_version(path: str) -> int:
    try:
        return int(os.stat(path).st_mtime)
    except OSError:
        return 0


def arr_artwork(info: ExternalInfo | None, kind: str, config: AppConfig) -> Path | None:
    """The cached Radarr/Sonarr poster or backdrop, if there is one (only from the cache)."""
    if info is None:
        return None
    stored = info.poster_file if kind == "poster" else info.backdrop_file
    cache = config.config_dir / "cache" / "arr"
    if not stored or not is_inside(stored, cache) or not Path(stored).is_file():
        return None
    return Path(stored)
