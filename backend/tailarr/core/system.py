"""Facts about the running container: user, permissions and folders."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def current_umask() -> int:
    # The only way to read the umask is to set it and put it back.
    mask = os.umask(0)
    os.umask(mask)
    return mask


@dataclass(frozen=True)
class FolderStatus:
    key: str
    label: str
    purpose: str
    path: str
    exists: bool
    writable: bool
    required: bool

    @property
    def ok(self) -> bool:
        return (self.exists and self.writable) or (not self.required and not self.exists)


def check_folder(key: str, label: str, purpose: str, path: Path, required: bool) -> FolderStatus:
    exists = path.is_dir()
    writable = exists and os.access(path, os.W_OK | os.X_OK)
    return FolderStatus(key, label, purpose, str(path), exists, writable, required)
