"""Removing Dolby Vision and changing tracks in one copy; batches that also update copies."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tailarr.core.config import AppConfig
from tailarr.jobs.models import CopyRecord
from tailarr.media.probe import describe, read_file

COLOUR = "Colour Test (2023)"
COLOUR_FILE = "Colour Test (2023) WEBDL-2160p DV HDR10.mkv"
ANOTHER = "Another Show (2022)"


@pytest.fixture
def app_client(client: TestClient, samples_dir: Path, config: AppConfig):
    for name, target in (("movies", config.default_movies_dir), ("tv", config.default_tv_dir)):
        shutil.rmtree(target)
        shutil.copytree(samples_dir / "data" / "media" / name, target, symlinks=True)
    state = client.app.state  # type: ignore[attr-defined]
    state.film_scanner.run()
    state.tv_scanner.run()
    state.job_queue.start()
    yield client
    state.job_queue.stop()


def _wait_all(client: TestClient, timeout: float = 120) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()["jobs"]
        if all(j["status"] not in ("queued", "running") for j in jobs):
            return jobs
        time.sleep(0.1)
    raise AssertionError("jobs didn't finish")


def _film_id(client: TestClient, folder: str) -> int:
    return next(
        f["id"] for f in client.get("/api/films").json()["films"] if f["folder_name"] == folder
    )


def test_hdr10_copy_with_track_changes_in_one_go(app_client: TestClient, config) -> None:
    film = _film_id(app_client, COLOUR)
    media = app_client.get(f"/api/films/{film}/media?file={COLOUR_FILE}").json()
    french = next(t for t in media["tracks"] if t["language"] == "fre")
    forced = next(t for t in media["tracks"] if t["type"] == "subtitles" and t["forced"])
    body = {
        "file": COLOUR_FILE,
        "remove": [forced["uid"]],
        "changes": [{"uid": french["uid"], "default": True, "name": "French 5.1"}],
    }
    preview = app_client.post(f"/api/films/{film}/hdr10-copy/preview", json=body).json()
    assert len(preview["removed"]) == 1 and "Subtitles 2" in preview["removed"][0]
    assert preview["settings"][0]["label"].startswith("Audio 2")
    job = app_client.post(
        f"/api/films/{film}/hdr10-copy", json={**body, "confirmed": True, "overwrite": True}
    ).json()
    assert _wait_all(app_client)[0]["status"] == "done", job
    copy = Path(config.default_movies_dir) / COLOUR / COLOUR_FILE.replace(".mkv", " - HDR10.mkv")
    details = describe(read_file(copy))
    assert "Dolby Vision" not in details.hdr.formats
    assert [t.uid for t in details.of_type("subtitles")] == [
        t["uid"] for t in media["tracks"] if t["type"] == "subtitles" and not t["forced"]
    ]
    new_french = next(t for t in details.tracks if t.uid == french["uid"])
    assert (new_french.default, new_french.name) == (True, "French 5.1")


def test_hdr10_copy_refuses_removing_all_audio(app_client: TestClient) -> None:
    film = _film_id(app_client, COLOUR)
    media = app_client.get(f"/api/films/{film}/media?file={COLOUR_FILE}").json()
    audio = [t["uid"] for t in media["tracks"] if t["type"] == "audio"]
    refused = app_client.post(
        f"/api/films/{film}/hdr10-copy/preview", json={"file": COLOUR_FILE, "remove": audio}
    )
    assert refused.status_code == 400 and "no sound" in refused.json()["detail"]


def _show(client: TestClient, title: str) -> dict:
    shows = client.get("/api/tv").json()["shows"]
    return next(s for s in shows if s["title"] == title)


def _record_copy(client: TestClient, original: Path, copy: Path, kind: str) -> None:
    stat = original.stat()
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        session.add(
            CopyRecord(
                path=str(copy),
                source_path=str(original),
                source_size=stat.st_size,
                source_mtime=stat.st_mtime,
                kind=kind,
                created_at=time.time(),
            )
        )
        session.commit()


def test_batch_can_also_update_copies(app_client: TestClient, config) -> None:
    season = Path(config.default_tv_dir) / ANOTHER / "Season 01"
    original = season / "Another Show (2022) - S01E01 - Start.mkv"
    copy = season / "Another Show (2022) - S01E01 - Start - HDR10.mkv"
    _record_copy(app_client, original, copy, "hdr10_copy")
    show = _show(app_client, "Another Show")
    body = {
        "season": 1,
        "action": {"type": "default_tracks", "audio_language": "fre"},
        "allow_hardlinked": True,
    }
    without = app_client.post(f"/api/tv/shows/{show['id']}/batch/preview", json=body).json()
    assert without["copies"] == 1
    assert not any(f["is_copy"] for f in without["files"])
    preview = app_client.post(
        f"/api/tv/shows/{show['id']}/batch/preview", json={**body, "include_copies": True}
    ).json()
    copies = [f for f in preview["files"] if f["is_copy"]]
    assert [c["label"] for c in copies] == ["S01E01 – Start (Tailarr's copy)"]
    assert copies[0]["will_run"] is True
    started = app_client.post(
        f"/api/tv/shows/{show['id']}/batch",
        json={**body, "include_copies": True, "confirmed": True},
    ).json()
    assert started["jobs"] == preview["will_run"]
    assert all(j["status"] == "done" for j in _wait_all(app_client))
    for path in (original, copy):
        french = next(t for t in describe(read_file(path)).of_type("audio") if t.language == "fre")
        assert french.default is True, path


def test_hdr10_batch_with_tracks_updates_existing_copies(app_client: TestClient, config) -> None:
    """DV already removed before: "also change copies" brings the copy's tracks in line."""
    season = Path(config.default_tv_dir) / ANOTHER / "Season 01"
    original = season / "Another Show (2022) - S01E01 - Start.mkv"
    copy = season / "Another Show (2022) - S01E01 - Start - HDR10.mkv"
    _record_copy(app_client, original, copy, "hdr10_copy")
    show = _show(app_client, "Another Show")
    action = {
        "type": "hdr10_copy",
        "default_audio": "fre",
        "subtitles": {"mode": "only", "languages": ["eng"]},
    }
    preview = app_client.post(
        f"/api/tv/shows/{show['id']}/batch/preview",
        json={"season": 1, "action": action, "include_copies": True},
    ).json()
    assert preview["action"].startswith("Make a copy without Dolby Vision (HDR10 copy), ")
    assert "French audio as the default" in preview["action"]
    by_label = {f["label"]: f for f in preview["files"]}
    assert "already exists" in by_label["S01E01 – Start"]["reason"]
    assert by_label["S01E01 – Start (Tailarr's copy)"]["will_run"] is True
    assert by_label["S01E02 – Middle"]["will_run"] is True  # a new HDR10 copy with French default
    app_client.post(
        f"/api/tv/shows/{show['id']}/batch",
        json={"season": 1, "action": action, "include_copies": True, "confirmed": True},
    )
    assert all(j["status"] == "done" for j in _wait_all(app_client))
    updated = describe(read_file(copy))
    assert next(t for t in updated.of_type("audio") if t.language == "fre").default is True
    middle = season / "Another Show (2022) - S01E02 - Middle - HDR10.mkv"
    made = describe(read_file(middle))
    assert "Dolby Vision" not in made.hdr.formats
    assert next(t for t in made.of_type("audio") if t.language == "fre").default is True


