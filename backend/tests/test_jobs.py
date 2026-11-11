"""The job queue engine: order, progress, failures, cancelling, clean-up and restarts."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tailarr.core.db import make_engine
from tailarr.core.disk import NotEnoughSpaceError, check_free_space, format_size
from tailarr.jobs.engine import (
    INTERRUPTED_IN_PLACE_MESSAGE,
    INTERRUPTED_MESSAGE,
    JobContext,
    JobFailed,
    JobQueue,
    JobType,
)
from tailarr.jobs.models import Job, JobStatus
from tailarr.media.tools import ToolError


@pytest.fixture
def engine(tmp_path: Path):
    return make_engine(tmp_path / "config" / "tailarr.db")


def _wait_for(queue: JobQueue, job_id: int, *statuses: str, timeout: float = 15) -> Job:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = queue.get(job_id)
        assert job is not None
        if job.status in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} is {job.status}, expected {statuses}")


def _submit(queue: JobQueue, kind: str, **params) -> int:
    job = queue.submit(kind, title="Test", subject="Film", path="/x/film.mkv", params=params)
    assert job.id is not None
    return job.id


def test_jobs_run_in_order_with_steps_and_messages(engine) -> None:
    ran: list[int] = []

    def run(ctx: JobContext) -> str:
        ctx.step(1, 2, "First")
        ctx.progress(50)
        ctx.step(2, 2, "Second")
        ran.append(ctx.params["n"])
        return f"Done {ctx.params['n']}"

    queue = JobQueue(engine, [JobType("demo", run)])
    ids = [_submit(queue, "demo", n=n) for n in range(3)]
    queue.start()
    try:
        assert queue.wait_until_idle()
        for n, job_id in enumerate(ids):
            job = _wait_for(queue, job_id, JobStatus.DONE)
            assert job.message == f"Done {n}"
            assert (job.step, job.step_number, job.step_count) == ("Second", 2, 2)
            assert job.progress == 100
            assert job.started_at and job.finished_at and job.finished_at >= job.started_at
        assert ran == [0, 1, 2]
    finally:
        queue.stop()


def test_failures_are_explained_and_the_queue_carries_on(engine) -> None:
    def fail(ctx: JobContext) -> str:
        kind = ctx.params["how"]
        if kind == "job":
            raise JobFailed("Not enough free space.", "df says so")
        if kind == "tool":
            raise ToolError("'mkvmerge' reported a problem.", "Error: bad file")
        raise RuntimeError("boom")

    queue = JobQueue(engine, [JobType("fail", fail), JobType("ok", lambda ctx: "fine")])
    a = _submit(queue, "fail", how="job")
    b = _submit(queue, "fail", how="tool")
    c = _submit(queue, "fail", how="crash")
    d = _submit(queue, "ok")
    queue.start()
    try:
        assert queue.wait_until_idle()
        job = _wait_for(queue, a, JobStatus.FAILED)
        assert (job.error, job.error_details) == ("Not enough free space.", "df says so")
        job = _wait_for(queue, b, JobStatus.FAILED)
        assert job.error_details == "Error: bad file"
        job = _wait_for(queue, c, JobStatus.FAILED)
        assert job.error == "Something unexpected went wrong, so the job was stopped."
        assert "RuntimeError: boom" in (job.error_details or "")
        assert _wait_for(queue, d, JobStatus.DONE).message == "fine"
    finally:
        queue.stop()


def test_unknown_job_type_fails_politely(engine) -> None:
    queue = JobQueue(engine, [JobType("ok", lambda ctx: "fine")])
    with Session(engine) as session:
        job = Job(kind="from-the-future", title="T", subject="S", path="/p", created_at=1)
        session.add(job)
        session.commit()
        session.refresh(job)
    queue.start()
    try:
        failed = _wait_for(queue, job.id, JobStatus.FAILED)  # type: ignore[arg-type]
        assert "isn't known" in (failed.error or "")
    finally:
        queue.stop()


def test_cancel_a_waiting_job(engine) -> None:
    queue = JobQueue(engine, [JobType("ok", lambda ctx: "fine")])
    job_id = _submit(queue, "ok")
    cancelled = queue.cancel(job_id)
    assert cancelled is not None and cancelled.status == JobStatus.CANCELLED
    queue.start()
    try:
        assert queue.wait_until_idle()
        assert queue.get(job_id).status == JobStatus.CANCELLED  # type: ignore[union-attr]
    finally:
        queue.stop()


def test_cancel_stops_a_running_tool_and_removes_temp_files(engine, tmp_path: Path) -> None:
    started = threading.Event()
    temp: list[Path] = []

    def slow(ctx: JobContext) -> str:
        ctx.step(1, 1, "Copying")
        path = ctx.temp_path(tmp_path)
        path.write_bytes(b"half a film")
        temp.append(path)
        started.set()
        ctx.run_tool("sleep", ["30"])
        return "should not get here"

    queue = JobQueue(engine, [JobType("slow", slow)])
    job_id = _submit(queue, "slow")
    queue.start()
    try:
        assert started.wait(10)
        assert temp[0].name.startswith(".tailarr-tmp-") and temp[0].exists()
        begun = time.monotonic()
        queue.cancel(job_id)
        job = _wait_for(queue, job_id, JobStatus.CANCELLED)
        assert time.monotonic() - begun < 5  # the tool was stopped, not waited for
        assert "Nothing was changed" in (job.message or "")
        assert not temp[0].exists()
    finally:
        queue.stop()


def test_temp_files_always_removed(engine, tmp_path: Path) -> None:
    def make(ctx: JobContext) -> str:
        path = ctx.temp_path(tmp_path, ".bin")
        path.write_bytes(b"x")
        if ctx.params["fail"]:
            raise JobFailed("Nope")
        return "ok"

    queue = JobQueue(engine, [JobType("make", make)])
    bad = _submit(queue, "make", fail=True)
    good = _submit(queue, "make", fail=False)
    queue.start()
    try:
        assert queue.wait_until_idle()
        _wait_for(queue, bad, JobStatus.FAILED)
        _wait_for(queue, good, JobStatus.DONE)
    finally:
        queue.stop()
    assert not (tmp_path / f".tailarr-tmp-{bad}-1.bin").exists()
    # A successful job renames its finished file into place first; anything left is a
    # working file, removed too.
    assert not (tmp_path / f".tailarr-tmp-{good}-1.bin").exists()


def test_restart_marks_running_jobs_interrupted_and_cleans_up(engine, tmp_path: Path) -> None:
    leftover = tmp_path / ".tailarr-tmp-1-1.mkv"
    leftover.write_bytes(b"half")
    not_ours = tmp_path / "Film.mkv"
    not_ours.write_bytes(b"film")
    with Session(engine) as session:
        copy = Job(
            kind="copy",
            title="T",
            subject="S",
            path="/p",
            created_at=1,
            status=JobStatus.RUNNING,
            temp_paths=json.dumps([str(leftover), str(not_ours)]),
        )
        edit = Job(
            kind="edit",
            title="T",
            subject="S",
            path="/p",
            created_at=2,
            status=JobStatus.RUNNING,
            cancellable=False,
        )
        waiting = Job(kind="copy", title="T", subject="S", path="/p", created_at=3)
        session.add_all([copy, edit, waiting])
        session.commit()
        ids = [copy.id, edit.id, waiting.id]

    queue = JobQueue(
        engine, [JobType("copy", lambda ctx: "copied"), JobType("edit", lambda ctx: "x", True)]
    )
    queue.start()
    try:
        first = _wait_for(queue, ids[0], JobStatus.INTERRUPTED)
        assert first.error == INTERRUPTED_MESSAGE
        second = _wait_for(queue, ids[1], JobStatus.INTERRUPTED)
        assert second.error == INTERRUPTED_IN_PLACE_MESSAGE
        # Waiting jobs survive the restart and run.
        assert _wait_for(queue, ids[2], JobStatus.DONE).message == "copied"
    finally:
        queue.stop()
    assert not leftover.exists()
    assert not_ours.exists()  # only Tailarr's own temporary files are ever deleted


def test_clear_finished_keeps_active_jobs(engine) -> None:
    queue = JobQueue(engine, [JobType("ok", lambda ctx: "fine")])
    done = _submit(queue, "ok")
    queue.start()
    _wait_for(queue, done, JobStatus.DONE)
    queue.stop()
    waiting = _submit(queue, "ok")
    assert queue.clear_finished() == 1
    assert queue.get(done) is None
    assert queue.get(waiting) is not None


def test_job_free_space_check(engine, tmp_path: Path) -> None:
    def big(ctx: JobContext) -> str:
        ctx.ensure_free_space(tmp_path, 10**18)
        return "impossible"

    queue = JobQueue(engine, [JobType("big", big)])
    job_id = _submit(queue, "big")
    queue.start()
    try:
        job = _wait_for(queue, job_id, JobStatus.FAILED)
        assert (job.error or "").startswith("Not enough free space on the disk: needs ")
    finally:
        queue.stop()


def test_disk_space_helpers(tmp_path: Path) -> None:
    assert format_size(48 * 1000**3) == "48 GB"
    assert format_size(1.234 * 1000**4) == "1.2 TB"
    assert format_size(730 * 1000**2) == "730 MB"
    assert format_size(12) == "12 bytes"
    assert check_free_space(tmp_path, 0, margin=0) > 0
    # A folder that doesn't exist yet is checked on its nearest existing parent.
    assert check_free_space(tmp_path / "new" / "folder", 0, margin=0) > 0
    with pytest.raises(NotEnoughSpaceError) as err:
        check_free_space(tmp_path, 10**18)
    assert "free. Free up some space" in err.value.message


# -- the API --------------------------------------------------------------------------


def test_jobs_api(client: TestClient) -> None:
    queue: JobQueue = client.app.state.job_queue  # type: ignore[attr-defined]
    assert client.get("/api/jobs").json() == {"jobs": [], "counts": {"running": 0, "queued": 0}}
    job = queue.submit(
        "track_settings",
        title="Change track settings",
        subject="Film (2020)",
        path="/data/media/movies/Film (2020)/Film.mkv",
        params={},
        film_id=7,
    )
    body = client.get("/api/jobs").json()
    assert body["counts"] == {"running": 0, "queued": 1}
    listed = body["jobs"][0]
    assert listed["status"] == "queued"
    assert listed["file_name"] == "Film.mkv"
    assert listed["film_id"] == 7
    assert listed["cancellable"] is True
    assert client.get("/api/jobs/counts").json() == {"running": 0, "queued": 1}
    assert client.get(f"/api/jobs/{job.id}").json()["subject"] == "Film (2020)"

    cancelled = client.post(f"/api/jobs/{job.id}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancellable"] is False
    again = client.post(f"/api/jobs/{job.id}/cancel")
    assert again.status_code == 409
    assert client.get("/api/jobs/999").status_code == 404

    assert client.delete("/api/jobs/finished").json() == {"removed": 1}
    assert client.get("/api/jobs").json()["jobs"] == []


def test_running_step_that_cannot_be_stopped(client: TestClient) -> None:
    queue: JobQueue = client.app.state.job_queue  # type: ignore[attr-defined]
    job = queue.submit("track_settings", title="T", subject="S", path="/p", params={})
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        row = session.get(Job, job.id)
        assert row is not None
        row.status, row.cancellable = JobStatus.RUNNING, False
        session.add(row)
        session.commit()
    response = client.post(f"/api/jobs/{job.id}/cancel")
    assert response.status_code == 409
    assert "can't be stopped safely" in response.json()["detail"]


def test_job_files_get_unraid_permissions(engine) -> None:
    # The database (which holds the jobs) follows UMASK like every file Tailarr makes.
    path = Path(engine.url.database)
    assert path.stat().st_mode & 0o777 == 0o666 & ~_umask()


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask
