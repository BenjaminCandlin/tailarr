"""Running jobs one at a time in the background.

Jobs are stored in SQLite so they survive restarts. A single worker thread
takes the oldest waiting job and runs it (disks are the bottleneck, so running
several at once would only make each one slower).

Each job type is a function that receives a :class:`JobContext`. The context
reports progress, runs tools (stopping them if the job is cancelled), hands out
temporary file names and checks free disk space. Whatever happens, temporary
files are removed when a job doesn't finish successfully, and jobs that were
running when Tailarr stopped are marked "interrupted" when it starts again.
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
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from ..core.disk import NotEnoughSpaceError, check_free_space
from ..media.tools import ToolCancelled, ToolError, ToolResult, run_tool_live
from .models import ACTIVE, Job, JobStatus

log = logging.getLogger(__name__)

TEMP_PREFIX = ".tailarr-tmp-"


class JobFailed(Exception):
    """A job couldn't be done. `message` is plain English; `details` is for experts."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class JobCancelled(Exception):
    """The owner cancelled the job."""


INTERRUPTED_MESSAGE = (
    "Tailarr was stopped or restarted while this job was running, so it didn't finish. "
    "Nothing was left half-done: any temporary files were removed. You can start it again."
)
INTERRUPTED_IN_PLACE_MESSAGE = (
    "Tailarr was stopped or restarted while this job was changing the file. "
    "Open the film to check its tracks, then try again if needed."
)


def _now() -> float:
    return time.time()


class JobContext:
    """What a running job uses to report progress and do its work safely."""

    def __init__(self, queue: JobQueue, job: Job) -> None:
        assert job.id is not None
        self._queue = queue
        self.job_id: int = job.id
        self.path = job.path
        self.film_id = job.film_id
        self.params: dict[str, Any] = json.loads(job.params)
        # Facts for the web page once the job is done (e.g. the new copy's file name).
        self.result: dict[str, Any] | None = None
        self.cancel_event = threading.Event()
        self._last_progress_write = 0.0
        self._temp_count = 0

    # -- progress --------------------------------------------------------------
    def step(self, number: int, count: int, text: str, *, cancellable: bool = True) -> None:
        """Start a new step, e.g. step(2, 3, "Saving the changes")."""
        self.check_cancelled()
        self._queue._update(
            self.job_id,
            step=text,
            step_number=number,
            step_count=count,
            progress=None,
            cancellable=cancellable,
        )

    def progress(self, percent: float) -> None:
        # Writing to the database for every percent would be wasteful; twice a second is plenty.
        now = time.monotonic()
        if percent < 100 and now - self._last_progress_write < 0.5:
            return
        self._last_progress_write = now
        self._queue._update(self.job_id, progress=max(0.0, min(100.0, percent)))

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled

    # -- tools -------------------------------------------------------------------
    def run_tool(
        self, name: str, args: list[str], *, cancellable: bool = True, timeout: float | None = None
    ) -> ToolResult:
        """Run a tool with live progress. Cancelling the job stops it (if `cancellable`)."""
        self.check_cancelled()
        try:
            return run_tool_live(
                name,
                args,
                on_progress=self.progress,
                cancel=self.cancel_event if cancellable else None,
                timeout=timeout,
            )
        except ToolCancelled as exc:
            raise JobCancelled from exc

    # -- files -------------------------------------------------------------------
    def temp_path(self, folder: str | os.PathLike[str], suffix: str = ".mkv") -> Path:
        """A hidden temporary file name in `folder`. It's removed if the job doesn't finish."""
        self._temp_count += 1
        path = Path(folder) / f"{TEMP_PREFIX}{self.job_id}-{self._temp_count}{suffix}"
        self._queue._add_temp_path(self.job_id, str(path))
        return path

    def discard(self, path: str | os.PathLike[str]) -> None:
        """Delete a temporary working file as soon as it's no longer needed (frees space)."""
        if Path(path).name.startswith(TEMP_PREFIX):
            Path(path).unlink(missing_ok=True)

    def ensure_free_space(self, folder: str | os.PathLike[str], needed: int, **kw: int) -> None:
        try:
            check_free_space(folder, needed, **kw)
        except NotEnoughSpaceError as exc:
            raise JobFailed(exc.message) from exc


JobHandler = Callable[[JobContext], str]


@dataclass(frozen=True)
class JobType:
    kind: str
    run: JobHandler
    # True for jobs that edit the original file itself: an interruption is explained differently.
    in_place: bool = False
    # What to say if Tailarr stopped during one of its "can't be cancelled" steps.
    interrupted_message: str | None = None


