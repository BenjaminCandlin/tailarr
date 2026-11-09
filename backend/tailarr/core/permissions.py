"""Unraid-friendly file permissions.

Most programs respect the container's UMASK automatically. A few (such as
SQLite) choose their own permissions, so files they create are fixed up here.
"""

from __future__ import annotations

import os
from pathlib import Path

from .system import current_umask


def file_mode() -> int:
    return 0o666 & ~current_umask()


def dir_mode() -> int:
    return 0o777 & ~current_umask()


def create_file(path: Path) -> None:
    """Create an empty file (if missing) with permissions that follow UMASK."""
    if path.exists():
        return
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, file_mode())
    os.close(fd)
    os.chmod(path, file_mode())  # os.open's mode is filtered by umask; make it exact


def apply_umask(path: Path) -> None:
    """Give an existing file or folder the permissions UMASK asks for."""
    os.chmod(path, dir_mode() if path.is_dir() else file_mode())
