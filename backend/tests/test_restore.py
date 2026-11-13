"""Putting files back from the recycle folder (Settings → Recycle folder → Restore)."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tailarr.core.config import AppConfig
from tailarr.jobs import restore
from tailarr.jobs.engine import JobQueue
from tailarr.jobs.models import RecycledFile
from tailarr.jobs.recycle import RECYCLE_FOLDER, move_to_recycle

FILM = "Sample Multi-Language Film (2021)"
FILE = "Sample Multi-Language Film (2021).mkv"


@pytest.fixture
def library(samples_dir: Path, config: AppConfig) -> Path:
    movies = Path(config.default_movies_dir)
    shutil.rmtree(movies)
    shutil.copytree(samples_dir / "data" / "media" / "movies", movies, symlinks=True)
    return movies


@pytest.fixture
def app_client(client: TestClient, library: Path):
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    queue: JobQueue = client.app.state.job_queue  # type: ignore[attr-defined]
    queue.start()
    yield client
    queue.stop()


def _engine(client: TestClient):
    return client.app.state.engine  # type: ignore[attr-defined]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wait(client: TestClient, job_id: int, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def _recycle(client: TestClient, path: Path) -> RecycledFile:
    with Session(_engine(client)) as session:
        record = move_to_recycle(session, str(path))
        session.expunge(record)
        return record


def _restore(client: TestClient, record_id: int, **body):
    return client.post(
        f"/api/settings/recycle/files/{record_id}/restore", json={"confirmed": True, **body}
    )


def _film_files(client: TestClient) -> list[str]:
    films = client.get("/api/films").json()["films"]
    film = next((f for f in films if f["folder_name"] == FILM), None)
    if film is None:
        return []
    return [f["name"] for f in client.get(f"/api/films/{film['id']}").json()["files"]]


def test_restore_puts_the_file_back(app_client: TestClient, library: Path) -> None:
    original = library / FILM / FILE
    before = _hash(original)
    record = _recycle(app_client, original)
    app_client.app.state.folder_changed(str(original.parent))  # type: ignore[attr-defined]
    assert FILE not in _film_files(app_client)

    listed = app_client.get("/api/settings/recycle/files").json()
    assert len(listed) == 1
    item = listed[0]
    assert item["id"] == record.id and item["name"] == FILE and item["folder"] == FILM
    assert item["original_path"] == str(original)
    assert item["available"] is True and item["clash"] is False and item["clash_size"] is None
    assert item["days_left"] == 30 and item["size"] == record.size

    unconfirmed = app_client.post(
        f"/api/settings/recycle/files/{record.id}/restore", json={"confirmed": False}
    )
    assert unconfirmed.status_code == 400
    assert Path(record.path).exists()

    response = _restore(app_client, record.id)  # type: ignore[arg-type]
    assert response.status_code == 202, response.text
    job = _wait(app_client, response.json()["id"])
    assert job["status"] == "done", job
    # The film had no other file, so it left the list: the job is named after the file.
    assert job["kind"] == restore.KIND and job["subject"] == Path(FILE).stem
    assert job["message"] == f"Put {FILE} back from the recycle folder."

    assert _hash(original) == before
    assert not (library / FILM / RECYCLE_FOLDER).exists()  # the empty recycle folder went
    with Session(_engine(app_client)) as session:
        assert session.exec(select(RecycledFile)).all() == []
    assert app_client.get("/api/settings/recycle/files").json() == []
    assert FILE in _film_files(app_client)  # shown straight away
    activity = app_client.get("/api/activity").json()
    assert any(a["kind"] == "restored" and a["source"] == "tailarr" for a in activity)


def test_restore_refuses_a_clash_unless_swapping(app_client: TestClient, library: Path) -> None:
    original = library / FILM / FILE
    old = _hash(original)
    record = _recycle(app_client, original)
    original.write_bytes(b"the copy that replaced it")
    item = app_client.get("/api/settings/recycle/files").json()[0]
    assert item["clash"] is True and item["clash_size"] == len(b"the copy that replaced it")

    refused = _restore(app_client, record.id)  # type: ignore[arg-type]
    assert refused.status_code == 409
    assert "already a file called" in refused.json()["detail"]
    assert original.read_bytes() == b"the copy that replaced it"

    # The job checks again itself (e.g. the file appeared after it was queued).
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    job = queue.submit(
        restore.KIND,
        title=restore.TITLE,
        subject="x",
        path=str(original),
        params={"recycled_id": record.id, "swap": False},
    )
    failed = _wait(app_client, job.id)  # type: ignore[arg-type]
    assert failed["status"] == "failed" and "already a file called" in failed["error"]

    swapped = _restore(app_client, record.id, swap=True)  # type: ignore[arg-type]
    assert swapped.status_code == 202, swapped.text
    job_out = _wait(app_client, swapped.json()["id"])
    assert job_out["status"] == "done", job_out
    assert "The file that was there moved to the recycle folder" in job_out["message"]
    assert _hash(original) == old
    # The file that was there waits in the recycle folder now, and can be put back too.
    listed = app_client.get("/api/settings/recycle/files").json()
    assert len(listed) == 1 and listed[0]["name"] == FILE and listed[0]["clash"] is True
    assert Path(job_out["result"]["recycled"]).read_bytes() == b"the copy that replaced it"


def test_restore_after_replacing_the_original(app_client: TestClient, library: Path) -> None:
    """The whole round trip: make a copy, replace the original with it, then undo that."""
    films = app_client.get("/api/films").json()["films"]
    film_id = next(f["id"] for f in films if f["folder_name"] == FILM)
    original = library / FILM / FILE
    before = _hash(original)
    tracks = app_client.get(f"/api/films/{film_id}/media", params={"file": FILE}).json()["tracks"]
    subs = [t for t in tracks if t["type"] == "subtitles"]
    made = app_client.post(
        f"/api/films/{film_id}/remove-tracks",
        json={"file": FILE, "remove": [subs[-1]["uid"]], "confirmed": True},
    )
    assert _wait(app_client, made.json()["id"])["status"] == "done"
    copy = "Sample Multi-Language Film (2021) - Tailarr.mkv"
    replaced = app_client.post(
        f"/api/films/{film_id}/replace-original",
        json={"copy_file": copy, "confirmed": True, "understood": True},
    )
    assert _wait(app_client, replaced.json()["id"])["status"] == "done"
    assert _hash(original) != before

    record_id = app_client.get("/api/settings/recycle/files").json()[0]["id"]
    job = _wait(app_client, _restore(app_client, record_id, swap=True).json()["id"])
    assert job["status"] == "done", job
    assert _hash(original) == before
    assert job["film_id"] == film_id


def test_restore_refuses_files_outside_the_library(
    app_client: TestClient, library: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "data" / "torrents" / RECYCLE_FOLDER / "Film.mkv"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"x")
    not_recycle = library / FILM / "Somewhere" / FILE
    not_recycle.parent.mkdir()
    not_recycle.write_bytes(b"x")
    elsewhere = library / FILM / RECYCLE_FOLDER / "Other.mkv"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"x")
    rows = [
        # A recycled file outside the Films and TV folders.
        RecycledFile(
            path=str(outside),
            original_path=str(library / FILM / "Film.mkv"),
            size=1,
            recycled_at=time.time(),
        ),
        # Not in a recycle folder.
        RecycledFile(
            path=str(not_recycle),
            original_path=str(library / FILM / "New.mkv"),
            size=1,
            recycled_at=time.time(),
        ),
        # Going back somewhere other than its own folder (e.g. the downloads).
        RecycledFile(
            path=str(elsewhere),
            original_path=str(tmp_path / "data" / "torrents" / "Other.mkv"),
            size=1,
            recycled_at=time.time(),
        ),
    ]
    with Session(_engine(app_client)) as session:
        for row in rows:
            session.add(row)
        session.commit()
        ids = [row.id for row in rows]
    listed = {item["id"] for item in app_client.get("/api/settings/recycle/files").json()}
    assert ids[0] not in listed  # not shown at all
    for record_id in ids:
        refused = _restore(app_client, record_id, swap=True)  # type: ignore[arg-type]
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"] == restore.NOT_OURS
    assert outside.exists() and not_recycle.exists() and elsewhere.exists()
    assert not (tmp_path / "data" / "torrents" / "Other.mkv").exists()


def test_restore_when_the_file_is_gone(app_client: TestClient, library: Path) -> None:
    record = _recycle(app_client, library / FILM / FILE)
    os.unlink(record.path)
    item = app_client.get("/api/settings/recycle/files").json()[0]
    assert item["available"] is False
    refused = _restore(app_client, record.id)  # type: ignore[arg-type]
    assert refused.status_code == 409 and refused.json()["detail"] == restore.GONE
    assert _restore(app_client, 9999).json()["detail"] == restore.GONE


def test_a_failed_restore_puts_the_current_file_back(
    app_client: TestClient, library: Path, monkeypatch
) -> None:
    original = library / FILM / FILE
    record = _recycle(app_client, original)
    original.write_bytes(b"current")
    real_rename = os.rename

    def failing_rename(src, dst):  # noqa: ANN001, ANN202
        if Path(src) == Path(record.path):
            raise OSError("disk said no")
        return real_rename(src, dst)

    monkeypatch.setattr(restore.os, "rename", failing_rename)
    job = _wait(app_client, _restore(app_client, record.id, swap=True).json()["id"])  # type: ignore[arg-type]
    assert job["status"] == "failed"
    assert job["error"] == "Tailarr couldn't put the file back, so nothing was changed."
    assert original.read_bytes() == b"current"
    assert Path(record.path).exists()
    with Session(_engine(app_client)) as session:
        assert [r.id for r in session.exec(select(RecycledFile))] == [record.id]


def test_restore_interrupted_message() -> None:
    job_type = restore.make_job_type(None, lambda: [], lambda folder: None)  # type: ignore[arg-type]
    assert job_type.in_place and job_type.interrupted_message == restore.INTERRUPTED
