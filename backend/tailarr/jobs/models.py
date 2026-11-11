"""The job table. Unlike the library tables, this is history the owner sees, not a cache."""

from __future__ import annotations

from enum import StrEnum

from sqlmodel import Field, SQLModel

# Bump when Job columns change. Old job history is then cleared (it's only history:
# nothing on disk depends on it, and no job can be running while Tailarr starts).
JOB_TABLE_VERSION = 2  # 2: added `result`


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # Tailarr stopped (restart, crash) while the job was running


ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str  # which job type runs it, e.g. "track_settings"
    title: str  # what it does, e.g. "Change track settings"
    subject: str  # what it's done to, e.g. "Blade Runner (1982)"
    film_id: int | None = None
    path: str  # the file the job works on
    group_id: str | None = Field(default=None, index=True)  # jobs started together (TV, rules)
    status: str = Field(default=JobStatus.QUEUED, index=True)
    step: str = ""  # e.g. "Saving the changes"
    step_number: int = 0
    step_count: int = 0
    progress: float | None = None  # 0-100 for the current step; None = no percentage
    cancellable: bool = True  # False while a step that mustn't be interrupted runs
    cancel_requested: bool = False
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    message: str | None = None  # plain-English result, e.g. "2 tracks changed."
    error: str | None = None  # plain-English reason it failed
    error_details: str | None = None  # the tools' own words, for "Show technical details"
    params: str = "{}"  # JSON: what the job type needs
    temp_paths: str = "[]"  # JSON: temporary files to remove if the job doesn't finish
    result: str | None = None  # JSON: facts for the web page, e.g. the new copy's file name


class CopyRecord(SQLModel, table=True):
    """A copy Tailarr made, and the file it was made from.

    Used to check, before "Replace the original", that the original hasn't changed since
    the copy was made (e.g. Radarr upgraded it). Stage 8 builds on this to tidy up copies
    after upgrades and renames. Never cleared automatically: it's not a cache.
    """

    path: str = Field(primary_key=True)  # the copy
    source_path: str = Field(index=True)
    source_size: int
    source_mtime: float
    kind: str  # the job type that made it, e.g. "remove_tracks"
    created_at: float
    job_id: int | None = None


class RecycledFile(SQLModel, table=True):
    """An original file moved to a recycle folder, to be deleted after the keep period."""

    id: int | None = Field(default=None, primary_key=True)
    path: str  # where it is now, inside a ".tailarr-recycle" folder
    original_path: str  # where it was
    size: int
    recycled_at: float
    job_id: int | None = None
