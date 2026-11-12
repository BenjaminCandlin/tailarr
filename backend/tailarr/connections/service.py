"""Using the connections: test them, learn titles/posters, and tell the apps about changes.

* **Sync**: Radarr's films and Sonarr's shows are matched to Tailarr's folders (after path
  mapping). Their titles and years are used on the pages, and their posters/backdrops are
  used when a folder has no artwork of its own. Runs after the settings are saved, after
  library scans (at most every few hours), and on request.
* **After a job**: Plex is asked to look at the changed folder again (new copies show up
  as versions); Radarr/Sonarr are asked to rescan only when an *original* changed (the
  owner's choice: they ignore extra copies).

Problems never stop a job: they're written to the activity log.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from ..core.config import AppConfig
from ..core.paths import PathMapping, is_inside, map_remote_path
from ..core.permissions import apply_umask, dir_mode
from ..core.settings_store import get_library_settings
from ..jobs.engine import JobType
from ..jobs.models import Job
from ..library.models import Film, Show
from ..library.naming import sort_key
from ..library.tv_scanner import show_folder_of
from .clients import NAMES, ArrClient, ConnectionProblem, PlexClient
from .models import ActivityEntry, ExternalInfo
from .settings import ConnectionSettings, ServiceSettings, get_connections

log = logging.getLogger(__name__)

SYNC_EVERY_SECONDS = 6 * 3600
POSTER_WIDTH = 600
BACKDROP_WIDTH = 1280
ACTIVITY_KEEP = 2000  # newest entries kept


def record_activity(
    engine: Engine,
    source: str,
    kind: str,
    message: str,
    *,
    ok: bool = True,
    details: str | None = None,
    path: str | None = None,
    job_id: int | None = None,
    rule_id: int | None = None,
) -> None:
    with Session(engine) as session:
        session.add(
            ActivityEntry(
                at=time.time(),
                source=source,
                kind=kind,
                message=message,
                ok=ok,
                details=details,
                path=path,
                job_id=job_id,
                rule_id=rule_id,
            )
        )
        session.commit()
        count = len(session.exec(select(ActivityEntry.id)).all())
        if count > ACTIVITY_KEEP:
            old = session.exec(
                select(ActivityEntry.id)
                .order_by(col(ActivityEntry.at))
                .limit(count - ACTIVITY_KEEP)
            ).all()
            session.exec(delete(ActivityEntry).where(col(ActivityEntry.id).in_(old)))  # type: ignore[arg-type]
            session.commit()


@dataclass
class SyncStatus:
    running: bool = False
    finished_at: float | None = None
    films: int | None = None
    shows: int | None = None
    errors: dict[str, str] | None = None


class Connections:
    def __init__(
        self,
        engine: Engine,
        config: AppConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        on_synced: Callable[[], None] | None = None,
    ) -> None:
        self._engine = engine
        self._config = config
        self.transport = transport  # tests answer instead of real servers
        self._on_synced = on_synced
        self._lock = threading.Lock()
        self._sync_lock = threading.Lock()  # one sync at a time (background or on request)
        self._status = SyncStatus()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- settings and clients ------------------------------------------------------------
    def settings(self) -> ConnectionSettings:
        with Session(self._engine) as session:
            return get_connections(session)

    def mappings(self) -> list[PathMapping]:
        with Session(self._engine) as session:
            library = get_library_settings(session, self._config)
        return [m.to_mapping() for m in library.path_mappings]

    def arr(self, service: str, settings: ServiceSettings | None = None) -> ArrClient:
        s = settings or getattr(self.settings(), service)
        return ArrClient(service, s.url, s.api_key, transport=self.transport)

    def plex(self, settings: ServiceSettings | None = None) -> PlexClient:
        s = settings or self.settings().plex
        return PlexClient(s.url, s.api_key, transport=self.transport)

    def test(self, service: str, settings: ServiceSettings) -> str:
        """Try a connection. Returns a plain-English success line; raises ConnectionProblem."""
        if not settings.url:
            raise ConnectionProblem(f"Fill in {NAMES[service]}'s address first.")
        if not settings.api_key:
            what = "token" if service == "plex" else "API key"
            raise ConnectionProblem(f"Fill in {NAMES[service]}'s {what} first.")
        if service == "plex":
            info = self.plex(settings).status()
            return f"Connected to Plex{' ' + info['version'] if info.get('version') else ''}."
        client = self.arr(service, settings)
        info = client.status()
        version = info.get("version", "")
        count = len(client.items())
        things = "films" if service == "radarr" else "shows"
        return f"Connected to {NAMES[service]} {version}. It has {count} {things}.".replace(
            "  ", " "
        )

    # -- sync: titles and posters --------------------------------------------------------
    def status(self) -> SyncStatus:
        with self._lock:
            return SyncStatus(**vars(self._status))

    def start_sync(self) -> bool:
        with self._lock:
            if self._status.running:
                return False
            self._status.running = True
        threading.Thread(target=self._sync_background, name="arr-sync", daemon=True).start()
        return True

    def sync_if_stale(self) -> bool:
        status = self.status()
        if status.running:
            return False
        settings = self.settings()
        if not (settings.radarr.configured or settings.sonarr.configured):
            return False
        if status.finished_at and time.time() - status.finished_at < SYNC_EVERY_SECONDS:
            return False
        return self.start_sync()

    def _sync_background(self) -> None:
        try:
            self.sync()
        except Exception:
            log.exception("Sync with Radarr/Sonarr failed")
            with self._lock:
                self._status.running = False

    def sync(self) -> SyncStatus:
        """Learn titles, years and artwork from Radarr and Sonarr (in this thread)."""
        with self._sync_lock:
            return self._sync()

    def _sync(self) -> SyncStatus:
        with self._lock:
            self._status.running = True
        settings = self.settings()
        errors: dict[str, str] = {}
        counts: dict[str, int | None] = {"radarr": None, "sonarr": None}
        for service in ("radarr", "sonarr"):
            service_settings: ServiceSettings = getattr(settings, service)
            if not service_settings.configured:
                with Session(self._engine) as session:
                    session.exec(delete(ExternalInfo).where(ExternalInfo.source == service))  # type: ignore[arg-type]
                    session.commit()
                continue
            try:
                counts[service] = self._sync_service(service, self.arr(service, service_settings))
            except ConnectionProblem as problem:
                errors[service] = problem.message
                record_activity(
                    self._engine,
                    service,
                    "sync",
                    f"Couldn't get titles and posters from {NAMES[service]}: {problem.message}",
                    ok=False,
                    details=problem.details,
                )
        with self._lock:
            self._status = SyncStatus(
                running=False,
                finished_at=time.time(),
                films=counts["radarr"],
                shows=counts["sonarr"],
                errors=errors or None,
            )
        if self._on_synced is not None:
            self._on_synced()
        return self.status()

    def _sync_service(self, service: str, client: ArrClient) -> int:
        items = client.items()
        mappings = self.mappings()
        with Session(self._engine) as session:
            library = get_library_settings(session, self._config)
            root = library.movies_dir if service == "radarr" else library.tv_dir
            if service == "radarr":
                local_art = {
                    f.folder: (f.poster_path, f.backdrop_path)
                    for f in session.exec(select(Film)).all()
                }
            else:
                local_art = {
                    s.folder: (s.poster_path, s.backdrop_path)
                    for s in session.exec(select(Show)).all()
                }
            existing = {
                e.folder: e
                for e in session.exec(select(ExternalInfo).where(ExternalInfo.source == service))
            }
            seen: set[str] = set()
            for item in items:
                remote = item.get("path")
                if not remote or "id" not in item:
                    continue
                folder = os.path.normpath(map_remote_path(remote, mappings))
                if not is_inside(folder, root):
                    continue
                seen.add(folder)
                info = existing.get(folder) or ExternalInfo(
                    folder=folder, source=service, arr_id=item["id"], title=""
                )
                info.arr_id = int(item["id"])
                info.title = item.get("title") or Path(folder).name
                info.year = item.get("year") or None
                art = local_art.get(folder)
                if art is not None:  # only fetch pictures for folders Tailarr lists
                    poster, backdrop = art
                    if not poster:
                        info.poster_file = (
                            self._cache_image(client, service, item, "poster", POSTER_WIDTH)
                            or info.poster_file
                        )
                    if not backdrop:
                        info.backdrop_file = (
                            self._cache_image(client, service, item, "fanart", BACKDROP_WIDTH)
                            or info.backdrop_file
                        )
                info.synced_at = time.time()
                session.add(info)
            for folder, info in existing.items():
                if folder not in seen:
                    session.delete(info)
            session.commit()
        return len(seen)

    def _cache_dir(self) -> Path:
        folder = self._config.config_dir / "cache" / "arr"
        for path in (folder.parent, folder):
            if not path.is_dir():
                path.mkdir(mode=dir_mode(), parents=True, exist_ok=True)
                apply_umask(path)
        return folder

    def _cache_image(
        self, client: ArrClient, service: str, item: dict[str, Any], kind: str, width: int
    ) -> str | None:
        image = next((i for i in item.get("images") or [] if i.get("coverType") == kind), None)
        if image is None:
            return None
        url = image.get("url") or ""
        key = hashlib.sha1(f"{service}|{item['id']}|{kind}|{url}".encode()).hexdigest()[:16]
        target = self._cache_dir() / f"{service}-{item['id']}-{kind}-{key}.jpg"
        if target.is_file():
            return str(target)
        try:
            if url.startswith("/"):
                data = client.get_bytes(url)
            else:
                remote = image.get("remoteUrl") or url
                if not remote.startswith("http"):
                    return None
                with httpx.Client(timeout=15, transport=client._transport) as http:
                    data = http.get(remote).raise_for_status().content
            with Image.open(io.BytesIO(data)) as picture:
                picture = ImageOps.exif_transpose(picture)
                picture.thumbnail((width, width * 3))
                temp = target.with_name(f".tmp-{os.getpid()}-{target.name}")
                picture.convert("RGB").save(temp, "JPEG", quality=82, optimize=True)
            apply_umask(temp)
            temp.replace(target)
        except (ConnectionProblem, httpx.HTTPError, OSError, UnidentifiedImageError) as error:
            log.info("No %s for %s %s: %s", kind, service, item.get("id"), error)
            return None
        # Older pictures of the same item aren't needed any more.
        for old in target.parent.glob(f"{service}-{item['id']}-{kind}-*.jpg"):
            if old != target:
                old.unlink(missing_ok=True)
        return str(target)

    # -- after a job -----------------------------------------------------------------------
    def after_job(self, job: Job, job_type: JobType) -> None:
        """A job finished successfully: tell Plex (and Radarr/Sonarr if an original changed)."""
        settings = self.settings()
        wants_plex = settings.plex_refresh and settings.plex.configured
        wants_rescan = settings.arr_rescan and job_type.in_place
        if not (wants_plex or wants_rescan):
            return
        threading.Thread(
            target=self._after_job,
            args=(job, wants_plex, wants_rescan),
            name="after-job",
            daemon=True,
        ).start()

    def _after_job(self, job: Job, wants_plex: bool, wants_rescan: bool) -> None:
        try:
            folder = str(Path(job.path).parent)
            if wants_plex:
                self.refresh_plex(folder, job_id=job.id)
            if wants_rescan:
                self.rescan_arr(job.path, job_id=job.id)
        except Exception:  # never let telling other apps break anything
            log.exception("Telling other apps about job %s failed", job.id)

    def refresh_plex(self, folder: str, *, job_id: int | None = None) -> bool:
        settings = self.settings()
        if not settings.plex.configured:
            return False
        client = self.plex(settings.plex)
        mappings = self.mappings()
        with Session(self._engine) as session:
            library = get_library_settings(session, self._config)
        kind = "movie" if is_inside(folder, library.movies_dir) else "show"
        try:
            sections = client.sections()
            target: tuple[str, str] | None = None
            for section in sections:
                for location in section.get("Location") or []:
                    plex_root = location.get("path") or ""
                    local_root = map_remote_path(plex_root, mappings)
                    if plex_root and is_inside(folder, local_root):
                        relative = os.path.relpath(folder, os.path.realpath(local_root))
                        plex_path = str(PurePosixPath(plex_root) / relative)
                        target = (str(section.get("key")), plex_path)
                        break
                if target:
                    break
            if target is not None:
                client.refresh(target[0], target[1])
                message = f"Asked Plex to look at {Path(folder).name} again."
            else:
                same_kind = [s for s in sections if s.get("type") == kind]
                for section in same_kind:
                    client.refresh(str(section.get("key")), None)
                message = (
                    "Plex's folders didn't match Tailarr's, so Plex was asked to scan its whole "
                    f"{'film' if kind == 'movie' else 'TV'} library. A path mapping for Plex "
                    "would make this quicker."
                )
            record_activity(self._engine, "plex", "refresh", message, path=folder, job_id=job_id)
            return True
        except ConnectionProblem as problem:
            record_activity(
                self._engine,
                "plex",
                "refresh",
                f"Couldn't ask Plex to refresh: {problem.message}",
                ok=False,
                details=problem.details,
                path=folder,
                job_id=job_id,
            )
            return False

    def rescan_arr(self, path: str, *, job_id: int | None = None) -> bool:
        settings = self.settings()
        with Session(self._engine) as session:
            library = get_library_settings(session, self._config)
            if is_inside(path, library.movies_dir):
                service, folder = "radarr", str(Path(path).parent)
            else:
                show = show_folder_of(path, Path(library.tv_dir))
                service, folder = "sonarr", str(show) if show else str(Path(path).parent)
            info = session.get(ExternalInfo, folder)
        service_settings: ServiceSettings = getattr(settings, service)
        if not service_settings.configured:
            return False
        if info is None:
            self.sync()
            with Session(self._engine) as session:
                info = session.get(ExternalInfo, folder)
        if info is None:
            record_activity(
                self._engine,
                service,
                "rescan",
                f"{NAMES[service]} doesn't seem to know {Path(folder).name}, so it wasn't asked "
                "to rescan. Check the path mapping if it should.",
                ok=False,
                path=folder,
                job_id=job_id,
            )
            return False
        try:
            self.arr(service, service_settings).rescan(info.arr_id)
        except ConnectionProblem as problem:
            record_activity(
                self._engine,
                service,
                "rescan",
                f"Couldn't ask {NAMES[service]} to rescan {info.title}: {problem.message}",
                ok=False,
                details=problem.details,
                path=folder,
                job_id=job_id,
            )
            return False
        record_activity(
            self._engine,
            service,
            "rescan",
            f"Asked {NAMES[service]} to rescan {info.title}.",
            path=folder,
            job_id=job_id,
        )
        return True

    # -- background --------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="arr-sync-timer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(5):
            try:
                self.sync_if_stale()
            except Exception:
                log.exception("Scheduled sync failed")
            self._stop.wait(SYNC_EVERY_SECONDS / 6)


def external_info(session: Session, folders: list[str] | None = None) -> dict[str, ExternalInfo]:
    query = select(ExternalInfo)
    if folders is not None:
        query = query.where(col(ExternalInfo.folder).in_(folders))
    return {e.folder: e for e in session.exec(query).all()}


def display_title(title: str, info: ExternalInfo | None) -> tuple[str, str]:
    """The title to show and to sort by: Radarr/Sonarr's when known."""
    if info is not None and info.title:
        return info.title, sort_key(info.title)
    return title, sort_key(title)
