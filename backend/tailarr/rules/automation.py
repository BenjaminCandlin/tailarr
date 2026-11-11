"""Running rules by themselves on new and upgraded files.

New files are found in two ways:

* **Radarr/Sonarr webhooks** (preferred): an import or upgrade message names the new file.
* **Folder watching** (optional, off by default, for setups without webhooks): `watchdog`
  notices new files, and because inotify isn't fully reliable on Unraid's `/mnt/user`
  shares the library is also re-scanned regularly; files that appeared since watching
  was switched on count as new.

A file is only handled once it has **finished copying**: its size and date haven't changed
for the settle time (60 s by default) and MKVToolNix can read it. Each enabled rule then
looks at it **once** per version of the file (path + size + date, `RuleRun`). Tailarr's
own copies and temporary files are never picked up, and Tailarr's own changes to a file
are remembered so they don't start rules again.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from ..connections.models import ExternalInfo
from ..connections.service import record_activity
from ..core.config import AppConfig
from ..core.paths import is_inside
from ..core.settings_store import get_library_settings
from ..jobs.engine import JobQueue, JobType
from ..jobs.models import Job
from ..library.media_reader import MediaReader, details_of
from ..library.models import Episode, EpisodeFile, Film, FilmFile, Show
from ..library.naming import TEMP_PREFIX, is_tailarr_copy
from ..library.tv_naming import episode_label
from .engine import Candidate, RuleMatch, plan_for, submit
from .models import Rule, RuleRun
from .settings import AutomationSettings, get_automation

log = logging.getLogger(__name__)

TICK_SECONDS = 5
GIVE_UP_SECONDS = 6 * 3600  # a file still changing after this long is left alone
# Reasons that only mean "already done": not worth an activity log line every time.
_QUIET = ("already exists", "Already set up", "Nothing to remove")


@dataclass
class Pending:
    path: str
    reason: str  # "Radarr import", "Sonarr upgrade", "new file in the Films folder"…
    first_seen: float
    size: int = -1
    mtime: float = -1
    stable_since: float = 0


def is_candidate_name(path: str) -> bool:
    name = Path(path).name
    return (
        name.lower().endswith(".mkv")
        and not name.startswith((".", TEMP_PREFIX))
        and not is_tailarr_copy(name)
        and ".tailarr-recycle" not in Path(path).parts
    )


class AutoRunner:
    def __init__(
        self,
        engine: Engine,
        config: AppConfig,
        reader: MediaReader,
        queue: JobQueue,
        folder_changed: Callable[[str], None],
        start_scans: Callable[[], None],
    ) -> None:
        self._engine = engine
        self._config = config
        self._reader = reader
        self._queue = queue
        self._folder_changed = folder_changed
        self._start_scans = start_scans
        self._lock = threading.Lock()
        self._pending: dict[str, Pending] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer = None
        self._watching: tuple[str, ...] = ()
        self._last_rescan = time.time()

    # -- settings -----------------------------------------------------------------------
    def settings(self) -> AutomationSettings:
        with Session(self._engine) as session:
            return get_automation(session)

    def roots(self) -> tuple[str, str]:
        with Session(self._engine) as session:
            library = get_library_settings(session, self._config)
        return library.movies_dir, library.tv_dir

    # -- finding new files ----------------------------------------------------------------
    def add(self, path: str, reason: str) -> bool:
        """A new or upgraded file to handle once it has finished copying."""
        path = os.path.normpath(path)
        if not is_candidate_name(path) or not any(is_inside(path, r) for r in self.roots()):
            return False
        with self._lock:
            if path not in self._pending:
                self._pending[path] = Pending(path=path, reason=reason, first_seen=time.time())
        return True

    def pending(self) -> list[Pending]:
        with self._lock:
            return list(self._pending.values())

    def webhook_hook(self, service: str, result) -> None:  # noqa: ANN001 (WebhookResult)
        name = "Radarr" if service == "radarr" else "Sonarr"
        for path in result.imported:
            kind = "upgrade" if path in result.upgraded else "import"
            self.add(path, f"{name} {kind}")

    def scanned(self) -> None:
        """After a library scan: with watching on, pick up files that appeared since."""
        settings = self.settings()
        if not settings.watch_folders or settings.watch_since is None:
            return
        with Session(self._engine) as session:
            rows: list[FilmFile | EpisodeFile] = [
                *session.exec(select(FilmFile).where(col(FilmFile.mtime) > settings.watch_since)),
                *session.exec(
                    select(EpisodeFile).where(col(EpisodeFile.mtime) > settings.watch_since)
                ),
            ]
            seen = set(session.exec(select(RuleRun.path)).all())
        for row in rows:
            if not row.is_copy and row.path not in seen:
                self.add(row.path, "new file found by the folder check")

    # -- handling --------------------------------------------------------------------------
    def tick(self, now: float | None = None) -> int:
        """Handle every pending file that has finished copying. Returns how many."""
        now = time.time() if now is None else now
        settle = self.settings().settle_seconds
        ready: list[Pending] = []
        with self._lock:
            for path, item in list(self._pending.items()):
                try:
                    stat = os.stat(path)
                except OSError:
                    if now - item.first_seen > 600:
                        del self._pending[path]  # gone (renamed or deleted meanwhile)
                    continue
                if (stat.st_size, stat.st_mtime) != (item.size, item.mtime):
                    item.size, item.mtime, item.stable_since = stat.st_size, stat.st_mtime, now
                    if settle > 0:
                        continue
                if now - item.stable_since >= settle:
                    ready.append(item)
                    del self._pending[path]
                elif now - item.first_seen > GIVE_UP_SECONDS:
                    del self._pending[path]
                    record_activity(
                        self._engine,
                        "rule",
                        "not-finished",
                        f"{Path(path).name} kept changing for hours, so rules left it alone.",
                        ok=False,
                        path=path,
                    )
        for item in ready:
            try:
                self.process(item.path, item.reason)
            except Exception:  # one file must never stop the others
                log.exception("Automatic rules failed for %s", item.path)
        return len(ready)

    def _candidate(self, session: Session, path: str) -> tuple[Candidate | None, str | None]:
        """The film or episode this file belongs to, read with the tools."""
        movies, tv = self.roots()
        self._folder_changed(str(Path(path).parent))  # make sure the library lists it
        infos = {e.folder: e for e in session.exec(select(ExternalInfo)).all()}
        film_file = session.exec(select(FilmFile).where(FilmFile.path == path)).first()
        if film_file is not None and is_inside(path, movies):
            film = session.get(Film, film_file.film_id)
            if film is None or film.main_file != film_file.name:
                return None, None
            info = infos.get(film.folder)
            title = info.title if info and info.title else film.title
            year = info.year if info and info.year else film.year
            kind, item_id, label = "film", film.id, f"{title} ({year})" if year else title
            file = film_file
        else:
            episode_file = session.exec(select(EpisodeFile).where(EpisodeFile.path == path)).first()
            if episode_file is None or not is_inside(path, tv):
                return None, None
            episode = session.get(Episode, episode_file.episode_id)
            show = session.get(Show, episode_file.show_id)
            if episode is None or show is None or episode.main_file != episode_file.name:
                return None, None
            info = infos.get(show.folder)
            parts = [
                info.title if info and info.title else show.title,
                episode_label(episode.season, episode.episode, episode.episode_end),
                episode.title,
            ]
            kind, item_id = "episode", episode.id
            label = " – ".join(p for p in parts if p)
            file = episode_file
        try:
            record = self._reader.get(session, path)
        except OSError as error:
            return None, f"Tailarr couldn't open {Path(path).name} ({error})."
        if record.error:
            return None, f"MKVToolNix couldn't read {Path(path).name}: {record.error}"
        candidate = Candidate(
            kind=kind,
            id=item_id,  # type: ignore[arg-type]
            label=label,
            path=path,
            is_copy=file.is_copy,
            details=details_of(record),
            read=True,
        )
        return candidate, None

    def process(self, path: str, reason: str) -> list[str]:
        """Let every enabled rule look at one finished file (once per version of the file)."""
        outcomes: list[str] = []
        with Session(self._engine) as session:
            rules = list(session.exec(select(Rule).where(Rule.enabled == True)))  # noqa: E712
            if not rules:
                return outcomes
            try:
                stat = os.stat(path)
            except OSError:
                return outcomes
            candidate, problem = self._candidate(session, path)
            if problem:
                record_activity(self._engine, "rule", "unreadable", problem, ok=False, path=path)
                return outcomes
            if candidate is None:
                return outcomes
            done = {
                r.rule_id
                for r in session.exec(
                    select(RuleRun).where(
                        RuleRun.path == path,
                        RuleRun.size == stat.st_size,
                        RuleRun.mtime == stat.st_mtime,
                    )
                )
            }
        for rule in rules:
            if rule.id in done:
                continue
            if (rule.scope == "films" and candidate.kind != "film") or (
                rule.scope == "tv" and candidate.kind != "episode"
            ):
                continue
            plan = plan_for(rule.to_input(), candidate)
            outcome, job_id = "no-match", None
            if plan is not None and plan.will_run:
                group, count = submit(
                    self._engine,
                    self._queue,
                    rule,
                    [RuleMatch(candidate, plan)],
                    reason=f"{reason}, {candidate.label}",
                )
                outcome = "queued" if count else "skipped"
                with Session(self._engine) as session:
                    job_id = session.exec(select(Job.id).where(Job.group_id == group)).first()
            elif plan is not None:
                outcome = "skipped"
                if (
                    plan.reason
                    and not plan.reason.startswith(_QUIET)
                    and not any(q in plan.reason for q in _QUIET)
                ):
                    record_activity(
                        self._engine,
                        "rule",
                        "skipped",
                        f"Rule “{rule.name}” skipped {candidate.label}: {plan.reason}",
                        path=path,
                        rule_id=rule.id,
                    )
            outcomes.append(outcome)
            with Session(self._engine) as session:
                session.add(
                    RuleRun(
                        rule_id=rule.id,  # type: ignore[arg-type]
                        path=path,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        at=time.time(),
                        outcome=outcome,
                        job_id=job_id,
                    )
                )
                session.commit()
        return outcomes

    def after_job(self, job: Job, job_type: JobType) -> None:
        """Tailarr changed an original itself: rules shouldn't treat that as a new file."""
        if not job_type.in_place:
            return
        try:
            stat = os.stat(job.path)
        except OSError:
            return
        with Session(self._engine) as session:
            for rule_id in session.exec(select(Rule.id)).all():
                session.add(
                    RuleRun(
                        rule_id=rule_id,  # type: ignore[arg-type]
                        path=job.path,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        at=time.time(),
                        outcome="tailarr-change",
                        job_id=job.id,
                    )
                )
            session.commit()

    # -- background ------------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self.apply_watch_settings()
        self._thread = threading.Thread(target=self._loop, name="auto-rules", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._stop_observer()

    def _loop(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            try:
                self.tick()
                settings = self.settings()
                if (
                    settings.watch_folders
                    and time.time() - self._last_rescan > settings.rescan_minutes * 60
                ):
                    self._last_rescan = time.time()
                    self._start_scans()  # each scan then calls scanned()
            except Exception:
                log.exception("Automatic rules check failed")

    def apply_watch_settings(self) -> None:
        """Start or stop watching the folders to match the settings."""
        settings = self.settings()
        roots = tuple(r for r in self.roots() if os.path.isdir(r))
        if not settings.watch_folders:
            self._stop_observer()
            return
        if self._observer is not None and self._watching == roots:
            return
        self._stop_observer()
        try:
            from watchdog.events import FileSystemEvent, FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:  # pragma: no cover - watchdog is a dependency
            return
        runner = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    runner.add(str(event.src_path), "new file in a watched folder")

            def on_moved(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    runner.add(str(event.dest_path), "new file in a watched folder")

        observer = Observer()
        for root in roots:
            try:
                observer.schedule(Handler(), root, recursive=True)
            except OSError as error:
                log.warning("Can't watch %s: %s", root, error)
        observer.daemon = True
        observer.start()
        self._observer, self._watching = observer, roots

    def _stop_observer(self) -> None:
        observer, self._observer = self._observer, None
        if observer is not None:
            observer.stop()
            observer.join(5)
