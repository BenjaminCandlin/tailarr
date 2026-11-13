"""Finding the films in the Films folder and remembering them in the database.

Scanning only lists folders and reads file sizes/dates, so it is quick and
never opens or changes the video files. Each film is one folder (the way
Radarr organises films). Video files loose in the Films folder itself and
anything in sub-folders of a film folder (extras, samples) are not listed.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, delete, select

from ..core.db import Setting
from ..core.paths import is_inside
from ..jobs.models import CopyRecord
from .artwork import find_backdrop, find_poster
from .models import Film, FilmFile
from .naming import TEMP_PREFIX, is_tailarr_copy, is_video, parse_film_folder, sort_key

log = logging.getLogger(__name__)

SCAN_STATUS_KEY = "films_scan"
# The film list is refreshed in the background when it is older than this.
STALE_AFTER_SECONDS = 15 * 60

# Folders some NAS systems and file systems create; never films.
_SYSTEM_FOLDERS = {"@eadir", "#recycle", "lost+found", "$recycle.bin", "system volume information"}


class LibraryFolderMissingError(RuntimeError):
    pass


@dataclass
class FoundFile:
    name: str
    path: str
    size: int
    mtime: float
    links: int
    # The file it was made from, when Tailarr's records say this file is one of its copies.
    copy_of: str | None = None

    @property
    def is_mkv(self) -> bool:
        return self.name.lower().endswith(".mkv")

    @property
    def is_copy(self) -> bool:
        # By name, or by Tailarr's records: Radarr/Sonarr may rename a copy and drop the
        # "- HDR10" ending, and it must still never be taken for an original.
        return self.copy_of is not None or is_tailarr_copy(self.name)


def recorded_copies(session: Session) -> dict[str, str]:
    """Every copy Tailarr has made: copy path -> the path it was made from."""
    return {record.path: record.source_path for record in session.exec(select(CopyRecord))}


@dataclass
class FoundFilm:
    folder: str
    folder_name: str
    files: list[FoundFile]
    poster: tuple[str, float] | None
    backdrop: tuple[str, float] | None

    @property
    def main_file(self) -> FoundFile:
        originals = [f for f in self.files if not f.is_copy] or self.files
        return max(originals, key=lambda f: (f.is_mkv, f.size))


def _stat_file(entry: os.DirEntry[str]) -> os.stat_result | None:
    try:
        if entry.is_file():
            return entry.stat()
    except OSError:
        pass
    return None


def _scan_folder(
    folder: Path, root: Path, copies: dict[str, str] | None = None
) -> FoundFilm | None:
    try:
        entries = list(os.scandir(folder))
    except OSError as error:
        log.warning("Couldn't read %s: %s", folder, error)
        return None
    names = [e.name for e in entries]
    files: list[FoundFile] = []
    for entry in entries:
        if not is_video(entry.name) or entry.name.startswith(TEMP_PREFIX):
            continue
        if not is_inside(entry.path, root):  # a link pointing outside the Films folder
            continue
        stat = _stat_file(entry)
        if stat is None:
            continue
        files.append(
            FoundFile(
                entry.name,
                entry.path,
                stat.st_size,
                stat.st_mtime,
                stat.st_nlink,
                copy_of=(copies or {}).get(entry.path),
            )
        )
    if not files:
        return None
    files.sort(key=lambda f: (f.is_copy, f.name.casefold()))

    def art(name: str | None) -> tuple[str, float] | None:
        if name is None:
            return None
        path = folder / name
        if not is_inside(path, root):
            return None
        try:
            return str(path), path.stat().st_mtime
        except OSError:
            return None

    film = FoundFilm(str(folder), folder.name, files, poster=None, backdrop=None)
    film.poster = art(find_poster(names, film.main_file.name))
    film.backdrop = art(find_backdrop(names, film.main_file.name))
    return film


def find_films(root: Path, copies: dict[str, str] | None = None) -> list[FoundFilm]:
    """List every film folder in the Films folder."""
    if not root.is_dir():
        raise LibraryFolderMissingError(
            f"Tailarr can't find your Films folder at {root}. Check the Films folder in "
            "Settings, and that the /data share is added to the container."
        )
    films: list[FoundFilm] = []
    for entry in os.scandir(root):
        if entry.name.startswith(".") or entry.name.casefold() in _SYSTEM_FOLDERS:
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        folder = Path(entry.path)
        if not is_inside(folder, root):
            continue
        found = _scan_folder(folder, root, copies)
        if found:
            films.append(found)
    return films


def _save_film(session: Session, item: FoundFilm, film: Film | None) -> Film:
    parsed = parse_film_folder(item.folder_name)
    main = item.main_file
    year = parsed.year
    if year is None:
        # e.g. folder "1917" holding "1917 (2019) Bluray-2160p.mkv"
        year = parse_film_folder(Path(main.name).stem).year
    film = film or Film(folder=item.folder, folder_name="", title="", sort_title="")
    film.folder_name = item.folder_name
    film.title = parsed.title
    film.sort_title = sort_key(parsed.title)
    film.year = year
    film.tmdb_id = parsed.tmdb_id
    film.imdb_id = parsed.imdb_id
    film.poster_path, film.poster_mtime = item.poster or (None, None)
    film.backdrop_path, film.backdrop_mtime = item.backdrop or (None, None)
    film.main_file = main.name
    film.size = sum(f.size for f in item.files)
    film.added_at = main.mtime
    film.file_count = len(item.files)
    session.add(film)
    session.flush()
    session.exec(delete(FilmFile).where(FilmFile.film_id == film.id))  # type: ignore[arg-type]
    for f in item.files:
        session.add(
            FilmFile(
                film_id=film.id,  # type: ignore[arg-type]
                name=f.name,
                path=f.path,
                size=f.size,
                mtime=f.mtime,
                is_mkv=f.is_mkv,
                is_copy=f.is_copy,
                links=f.links,
            )
        )
    return film


def save_films(session: Session, found: list[FoundFilm]) -> int:
    """Bring the database in line with what's on disk. Returns the number of films."""
    existing = {film.folder: film for film in session.exec(select(Film)).all()}
    seen: set[str] = set()
    for item in found:
        seen.add(item.folder)
        _save_film(session, item, existing.get(item.folder))
    # Films that are gone, or that belong to a previous Films folder setting.
    for folder, film in existing.items():
        if folder not in seen:
            session.exec(delete(FilmFile).where(FilmFile.film_id == film.id))  # type: ignore[arg-type]
            session.delete(film)
    session.commit()
    return len(found)


def rescan_film_folder(session: Session, folder: str, root: Path) -> Film | None:
    """Update one film after Tailarr added, replaced or removed a file in its folder.

    Much quicker than a full scan. Returns None if the folder no longer holds a film.
    """
    existing = session.exec(select(Film).where(Film.folder == folder)).first()
    found = (
        _scan_folder(Path(folder), root, recorded_copies(session))
        if is_inside(folder, root)
        else None
    )
    if found is None:
        if existing is not None:
            session.exec(delete(FilmFile).where(FilmFile.film_id == existing.id))  # type: ignore[arg-type]
            session.delete(existing)
            session.commit()
        return None
    film = _save_film(session, found, existing)
    session.commit()
    session.refresh(film)
    return film


@dataclass
class ScanStatus:
    running: bool = False
    started_at: float | None = None
    finished_at: float | None = None
    root: str | None = None
    film_count: int | None = None
    error: str | None = None


class LibraryScanner:
    """Runs one scan at a time in the background and remembers how the last one went.

    Subclasses say which setting key holds the status and how to find and save items.
    """

    status_key = ""
    label = "library"
    missing_message = "Tailarr couldn't read your library folder ({error})."

    def __init__(
        self,
        engine: Engine,
        root: Callable[[], Path],
        on_scanned: Callable[[], object] | None = None,
    ) -> None:
        self._engine = engine
        self._films_root = root
        self._on_scanned = on_scanned  # called after each successful scan
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None

    # -- status ---------------------------------------------------------------
    def status(self) -> ScanStatus:
        with Session(self._engine) as session:
            row = session.get(Setting, self.status_key)
        saved = json.loads(row.value) if row else {}
        status = ScanStatus(**{k: v for k, v in saved.items() if k in ScanStatus.__annotations__})
        with self._lock:
            status.running = self._running
            if self._running:
                status.started_at = self._started_at
        return status

    def _save_status(self, status: ScanStatus) -> None:
        data = asdict(status)
        data["running"] = False
        with Session(self._engine) as session:
            session.merge(Setting(key=self.status_key, value=json.dumps(data)))
            session.commit()

    def is_stale(self) -> bool:
        status = self.status()
        if status.running:
            return False
        if status.finished_at is None or status.root != str(self._films_root()):
            return True
        return time.time() - status.finished_at > STALE_AFTER_SECONDS

    # -- scanning -------------------------------------------------------------
    def run(self) -> ScanStatus:
        """Scan now, in this thread. If a scan is already running, wait for it instead."""
        with self._lock:
            if self._running:
                thread = self._thread
            else:
                thread = None
                self._running = True
                self._started_at = time.time()
        if thread is not None:
            thread.join()
            return self.status()
        try:
            return self._scan()
        finally:
            with self._lock:
                self._running = False

    def start(self) -> bool:
        """Start a scan in the background. Returns False if one is already running."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._started_at = time.time()
            self._thread = threading.Thread(
                target=self._background, name=f"{self.label}-scan", daemon=True
            )
            self._thread.start()
        return True

    def start_if_stale(self) -> bool:
        return self.is_stale() and self.start()

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _background(self) -> None:
        try:
            self._scan()
        except Exception:  # never let a scan crash the app
            log.exception("%s scan failed", self.label)
        finally:
            with self._lock:
                self._running = False

    def find_and_save(self, session: Session, root: Path) -> int:
        raise NotImplementedError

    def _scan(self) -> ScanStatus:
        root = Path(self._films_root())
        status = ScanStatus(started_at=self._started_at, root=str(root))
        try:
            with Session(self._engine) as session:
                status.film_count = self.find_and_save(session, root)
        except LibraryFolderMissingError as error:
            status.error = str(error)
        except OSError as error:
            status.error = self.missing_message.format(error=error.strerror or error)
        status.finished_at = time.time()
        self._save_status(status)
        log.info(
            "%s scan of %s: %s found, error=%s", self.label, root, status.film_count, status.error
        )
        if status.error is None and self._on_scanned is not None:
            self._on_scanned()
        return status


class FilmScanner(LibraryScanner):
    status_key = SCAN_STATUS_KEY
    label = "film"
    missing_message = "Tailarr couldn't read your Films folder ({error})."

    def find_and_save(self, session: Session, root: Path) -> int:
        return save_films(session, find_films(root, recorded_copies(session)))
