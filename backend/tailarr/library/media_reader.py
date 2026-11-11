"""Reading the tracks and HDR information of every film file, and remembering it.

After each library scan a background reader goes through every video file
whose information isn't known yet (or whose size or date has changed), one
file at a time so the server isn't overloaded. Opening a film's page reads its
files straight away if the background reader hasn't got to them yet.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import defer
from sqlmodel import Session, col, select

from ..core.paths import is_inside
from ..media.probe import MediaDetails, ReadError, describe, read_file
from .models import Film, FilmFile, MediaRecord

log = logging.getLogger(__name__)

# Bump when the summary columns of MediaRecord are worked out differently; they are
# then recalculated from the stored tool output (no files are read again).
SUMMARY_VERSION = 1


def _apply_summary(record: MediaRecord) -> None:
    record.summary_version = SUMMARY_VERSION
    if record.raw is None:
        record.hdr, record.dv_profile, record.resolution = "", None, None
        return
    details = describe(json.loads(record.raw))
    record.hdr = ",".join(details.hdr.formats)
    record.dv_profile = details.hdr.dv_label
    record.resolution = details.resolution


def is_current(record: MediaRecord | None, size: int, mtime: float) -> bool:
    return record is not None and record.size == size and abs(record.mtime - mtime) < 1e-3


def read_and_store(session: Session, path: str, size: int, mtime: float) -> MediaRecord:
    """Read one file with the tools and save the result (or the reason it failed)."""
    record = MediaRecord(path=path, size=size, mtime=mtime, read_at=time.time())
    try:
        record.raw = json.dumps(read_file(path), separators=(",", ":"))
    except ReadError as error:
        record.error, record.error_details = error.message, error.details
    _apply_summary(record)
    # Insert or replace in one step: the background reader and a page visit may read
    # the same file at the same moment.
    values = record.model_dump()
    statement = sqlite_insert(MediaRecord).values(**values)
    statement = statement.on_conflict_do_update(index_elements=["path"], set_=values)
    session.exec(statement)  # type: ignore[call-overload]
    session.commit()
    saved = session.get(MediaRecord, path, populate_existing=True)
    assert saved is not None
    return saved


def details_of(record: MediaRecord) -> MediaDetails | None:
    return describe(json.loads(record.raw)) if record.raw else None


@dataclass
class ReaderStatus:
    running: bool = False
    done: int = 0
    total: int = 0


class MediaReader:
    """Reads files in the background, one at a time, and on request for a single file."""

    def __init__(self, engine: Engine, films_root: Callable[[], Path]) -> None:
        self._engine = engine
        self._films_root = films_root
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._again = False
        self._stop = threading.Event()
        self._done = 0
        self._total = 0

    # -- single files ----------------------------------------------------------
    def get(self, session: Session, path: str, *, refresh: bool = False) -> MediaRecord:
        """The information for one file, reading it now if it isn't known or is out of date."""
        stat = os.stat(path)
        record = session.get(MediaRecord, path)
        if not refresh and is_current(record, stat.st_size, stat.st_mtime):
            assert record is not None
            if record.summary_version != SUMMARY_VERSION:
                _apply_summary(record)
                session.add(record)
                session.commit()
            return record
        return read_and_store(session, path, stat.st_size, stat.st_mtime)

    def file_changed(self, path: str) -> None:
        """Tailarr has just changed this file: update the library's record of it and read it.

        Without this the film page would show the file as "not read yet" until the next
        library scan, because its size or date no longer match what the scan saw.
        """
        stat = os.stat(path)
        with Session(self._engine) as session:
            for row in session.exec(select(FilmFile).where(FilmFile.path == path)).all():
                row.size, row.mtime, row.links = stat.st_size, stat.st_mtime, stat.st_nlink
                session.add(row)
                film = session.get(Film, row.film_id)
                if film is not None:
                    siblings = session.exec(
                        select(FilmFile).where(FilmFile.film_id == row.film_id)
                    ).all()
                    film.size = sum(f.size for f in siblings)
                    session.add(film)
            session.commit()
            read_and_store(session, path, stat.st_size, stat.st_mtime)

    # -- status -------------------------------------------------------------------
    def status(self) -> ReaderStatus:
        with self._lock:
            return ReaderStatus(self._running, self._done, self._total)

    # -- background -------------------------------------------------------------
    def start(self) -> bool:
        """Read any files that need it, in the background. Returns False if already running."""
        with self._lock:
            if self._running:
                self._again = True  # a new scan finished: look again when this round ends
                return False
            self._running = True
            self._again = False
            self._stop.clear()
            self._thread = threading.Thread(target=self._background, name="media-read", daemon=True)
            self._thread.start()
        return True

    def run(self) -> None:
        """Do a full round now, in this thread (waits for a background round first)."""
        self.wait()
        with self._lock:
            self._running = True
            self._again = False
        try:
            self._round()
        finally:
            with self._lock:
                self._running = False

    def stop(self, timeout: float | None = 5) -> None:
        self._stop.set()
        self.wait(timeout)

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _background(self) -> None:
        try:
            while True:
                self._round()
                with self._lock:
                    if not self._again or self._stop.is_set():
                        break
                    self._again = False
        except Exception:  # never let reading crash the app
            log.exception("Reading film details failed")
        finally:
            with self._lock:
                self._running = False

    def _todo(self, session: Session) -> list[str]:
        query = select(MediaRecord).options(defer(MediaRecord.raw))  # type: ignore[arg-type]
        records = {r.path: r for r in session.exec(query).all()}
        todo = []
        rows = session.exec(select(FilmFile).order_by(col(FilmFile.mtime).desc())).all()
        for f in rows:
            record = records.get(f.path)
            if not is_current(record, f.size, f.mtime):
                todo.append(f.path)
            elif record is not None and record.summary_version != SUMMARY_VERSION:
                _apply_summary(record)
                session.add(record)
        session.commit()
        return todo

    def _round(self) -> None:
        with Session(self._engine) as session:
            self._clean_up(session)
            todo = self._todo(session)
            with self._lock:
                self._done, self._total = 0, len(todo)
            for path in todo:
                if self._stop.is_set():
                    return
                try:
                    stat = os.stat(path)
                except OSError:
                    continue  # gone since the scan; the next scan will notice
                record = session.get(MediaRecord, path)
                if not is_current(record, stat.st_size, stat.st_mtime):
                    read_and_store(session, path, stat.st_size, stat.st_mtime)
                with self._lock:
                    self._done += 1
        log.info("Read details of %s files", len(todo))

    def _clean_up(self, session: Session) -> None:
        """Forget files in the Films folder that the library no longer has."""
        root = self._films_root()
        known = set(session.exec(select(FilmFile.path)).all())
        if not known:
            return  # e.g. the array is stopped: keep everything for when it's back
        for record in session.exec(select(MediaRecord)).all():
            if record.path not in known and is_inside(record.path, root):
                session.delete(record)
        session.commit()
