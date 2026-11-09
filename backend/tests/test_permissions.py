from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tailarr.core.db import make_engine
from tailarr.core.permissions import apply_umask, create_file


@pytest.fixture
def unraid_umask():
    old = os.umask(0o002)
    try:
        yield
    finally:
        os.umask(old)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_database_follows_unraid_umask(tmp_path: Path, unraid_umask) -> None:
    db = tmp_path / "config" / "tailarr.db"
    make_engine(db)
    assert _mode(db) == 0o664


def test_create_file_and_apply_umask(tmp_path: Path, unraid_umask) -> None:
    f = tmp_path / "new.mkv"
    create_file(f)
    assert _mode(f) == 0o664
    os.chmod(f, 0o600)
    apply_umask(f)
    assert _mode(f) == 0o664
    d = tmp_path / "folder"
    d.mkdir(mode=0o700)
    apply_umask(d)
    assert _mode(d) == 0o775


def test_existing_file_is_left_alone(tmp_path: Path, unraid_umask) -> None:
    f = tmp_path / "existing"
    f.write_text("keep me")
    os.chmod(f, 0o640)
    create_file(f)
    assert f.read_text() == "keep me"
    assert _mode(f) == 0o640
