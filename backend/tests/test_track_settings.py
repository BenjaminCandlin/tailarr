"""Changing default/forced flags and track names in place, with real mkvpropedit."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tailarr.core.config import AppConfig
from tailarr.jobs.engine import JobQueue
from tailarr.jobs.models import JobStatus

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


def _film_id(client: TestClient, title: str = "Sample Multi-Language Film") -> int:
    films = client.get("/api/films").json()["films"]
    return next(f["id"] for f in films if f["title"] == title)


def _tracks(client: TestClient, film_id: int, file: str = FILE) -> list[dict]:
    return client.get(f"/api/films/{film_id}/media", params={"file": file}).json()["tracks"]


def _mkvmerge_tracks(path: Path) -> list[dict]:
    env = {**os.environ, "LC_ALL": "C.UTF-8"}
    out = subprocess.run(["mkvmerge", "-J", str(path)], capture_output=True, env=env, check=True)
    return [t["properties"] for t in json.loads(out.stdout)["tracks"]]


def _wait(client: TestClient, job_id: int, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def _by_type(tracks: list[dict], kind: str) -> list[dict]:
    return [t for t in tracks if t["type"] == kind]


def test_tracks_have_unique_ids(app_client: TestClient) -> None:
    tracks = _tracks(app_client, _film_id(app_client))
    uids = [t["uid"] for t in tracks]
    assert all(uid.isdigit() for uid in uids)
    assert len(set(uids)) == len(uids)


def test_preview_describes_changes_and_changes_nothing(
    app_client: TestClient, library: Path
) -> None:
    film_id = _film_id(app_client)
    path = library / FILM / FILE
    before = (path.stat().st_mtime, path.read_bytes())
    tracks = _tracks(app_client, film_id)
    english_audio, french_audio, _ = _by_type(tracks, "audio")
    subs = _by_type(tracks, "subtitles")
    body = {
        "file": FILE,
        "changes": [
            {"uid": english_audio["uid"], "default": False},
            {"uid": french_audio["uid"], "default": True, "name": "French"},
            {"uid": subs[2]["uid"], "forced": True, "name": ""},
            {"uid": subs[0]["uid"], "default": True},  # already the default: nothing to do
        ],
    }
    preview = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=body)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["file"] == FILE
    assert data["hardlinked"] is False
    assert data["free_space"] > 0
    assert [(t["label"], t["changes"]) for t in data["tracks"]] == [
        ("Audio 1: English", ["Stop it being the default"]),
        (
            "Audio 2: French",
            ["Make it the default", "Rename it from “Français 5.1” to “French”"],
        ),
        (
            "Subtitles 3: French",
            [
                "Mark it as forced (shown even when subtitles are off)",
                "Remove its name “Français”",
            ],
        ),
    ]
    assert (path.stat().st_mtime, path.read_bytes()) == before


def test_saving_needs_confirmation(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    audio = _by_type(_tracks(app_client, film_id), "audio")[1]
    body = {"file": FILE, "changes": [{"uid": audio["uid"], "default": True}]}
    response = app_client.post(f"/api/films/{film_id}/track-settings", json=body)
    assert response.status_code == 400
    assert "needs your confirmation" in response.json()["detail"]
    assert app_client.get("/api/jobs").json()["jobs"] == []


def test_change_flags_and_names(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client)
    path = library / FILM / FILE
    size_before = path.stat().st_size
    mode_before = path.stat().st_mode
    tracks = _tracks(app_client, film_id)
    english_audio, french_audio, japanese_audio = _by_type(tracks, "audio")
    subs = _by_type(tracks, "subtitles")
    body = {
        "file": FILE,
        "confirmed": True,
        "changes": [
            {"uid": english_audio["uid"], "default": False},
            {"uid": japanese_audio["uid"], "default": True, "name": "日本語 — Japanese"},
            {"uid": subs[0]["uid"], "default": False},
            {"uid": subs[1]["uid"], "forced": False, "name": ""},
            {"uid": subs[3]["uid"], "forced": True},
        ],
    }
    response = app_client.post(f"/api/films/{film_id}/track-settings", json=body)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["title"] == "Change track settings"
    assert job["subject"] == "Sample Multi-Language Film (2021)"
    assert job["file_name"] == FILE

    finished = _wait(app_client, job["id"])
    assert finished["status"] == "done", finished
    assert finished["message"].startswith("5 tracks changed.")
    assert finished["step_count"] == 3

    # The real file has the new settings, and nothing else changed.
    props = _mkvmerge_tracks(path)
    assert [p["default_track"] for p in props] == [
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert [p.get("forced_track", False) for p in props] == [
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        True,
    ]
    assert props[3]["track_name"] == "日本語 — Japanese"
    assert "track_name" not in props[5]
    assert path.stat().st_size == size_before
    assert path.stat().st_mode == mode_before

    # The film page shows the new settings straight away (no re-scan needed).
    fresh = _tracks(app_client, film_id)
    assert [t["default"] for t in fresh] == [p["default_track"] for p in props]
    detail = app_client.get(f"/api/films/{film_id}").json()
    assert detail["files"][0]["media"]["read"] is True


def test_nothing_to_change(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    audio = _by_type(_tracks(app_client, film_id), "audio")[0]
    body = {"file": FILE, "confirmed": True, "changes": [{"uid": audio["uid"], "default": True}]}
    response = app_client.post(f"/api/films/{film_id}/track-settings", json=body)
    assert response.status_code == 400
    assert "already have these settings" in response.json()["detail"]
    empty = {"file": FILE, "confirmed": True, "changes": []}
    assert app_client.post(f"/api/films/{film_id}/track-settings", json=empty).status_code == 400


def test_unknown_track_is_refused(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    body = {"file": FILE, "changes": [{"uid": "123", "default": True}]}
    response = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=body)
    assert response.status_code == 409
    assert "tracks in this file have changed" in response.json()["detail"]


def test_bad_names_are_refused(app_client: TestClient) -> None:
    film_id = _film_id(app_client)
    uid = _tracks(app_client, film_id)[1]["uid"]
    for name in ("x" * 201, "bell\x07"):
        body = {"file": FILE, "changes": [{"uid": uid, "name": name}]}
        response = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=body)
        assert response.status_code == 422
    # Line breaks and extra spaces are tidied rather than refused.
    body = {"file": FILE, "changes": [{"uid": uid, "name": "  Main\n  audio "}]}
    response = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=body)
    assert "“Main audio”" in response.json()["tracks"][0]["changes"][0]


def test_only_mkv_files_in_the_film(app_client: TestClient) -> None:
    film_id = _film_id(app_client, "Old Home Video")
    detail = app_client.get(f"/api/films/{film_id}").json()
    body = {"file": detail["main_file"], "changes": [{"uid": "1", "default": True}]}
    response = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=body)
    assert response.status_code == 400
    assert "only change MKV files" in response.json()["detail"]
    other = {"file": "../../../etc/passwd", "changes": [{"uid": "1", "default": True}]}
    response = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=other)
    assert response.status_code == 404


def test_hardlinked_file_needs_i_understand(
    app_client: TestClient, library: Path, tmp_path: Path
) -> None:
    path = library / FILM / FILE
    seeding = tmp_path / "data" / "torrents" / "movies" / "Sample.Film.mkv"
    seeding.parent.mkdir(parents=True)
    os.link(path, seeding)
    app_client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    film_id = _film_id(app_client)
    audio = _by_type(_tracks(app_client, film_id), "audio")[2]
    body = {"file": FILE, "changes": [{"uid": audio["uid"], "default": True}]}

    preview = app_client.post(f"/api/films/{film_id}/track-settings/preview", json=body).json()
    assert preview["hardlinked"] is True

    refused = app_client.post(
        f"/api/films/{film_id}/track-settings", json={**body, "confirmed": True}
    )
    assert refused.status_code == 409
    assert "also in your downloads" in refused.json()["detail"]
    assert app_client.get("/api/jobs").json()["jobs"] == []

    allowed = app_client.post(
        f"/api/films/{film_id}/track-settings",
        json={**body, "confirmed": True, "allow_hardlinked": True},
    )
    assert allowed.status_code == 202
    assert _wait(app_client, allowed.json()["id"])["status"] == "done"
    # Both names are the same file, so the seeding copy changed too (that's what the warning says).
    assert _mkvmerge_tracks(seeding)[3]["default_track"] is True
    assert seeding.stat().st_ino == path.stat().st_ino


def test_job_refuses_a_file_that_became_hardlinked(
    app_client: TestClient, library: Path, tmp_path: Path
) -> None:
    """The check is repeated when the job runs, not only when it's requested."""
    film_id = _film_id(app_client)
    audio = _by_type(_tracks(app_client, film_id), "audio")[2]
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    queue.stop()
    response = app_client.post(
        f"/api/films/{film_id}/track-settings",
        json={"file": FILE, "confirmed": True, "changes": [{"uid": audio["uid"], "default": True}]},
    )
    path = library / FILM / FILE
    os.link(path, tmp_path / "seeding.mkv")
    queue.start()
    job = _wait(app_client, response.json()["id"])
    assert job["status"] == "failed"
    assert "also in your downloads" in job["error"]
    assert _mkvmerge_tracks(path)[3]["default_track"] is False


