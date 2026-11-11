"""The recycle folder: where replaced originals wait before being deleted.

When the owner replaces an original file with a copy, the original isn't deleted
straight away: it's moved into a hidden ``.tailarr-recycle`` folder inside the
film's own folder and deleted after the keep period (30 days by default).

Inside the film's folder because moving a file within the same folder tree is
an instant rename on the same disk (no copying of 50 GB films between Unraid
disks). Hidden (starting with a dot) because Plex, Radarr and Tailarr's own
scans skip hidden folders, so nobody mistakes it for a second version.

Only files Tailarr itself put in a recycle folder (recorded in the database)
are ever deleted.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from ..core.paths import is_inside
from ..core.permissions import apply_umask
from ..core.settings_store import get_recycle_settings
from .models import RecycledFile

log = logging.getLogger(__name__)

RECYCLE_FOLDER = ".tailarr-recycle"
CLEAN_EVERY_SECONDS = 6 * 3600


def recycle_path(original: str | os.PathLike[str]) -> Path:
    """Where `original` goes: the recycle folder next to it, never clashing with a file there."""
    original = Path(original)
    folder = original.parent / RECYCLE_FOLDER
    target = folder / original.name
    number = 2
    while target.exists():
        target = folder / f"{original.stem} ({number}){original.suffix}"
        number += 1
    return target


def move_to_recycle(session: Session, original: str, job_id: int | None = None) -> RecycledFile:
    """Move a file into its recycle folder (an instant rename) and remember it."""
    target = recycle_path(original)
    if not target.parent.exists():
        target.parent.mkdir()
        apply_umask(target.parent)
    size = os.stat(original).st_size
    os.rename(original, target)
    record = RecycledFile(
        path=str(target),
        original_path=original,
        size=size,
        recycled_at=time.time(),
        job_id=job_id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _is_ours(path: str, roots: list[str]) -> bool:
    return Path(path).parent.name == RECYCLE_FOLDER and any(is_inside(path, r) for r in roots)


def clean_recycle(engine: Engine, roots: list[str], now: float | None = None) -> int:
    """Delete recycled files older than the keep period. Returns how many were deleted."""
    now = time.time() if now is None else now
    removed = 0
    with Session(engine) as session:
        keep_days = get_recycle_settings(session).keep_days
        cutoff = now - keep_days * 86400
        old = session.exec(select(RecycledFile).where(col(RecycledFile.recycled_at) < cutoff)).all()
        for record in old:
            if not _is_ours(record.path, roots):
                # e.g. the Films folder setting changed: leave the file alone, keep the record.
                continue
            try:
                os.unlink(record.path)
            except FileNotFoundError:
                pass  # deleted by hand already
            except OSError as error:
                log.warning("Couldn't delete recycled file %s: %s", record.path, error)
                continue
            removed += 1
            session.delete(record)
            with contextlib.suppress(OSError):
                Path(record.path).parent.rmdir()  # only succeeds once the folder is empty
        session.commit()
    if removed:
        log.info("Deleted %s old file(s) from recycle folders", removed)
    return removed


class RecycleCleaner:
    """Empties old files from the recycle folders at start-up and every few hours."""

    def __init__(self, engine: Engine, roots: Callable[[], list[str]]) -> None:
        self._engine = engine
        self._roots = roots
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="recycle-clean", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                clean_recycle(self._engine, self._roots())
            except Exception:  # never let clean-up crash the app
                log.exception("Cleaning the recycle folders failed")
            self._stop.wait(CLEAN_EVERY_SECONDS)
