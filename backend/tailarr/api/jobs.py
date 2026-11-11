"""The job queue: list, follow, cancel and clear jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from ..jobs.engine import JobQueue
from ..jobs.models import ACTIVE, Job, JobStatus
from .deps import get_session

router = APIRouter(prefix="/api/jobs")

HISTORY_LIMIT = 100


def get_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


class JobOut(BaseModel):
    id: int
    kind: str
    title: str
    subject: str
    file_name: str
    film_id: int | None
    group_id: str | None
    status: JobStatus
    step: str
    step_number: int
    step_count: int
    progress: float | None
    cancellable: bool
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    message: str | None
    error: str | None
    error_details: str | None


class JobCountsOut(BaseModel):
    running: int
    queued: int


class JobListOut(BaseModel):
    jobs: list[JobOut]
    counts: JobCountsOut


def _time(seconds: float | None) -> datetime | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, UTC)


def job_out(job: Job) -> JobOut:
    assert job.id is not None
    return JobOut(
        id=job.id,
        kind=job.kind,
        title=job.title,
        subject=job.subject,
        file_name=job.path.rsplit("/", 1)[-1],
        film_id=job.film_id,
        group_id=job.group_id,
        status=JobStatus(job.status),
        step=job.step,
        step_number=job.step_number,
        step_count=job.step_count,
        progress=job.progress,
        cancellable=job.cancellable and job.status in ACTIVE,
        cancel_requested=job.cancel_requested,
        created_at=_time(job.created_at),  # type: ignore[arg-type]
        started_at=_time(job.started_at),
        finished_at=_time(job.finished_at),
        message=job.message,
        error=job.error,
        error_details=job.error_details,
    )


def _counts(session: Session) -> JobCountsOut:
    rows = session.exec(
        select(Job.status, func.count())
        .where(col(Job.status).in_(list(ACTIVE)))
        .group_by(Job.status)
    ).all()
    counts = dict(rows)
    return JobCountsOut(
        running=counts.get(JobStatus.RUNNING, 0), queued=counts.get(JobStatus.QUEUED, 0)
    )


@router.get("", response_model=JobListOut)
def list_jobs(session: Annotated[Session, Depends(get_session)]) -> JobListOut:
    """Waiting and running jobs first (oldest first), then the most recent finished ones."""
    active = session.exec(
        select(Job).where(col(Job.status).in_(list(ACTIVE))).order_by(col(Job.id))
    ).all()
    history = session.exec(
        select(Job)
        .where(col(Job.status).not_in(list(ACTIVE)))
        .order_by(col(Job.finished_at).desc(), col(Job.id).desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return JobListOut(jobs=[job_out(j) for j in [*active, *history]], counts=_counts(session))


@router.get("/counts", response_model=JobCountsOut)
def job_counts(session: Annotated[Session, Depends(get_session)]) -> JobCountsOut:
    """How many jobs are running and waiting (for the badge on Queue)."""
    return _counts(session)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, queue: Annotated[JobQueue, Depends(get_queue)]) -> JobOut:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="This job isn't in the list any more.")
    return job_out(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, queue: Annotated[JobQueue, Depends(get_queue)]) -> JobOut:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="This job isn't in the list any more.")
    if job.status == JobStatus.RUNNING and not job.cancellable:
        raise HTTPException(
            status_code=409,
            detail="This step can't be stopped safely: stopping now could damage the file. "
            "It only takes a moment.",
        )
    if job.status not in ACTIVE:
        raise HTTPException(status_code=409, detail="This job has already finished.")
    cancelled = queue.cancel(job_id)
    assert cancelled is not None
    return job_out(cancelled)


class ClearedOut(BaseModel):
    removed: int


@router.delete("/finished", response_model=ClearedOut)
def clear_finished(queue: Annotated[JobQueue, Depends(get_queue)]) -> ClearedOut:
    """Remove finished, failed and cancelled jobs from the list."""
    return ClearedOut(removed=queue.clear_finished())
