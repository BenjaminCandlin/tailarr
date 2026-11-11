"""Saving a copy without some tracks, replacing the original, and the recycle folder."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tailarr.core.config import AppConfig
from tailarr.jobs import remove_tracks, replace_original
from tailarr.jobs.engine import JobFailed, JobQueue
from tailarr.jobs.models import CopyRecord, Job, JobStatus, RecycledFile
from tailarr.jobs.recycle import RECYCLE_FOLDER, clean_recycle, recycle_path
from tailarr.jobs.remove_tracks import output_name, place_new_file

FILM = "Sample Multi-Language Film (2021)"
FILE = "Sample Multi-Language Film (2021).mkv"
COPY = "Sample Multi-Language Film (2021) - Tailarr.mkv"


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


def _film_id(client: TestClient, title: str = "Sample Multi-Language Film") -> int:
    films = client.get("/api/films").json()["films"]
    return next(f["id"] for f in films if f["title"] == title)


def _tracks(client: TestClient, film_id: int, file: str = FILE) -> list[dict]:
    return client.get(f"/api/films/{film_id}/media", params={"file": file}).json()["tracks"]


def _by_type(tracks: list[dict], kind: str) -> list[dict]:
    return [t for t in tracks if t["type"] == kind]


def _mkvmerge(path: Path) -> dict:
    env = {**os.environ, "LC_ALL": "C.UTF-8"}
    out = subprocess.run(["mkvmerge", "-J", str(path)], capture_output=True, env=env, check=True)
    return json.loads(out.stdout)


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


def _remove_body(client: TestClient, film_id: int, **extra) -> dict:
    tracks = _tracks(client, film_id)
    audio = _by_type(tracks, "audio")
    subs = _by_type(tracks, "subtitles")
    # Leave out the Japanese audio and the French and Spanish subtitles.
    return {
        "file": FILE,
        "remove": [audio[2]["uid"], subs[2]["uid"], subs[3]["uid"]],
        **extra,
    }


def _make_copy(client: TestClient, film_id: int, **extra) -> dict:
    body = _remove_body(client, film_id, confirmed=True, **extra)
    response = client.post(f"/api/films/{film_id}/remove-tracks", json=body)
    assert response.status_code == 202, response.text
    return _wait(client, response.json()["id"])


# -- naming and planning --------------------------------------------------------------------


def test_copy_names() -> None:
    assert output_name("Film (2020).mkv") == "Film (2020) - Tailarr.mkv"
    assert output_name("Film (2020) - HDR10.mkv") == "Film (2020) - HDR10 - Tailarr.mkv"
    # A copy of Tailarr's own copy updates it rather than stacking names.
    assert output_name("Film (2020) - Tailarr.mkv") == "Film (2020) - Tailarr.mkv"


def test_preview(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client)
    original = library / FILM / FILE
    before = _hash(original)
    tracks = _tracks(app_client, film_id)
    body = _remove_body(app_client, film_id)
    body["changes"] = [{"uid": _by_type(tracks, "audio")[1]["uid"], "name": "French"}]
    response = app_client.post(f"/api/films/{film_id}/remove-tracks/preview", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["new_file"] == COPY
    assert data["exists"] is False and data["updates_copy"] is False
    assert data["removed"] == [
        "Audio 3: Japanese – AAC, Stereo, “Japanese”",
        "Subtitles 3: French – SRT (text), “Français”",
        "Subtitles 4: Spanish – SRT (text), “Español”",
    ]
    assert len(data["kept"]) == 5
    assert data["settings"] == [
        {
            "label": "Audio 2: French",
            "changes": ["Rename it from “Français 5.1” to “French”"],
        }
    ]
    assert data["warnings"] == []
    assert data["space_needed"] > original.stat().st_size
    assert data["enough_space"] is True
    assert _hash(original) == before  # a preview never changes anything
    assert not (library / FILM / COPY).exists()


def test_preview_warnings(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    tracks = _tracks(app_client, film_id)
    audio, subs = _by_type(tracks, "audio"), _by_type(tracks, "subtitles")
    body = {"file": FILE, "remove": [audio[0]["uid"], subs[0]["uid"]]}
    data = app_client.post(f"/api/films/{film_id}/remove-tracks/preview", json=body).json()
    assert any("None of the audio tracks left" in w for w in data["warnings"])
    assert any("no subtitles will show" in w for w in data["warnings"])


@pytest.mark.parametrize(
    ("pick", "status", "message"),
    [
        (lambda t: [], 400, "Untick at least one track"),
        (lambda t: [t[0]["uid"]], 400, "Video tracks can't be removed"),
        (lambda t: [x["uid"] for x in t if x["type"] == "audio"], 400, "Keep at least one audio"),
        (lambda t: ["12345"], 409, "tracks in this file have changed"),
    ],
)
def test_refused_copies(app_client: TestClient, pick, status: int, message: str) -> None:
    film_id = _film_id(app_client)
    body = {"file": FILE, "remove": pick(_tracks(app_client, film_id))}
    response = app_client.post(f"/api/films/{film_id}/remove-tracks/preview", json=body)
    assert response.status_code == status
    assert message in response.json()["detail"]


def test_copy_needs_confirmation(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    response = app_client.post(
        f"/api/films/{film_id}/remove-tracks", json=_remove_body(app_client, film_id)
    )
    assert response.status_code == 400
    assert app_client.get("/api/jobs").json()["jobs"] == []


# -- making the copy ------------------------------------------------------------------------


def test_make_a_copy(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client)
    original = library / FILM / FILE
    before = (_hash(original), original.stat().st_mtime)
    tracks = _tracks(app_client, film_id)
    japanese, french = _by_type(tracks, "audio")[2], _by_type(tracks, "audio")[1]
    job = _make_copy(
        app_client,
        film_id,
        changes=[
            {"uid": french["uid"], "default": True, "name": "French"},
            {"uid": _by_type(tracks, "audio")[0]["uid"], "default": False},
            {"uid": japanese["uid"], "default": True},  # ignored: that track is left out
        ],
    )
    assert job["status"] == "done", job
    assert job["title"] == "Save a copy without some tracks"
    assert job["message"] == (
        f"Copy saved as “{COPY}” (3 tracks left out). Your original wasn't changed."
    )
    assert job["result"] == {"copy": COPY, "source": FILE}

    # The original is untouched.
    assert (_hash(original), original.stat().st_mtime) == before

    copy = library / FILM / COPY
    info = _mkvmerge(copy)
    props = [(t["type"], t["properties"]["language"]) for t in info["tracks"]]
    assert props == [
        ("video", "und"),
        ("audio", "eng"),
        ("audio", "fre"),
        ("subtitles", "eng"),
        ("subtitles", "eng"),
    ]
    assert [t["properties"]["default_track"] for t in info["tracks"]] == [
        False,
        False,
        True,
        True,
        False,
    ]
    assert info["tracks"][2]["properties"]["track_name"] == "French"
    assert info["tracks"][4]["properties"]["forced_track"] is True
    source = _mkvmerge(original)
    assert (
        info["container"]["properties"]["duration"] == source["container"]["properties"]["duration"]
    )
    assert info["chapters"] == source["chapters"]
    assert len(info["attachments"]) == len(source["attachments"]) == 1
    assert info.get("global_tags") == source.get("global_tags")

    # Unraid permissions, and no temporary files left behind.
    umask = os.umask(0)
    os.umask(umask)
    assert copy.stat().st_mode & 0o777 == 0o666 & ~umask
    assert not [p for p in (library / FILM).iterdir() if p.name.startswith(".tailarr-tmp-")]

    # Tailarr remembers the copy, and the film page lists it straight away.
    with Session(_engine(app_client)) as session:
        record = session.get(CopyRecord, str(copy))
        assert record is not None and record.source_path == str(original)
    files = app_client.get(f"/api/films/{film_id}").json()["files"]
    assert [f["name"] for f in files] == [FILE, COPY]
    assert files[1]["is_copy"] is True
    assert files[1]["copy_of"] == FILE
    assert files[1]["can_replace_original"] is True
    assert files[1]["media"]["read"] is True
    assert files[0]["copy_of"] is None and files[0]["can_replace_original"] is False


def test_existing_copy_is_only_replaced_when_asked(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client)
    assert _make_copy(app_client, film_id)["status"] == "done"
    copy = library / FILM / COPY
    first = _hash(copy)

    preview = app_client.post(
        f"/api/films/{film_id}/remove-tracks/preview", json=_remove_body(app_client, film_id)
    ).json()
    assert preview["exists"] is True
    refused = app_client.post(
        f"/api/films/{film_id}/remove-tracks",
        json=_remove_body(app_client, film_id, confirmed=True),
    )
    assert refused.status_code == 409
    assert "Replace the existing copy" in refused.json()["detail"]

    tracks = _tracks(app_client, film_id)
    body = _remove_body(app_client, film_id, confirmed=True, overwrite=True)
    body["changes"] = [{"uid": _by_type(tracks, "audio")[0]["uid"], "name": "Main"}]
    job = _wait(
        app_client, app_client.post(f"/api/films/{film_id}/remove-tracks", json=body).json()["id"]
    )
    assert job["status"] == "done"
    assert _hash(copy) != first
    assert _mkvmerge(copy)["tracks"][1]["properties"]["track_name"] == "Main"


def test_a_file_that_is_not_a_tailarr_copy_is_never_replaced(
    app_client: TestClient, library: Path
) -> None:
    """A job queued earlier finds someone else's file under the copy's name: it stops."""
    film_id = _film_id(app_client)
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    queue.stop()
    response = app_client.post(
        f"/api/films/{film_id}/remove-tracks",
        json=_remove_body(app_client, film_id, confirmed=True),
    )
    assert response.status_code == 202
    copy = library / FILM / COPY
    copy.write_bytes(b"made by someone else")
    queue.start()
    job = _wait(app_client, response.json()["id"])
    assert job["status"] == "failed"
    assert "already exists" in job["error"]
    assert copy.read_bytes() == b"made by someone else"


def test_copy_of_a_tailarr_copy_updates_it(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client)
    assert _make_copy(app_client, film_id)["status"] == "done"
    copy_tracks = _tracks(app_client, film_id, COPY)
    english_subs = _by_type(copy_tracks, "subtitles")[0]
    body = {"file": COPY, "remove": [english_subs["uid"]]}
    preview = app_client.post(f"/api/films/{film_id}/remove-tracks/preview", json=body).json()
    assert preview["new_file"] == COPY
    assert preview["updates_copy"] is True
    job = _wait(
        app_client,
        app_client.post(
            f"/api/films/{film_id}/remove-tracks",
            json={**body, "confirmed": True, "overwrite": True},
        ).json()["id"],
    )
    assert job["status"] == "done", job
    assert "Copy updated" in job["message"]
    assert len(_mkvmerge(library / FILM / COPY)["tracks"]) == 4
    # Still known as a copy of the original, so it can still replace it.
    files = app_client.get(f"/api/films/{film_id}").json()["files"]
    assert files[1]["copy_of"] == FILE and files[1]["can_replace_original"] is True


def test_a_copy_that_fails_its_check_is_thrown_away(
    app_client: TestClient, library: Path, monkeypatch
) -> None:
    monkeypatch.setattr(remove_tracks, "verify_copy", lambda copy, plan: ["Length: 1 s"])
    film_id = _film_id(app_client)
    job = _make_copy(app_client, film_id)
    assert job["status"] == "failed"
    assert "thrown away" in job["error"]
    assert job["error_details"] == "Length: 1 s"
    assert sorted(p.name for p in (library / FILM).iterdir()) == [FILE]


def test_not_enough_space(app_client: TestClient, monkeypatch) -> None:
    from tailarr.api import actions

    monkeypatch.setattr(actions, "free_space", lambda path: 1000)
    film_id = _film_id(app_client)
    preview = app_client.post(
        f"/api/films/{film_id}/remove-tracks/preview", json=_remove_body(app_client, film_id)
    ).json()
    assert preview["enough_space"] is False
    response = app_client.post(
        f"/api/films/{film_id}/remove-tracks",
        json=_remove_body(app_client, film_id, confirmed=True),
    )
    assert response.status_code == 507


def test_place_new_file(tmp_path: Path) -> None:
    temp = tmp_path / ".tailarr-tmp-1-1.mkv"
    final = tmp_path / "Film - Tailarr.mkv"
    temp.write_bytes(b"new")
    final.write_bytes(b"old")
    with pytest.raises(JobFailed):
        place_new_file(temp, final, overwrite=False)
    assert final.read_bytes() == b"old" and temp.exists()
    place_new_file(temp, final, overwrite=True)
    assert final.read_bytes() == b"new" and not temp.exists()
    temp.write_bytes(b"newer")
    other = tmp_path / "Other - Tailarr.mkv"
    place_new_file(temp, other, overwrite=False)
    assert other.read_bytes() == b"newer" and not temp.exists()
    assert other.stat().st_nlink == 1


# -- replacing the original ----------------------------------------------------------------


def _replace(client: TestClient, film_id: int, **body) -> dict:
    response = client.post(
        f"/api/films/{film_id}/replace-original",
        json={"copy_file": COPY, "confirmed": True, "understood": True, **body},
    )
    assert response.status_code == 202, response.text
    return _wait(client, response.json()["id"])


def test_replace_the_original(app_client: TestClient, library: Path, tmp_path: Path) -> None:
    film_id = _film_id(app_client)
    original = library / FILM / FILE
    seeding = tmp_path / "data" / "torrents" / "movies" / "Sample.Film.mkv"
    seeding.parent.mkdir(parents=True)
    os.link(original, seeding)
    original_hash = _hash(original)
    assert _make_copy(app_client, film_id)["status"] == "done"
    copy_hash = _hash(library / FILM / COPY)

    preview = app_client.post(
        f"/api/films/{film_id}/replace-original/preview", json={"copy_file": COPY}
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["original"] == FILE and data["copy_file"] == COPY
    assert data["hardlinked"] is True
    assert data["keep_days"] == 30
    assert data["loses_dolby_vision"] is False
    assert data["recycle_folder"].endswith(f"{FILM}/{RECYCLE_FOLDER}")

    unconfirmed = app_client.post(
        f"/api/films/{film_id}/replace-original", json={"copy_file": COPY, "confirmed": True}
    )
    assert unconfirmed.status_code == 400

    job = _replace(app_client, film_id)
    assert job["status"] == "done", job
    assert "kept in the recycle folder for 30 days" in job["message"]

    # The copy now has the original's name; the original waits in the recycle folder.
    assert _hash(original) == copy_hash
    recycled = library / FILM / RECYCLE_FOLDER / FILE
    assert _hash(recycled) == original_hash
    assert not (library / FILM / COPY).exists()
    # The seeding copy in the downloads folder is untouched and still works.
    assert _hash(seeding) == original_hash
    assert seeding.stat().st_ino == recycled.stat().st_ino

    with Session(_engine(app_client)) as session:
        assert session.exec(select(CopyRecord)).all() == []
        rows = session.exec(select(RecycledFile)).all()
        assert [(r.path, r.original_path) for r in rows] == [(str(recycled), str(original))]

    # The film page shows one file, with the copy's tracks; the recycle folder isn't listed.
    detail = app_client.get(f"/api/films/{film_id}").json()
    assert [f["name"] for f in detail["files"]] == [FILE]
    assert len(_tracks(app_client, film_id)) == 5
    assert app_client.get("/api/settings/recycle").json() == {
        "keep_days": 30,
        "file_count": 1,
        "total_size": recycled.stat().st_size,
    }


def test_replace_refused_when_the_original_changed(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client)
    assert _make_copy(app_client, film_id)["status"] == "done"
    original = library / FILM / FILE
    os.utime(original, (time.time() + 60, time.time() + 60))  # e.g. Radarr upgraded it
    app_client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    files = app_client.get(f"/api/films/{film_id}").json()["files"]
    assert files[1]["can_replace_original"] is False
    response = app_client.post(
        f"/api/films/{film_id}/replace-original/preview", json={"copy_file": COPY}
    )
    assert response.status_code == 409
    assert "changed since this copy was made" in response.json()["detail"]


def test_replace_refused_for_unknown_copies(app_client: TestClient) -> None:
    film_id = _film_id(app_client, "Colour Test")
    copy = "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv"
    response = app_client.post(
        f"/api/films/{film_id}/replace-original/preview", json={"copy_file": copy}
    )
    assert response.status_code == 400
    assert "no record of making this copy" in response.json()["detail"]


def test_replace_puts_the_original_back_if_the_swap_fails(
    app_client: TestClient, library: Path, monkeypatch
) -> None:
    film_id = _film_id(app_client)
    assert _make_copy(app_client, film_id)["status"] == "done"
    original = library / FILM / FILE
    original_hash = _hash(original)
    real_rename = os.rename

    def failing_rename(src, dst):
        if str(src).endswith(COPY):
            raise PermissionError(13, "Permission denied")
        return real_rename(src, dst)

    monkeypatch.setattr(replace_original.os, "rename", failing_rename)
    job = _replace(app_client, film_id)
    assert job["status"] == "failed"
    assert "the original was put back" in job["error"]
    assert _hash(original) == original_hash
    assert (library / FILM / COPY).exists()
    with Session(_engine(app_client)) as session:
        assert session.exec(select(RecycledFile)).all() == []
        assert session.get(CopyRecord, str(library / FILM / COPY)) is not None


def test_replace_interrupted_message() -> None:
    job_type = replace_original.make_job_type(None, lambda: [], lambda folder: None)  # type: ignore[arg-type]
    assert job_type.in_place and job_type.interrupted_message == replace_original.INTERRUPTED


# -- the recycle folder ---------------------------------------------------------------------


def test_recycle_names_never_clash(tmp_path: Path) -> None:
    original = tmp_path / "Film.mkv"
    assert recycle_path(original) == tmp_path / RECYCLE_FOLDER / "Film.mkv"
    (tmp_path / RECYCLE_FOLDER).mkdir()
    (tmp_path / RECYCLE_FOLDER / "Film.mkv").write_bytes(b"1")
    (tmp_path / RECYCLE_FOLDER / "Film (2).mkv").write_bytes(b"2")
    assert recycle_path(original) == tmp_path / RECYCLE_FOLDER / "Film (3).mkv"


def test_old_recycled_files_are_deleted(client: TestClient, library: Path, tmp_path: Path) -> None:
    engine = _engine(client)
    folder = library / FILM / RECYCLE_FOLDER
    folder.mkdir()
    old, new = folder / "old.mkv", folder / "new.mkv"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    outside = tmp_path / RECYCLE_FOLDER / "outside.mkv"  # not in the library: never deleted
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    now = time.time()
    with Session(engine) as session:
        for path, age_days in ((old, 31), (new, 29), (outside, 400)):
            session.add(
                RecycledFile(
                    path=str(path), original_path="/x", size=3, recycled_at=now - age_days * 86400
                )
            )
        session.commit()
    roots = [str(library)]
    assert clean_recycle(engine, roots, now) == 1
    assert not old.exists() and new.exists() and outside.exists()
    # A shorter keep period applies to what's already there.
    assert client.put("/api/settings/recycle", json={"keep_days": 7}).status_code == 200
    assert clean_recycle(engine, roots, now) == 1
    assert not new.exists()
    assert not folder.exists()  # the empty recycle folder is tidied away
    with Session(engine) as session:
        assert [r.path for r in session.exec(select(RecycledFile)).all()] == [str(outside)]


def test_recycle_settings_validation(client: TestClient) -> None:
    assert client.get("/api/settings/recycle").json()["keep_days"] == 30
    for bad in (0, 366):
        assert client.put("/api/settings/recycle", json={"keep_days": bad}).status_code == 422
    assert client.put("/api/settings/recycle", json={"keep_days": 90}).json()["keep_days"] == 90
    assert client.get("/api/settings/recycle").json()["keep_days"] == 90


def test_job_history_keeps_results(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    job = _make_copy(app_client, film_id)
    with Session(_engine(app_client)) as session:
        row = session.get(Job, job["id"])
        assert row is not None and row.status == JobStatus.DONE
        assert json.loads(row.result or "{}") == {"copy": COPY, "source": FILE}