def test_files_left_without_subtitles_are_flagged(app_client: TestClient) -> None:
    show = _show(app_client, "Test Show")
    preview = app_client.post(
        f"/api/tv/shows/{show['id']}/batch/preview",
        json={
            "season": 1,
            "action": {
                "type": "remove_tracks",
                "subtitles": {"mode": "only", "languages": ["jpn"]},
            },
        },
    ).json()
    flagged = [f for f in preview["files"] if f["warnings"]]
    assert [f["label"] for f in flagged] == ["S01E03 – Many Voices"]
    assert flagged[0]["warnings"] == ["No subtitles would be left in this file."]
    assert preview["flagged"] == 1
    no_audio = app_client.post(
        f"/api/tv/shows/{show['id']}/batch/preview",
        json={
            "season": 1,
            "action": {"type": "remove_tracks", "audio": {"mode": "only", "languages": ["kor"]}},
        },
    ).json()
    assert all(
        f["reason"] == "No audio tracks would be left, so this file is skipped."
        for f in no_audio["files"]
    )
    assert no_audio["flagged"] == 3


def test_change_many_films_at_once(app_client: TestClient, config) -> None:
    films = {f["folder_name"]: f["id"] for f in app_client.get("/api/films").json()["films"]}
    chosen = [
        films[COLOUR],
        films["Blu-ray Night (2018) {imdb-tt0000001}"],
        films["Bright Lights (2019)"],
    ]
    body = {"film_ids": chosen, "action": {"type": "hdr10_copy"}}
    preview = app_client.post("/api/films/batch/preview", json=body).json()
    assert preview["scope"] == "3 films"
    by_label = {f["label"]: f for f in preview["files"]}
    assert by_label["Blu-ray Night (2018)"]["will_run"] is True
    assert "already exists" in by_label["Colour Test (2023)"]["reason"]
    assert "no Dolby Vision" in by_label["Bright Lights (2019)"]["reason"]
    assert all(f["kind"] == "film" for f in preview["files"])
    assert preview["copies"] == 1  # Colour Test's HDR10 copy
    one = app_client.post(
        "/api/films/batch/preview", json={**body, "film_ids": [films[COLOUR]]}
    ).json()
    assert one["scope"] == "Colour Test (2023)"
    assert app_client.post("/api/films/batch", json=body).status_code == 400  # not confirmed
    started = app_client.post("/api/films/batch", json={**body, "confirmed": True}).json()
    assert started["jobs"] == 1
    jobs = _wait_all(app_client)
    assert [j["status"] for j in jobs] == ["done"] and jobs[0]["film_id"] == chosen[1]
    assert (
        app_client.post("/api/films/batch/preview", json={**body, "film_ids": [999999]}).status_code
        == 404
    )