def test_job_notices_a_replaced_file(app_client: TestClient, library: Path, samples_dir) -> None:
    """If Radarr replaces the file before the job runs, no track of the new file is touched."""
    film_id = _film_id(app_client)
    audio = _by_type(_tracks(app_client, film_id), "audio")[2]
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    queue.stop()
    response = app_client.post(
        f"/api/films/{film_id}/track-settings",
        json={"file": FILE, "confirmed": True, "changes": [{"uid": audio["uid"], "default": True}]},
    )
    path = library / FILM / FILE
    shutil.copy(samples_dir / "files" / "sdr_2997.mkv", path)
    before = path.read_bytes()
    queue.start()
    job = _wait(app_client, response.json()["id"])
    assert job["status"] == "failed"
    assert "tracks in this file have changed" in job["error"]
    assert path.read_bytes() == before


def test_job_refuses_files_outside_the_library(app_client: TestClient, tmp_path: Path) -> None:
    outside = tmp_path / "data" / "torrents" / "film.mkv"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"not really a film")
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    job = queue.submit(
        "track_settings",
        title="T",
        subject="S",
        path=str(outside),
        params={"changes": [{"uid": "1", "default": True}]},
    )
    finished = _wait(app_client, job.id)  # type: ignore[arg-type]
    assert finished["status"] == JobStatus.FAILED
    assert "isn't inside your Films or TV folder" in finished["error"]
    assert outside.read_bytes() == b"not really a film"