class JobQueue:
    def __init__(self, engine: Engine, job_types: list[JobType]) -> None:
        self._engine = engine
        self._types = {t.kind: t for t in job_types}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: JobContext | None = None
        self._idle = threading.Event()
        self._idle.set()

    # -- adding and cancelling ---------------------------------------------------
    def submit(
        self,
        kind: str,
        *,
        title: str,
        subject: str,
        path: str,
        params: dict[str, Any],
        film_id: int | None = None,
        group_id: str | None = None,
    ) -> Job:
        if kind not in self._types:
            raise ValueError(f"Unknown job type {kind!r}")
        job = Job(
            kind=kind,
            title=title,
            subject=subject,
            path=path,
            film_id=film_id,
            group_id=group_id,
            params=json.dumps(params),
            created_at=_now(),
        )
        with Session(self._engine) as session:
            session.add(job)
            session.commit()
            session.refresh(job)
        self._idle.clear()
        self._wake.set()
        return job

    def cancel(self, job_id: int) -> Job | None:
        """Cancel a waiting job at once, or ask a running one to stop."""
        with self._lock, Session(self._engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return None
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.finished_at = _now()
                job.message = "Cancelled before it started. Nothing was changed."
            elif job.status == JobStatus.RUNNING:
                job.cancel_requested = True
                current = self._current
                if current is not None and current.job_id == job_id:
                    current.cancel_event.set()
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def get(self, job_id: int) -> Job | None:
        with Session(self._engine) as session:
            return session.get(Job, job_id)

    def clear_finished(self) -> int:
        """Forget finished jobs (the history list). Waiting and running jobs stay."""
        with Session(self._engine) as session:
            jobs = session.exec(select(Job).where(col(Job.status).not_in(list(ACTIVE)))).all()
            for job in jobs:
                session.delete(job)
            session.commit()
            return len(jobs)

    # -- worker ------------------------------------------------------------------
    def start(self) -> None:
        """Tidy up after the last run, then start working through the queue."""
        self.recover()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._work, name="job-worker", daemon=True)
            self._thread.start()
        self._wake.set()

    def stop(self, timeout: float | None = 10) -> None:
        self._stop.set()
        current = self._current
        if current is not None:
            current.cancel_event.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def wait_until_idle(self, timeout: float = 30) -> bool:
        """For tests: wait until no job is waiting or running."""
        return self._idle.wait(timeout)

    def recover(self) -> None:
        """Mark jobs that were running when Tailarr stopped as interrupted, and clean up."""
        with Session(self._engine) as session:
            stuck = session.exec(select(Job).where(Job.status == JobStatus.RUNNING)).all()
            for job in stuck:
                job_type = self._types.get(job.kind)
                _remove_temp_files(job)
                # An in-place job stopped during its "don't interrupt" step may have
                # changed the file; say so honestly.
                mid_edit = job_type is not None and job_type.in_place and not job.cancellable
                job.error = INTERRUPTED_MESSAGE
                if mid_edit:
                    assert job_type is not None
                    job.error = job_type.interrupted_message or INTERRUPTED_IN_PLACE_MESSAGE
                job.status = JobStatus.INTERRUPTED
                job.finished_at = _now()
                job.cancellable = False
                session.add(job)
            session.commit()

    def _next_job(self) -> Job | None:
        with Session(self._engine) as session:
            query = (
                select(Job)
                .where(Job.status == JobStatus.QUEUED)
                .order_by(col(Job.created_at), col(Job.id))
                .limit(1)
            )
            return session.exec(query).first()

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._next_job()
            except Exception:  # e.g. the database is briefly locked
                log.exception("Couldn't read the job queue")
                job = None
            if job is None:
                self._idle.set()
                self._wake.wait(5)
                self._wake.clear()
                continue
            self._idle.clear()
            self._run(job)

    def _run(self, job: Job) -> None:
        job_type = self._types.get(job.kind)
        context = JobContext(self, job)
        with self._lock:
            # Re-check: it may have been cancelled between being picked and starting.
            with Session(self._engine) as session:
                fresh = session.get(Job, job.id)
                if fresh is None or fresh.status != JobStatus.QUEUED:
                    return
                fresh.status = JobStatus.RUNNING
                fresh.started_at = _now()
                session.add(fresh)
                session.commit()
            self._current = context

        outcome: dict[str, Any]
        try:
            if job_type is None:
                raise JobFailed(
                    "This kind of job isn't known to this version of Tailarr.", job.kind
                )
            message = job_type.run(context)
            outcome = {"status": JobStatus.DONE, "message": message, "progress": 100.0}
            if context.result is not None:
                outcome["result"] = json.dumps(context.result)
        except JobCancelled:
            outcome = {
                "status": JobStatus.CANCELLED,
                "message": "Cancelled. Nothing was changed and no files were left behind.",
            }
        except JobFailed as exc:
            outcome = {
                "status": JobStatus.FAILED,
                "error": exc.message,
                "error_details": exc.details or None,
            }
        except ToolError as exc:
            outcome = {
                "status": JobStatus.FAILED,
                "error": exc.message,
                "error_details": exc.details or None,
            }
        except Exception as exc:  # never let one job stop the queue
            log.exception("Job %s failed unexpectedly", job.id)
            outcome = {
                "status": JobStatus.FAILED,
                "error": "Something unexpected went wrong, so the job was stopped.",
                "error_details": f"{type(exc).__name__}: {exc}",
            }
        finally:
            with self._lock:
                self._current = None

        with Session(self._engine) as session:
            fresh = session.get(Job, job.id)
            if fresh is None:
                return
            # Whatever happened, no temporary file is left behind. (A successful job has
            # already renamed its finished file into place; leftovers are working files.)
            _remove_temp_files(fresh)
            for key, value in outcome.items():
                setattr(fresh, key, value)
            fresh.finished_at = _now()
            fresh.cancellable = False
            session.add(fresh)
            session.commit()

    # -- used by JobContext --------------------------------------------------------
    def _update(self, job_id: int, **values: Any) -> None:
        with Session(self._engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            for key, value in values.items():
                setattr(job, key, value)
            session.add(job)
            session.commit()

    def _add_temp_path(self, job_id: int, path: str) -> None:
        with Session(self._engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            paths = json.loads(job.temp_paths)
            paths.append(path)
            job.temp_paths = json.dumps(paths)
            session.add(job)
            session.commit()


def _remove_temp_files(job: Job) -> None:
    for path in json.loads(job.temp_paths or "[]"):
        # Only ever delete Tailarr's own hidden temporary files.
        if not Path(path).name.startswith(TEMP_PREFIX):
            continue
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            log.warning("Couldn't remove temporary file %s", path)
