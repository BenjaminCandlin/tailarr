"""Free disk space checks, so a job never fills a disk halfway through."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Always leave this much free on top of what a job needs (logs, Plex, other containers).
SAFETY_MARGIN = 1024**3  # 1 GB


class NotEnoughSpaceError(Exception):
    def __init__(self, message: str, needed: int, free: int) -> None:
        super().__init__(message)
        self.message = message
        self.needed = needed
        self.free = free


def format_size(size: float) -> str:
    """Sizes the way people read them: '48 GB', '1.2 TB', '730 MB'."""
    units = ("bytes", "KB", "MB", "GB", "TB", "PB")
    value = float(size)
    for unit in units:
        if value < 1000 or unit == units[-1]:
            if unit == "bytes":
                return f"{int(value)} bytes"
            return f"{value:.1f} {unit}" if value < 10 else f"{value:.0f} {unit}"
        value /= 1000
    raise AssertionError("unreachable")


def free_space(folder: str | os.PathLike[str]) -> int:
    """Free bytes on the disk that holds `folder` (or its nearest existing parent)."""
    path = Path(folder)
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path).free


def check_free_space(
    folder: str | os.PathLike[str], needed: int, *, margin: int = SAFETY_MARGIN
) -> int:
    """Raise NotEnoughSpaceError unless `needed` bytes plus the margin are free.

    Returns the free space, for the summary shown before a job starts.
    """
    free = free_space(folder)
    total = needed + margin
    if free < total:
        raise NotEnoughSpaceError(
            f"Not enough free space on the disk: needs {format_size(total)}, "
            f"{format_size(free)} free. Free up some space and try again.",
            needed=total,
            free=free,
        )
    return free
