"""Radarr, Sonarr and Plex: settings, tests, titles/posters, after-job calls and webhooks.

The apps are faked (tests/fake_apps.py); the media tools and files are real.
"""

from __future__ import annotations

import base64
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tailarr.core.config import AppConfig
from tailarr.jobs.models import CopyRecord, RecycledFile
from tailarr.main import create_app
from tests.conftest import page_client

from .fake_apps import PLEX_TOKEN, RADARR_KEY, SONARR_KEY, FakeApps, movie, series

COLOUR = "Colour Test (2023)"
COLOUR_FILE = "Colour Test (2023) WEBDL-2160p DV HDR10.mkv"
COLOUR_COPY = "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv"
STREAMING = "Streaming Only (2024)"
BRIGHT = "Bright Lights (2019)"


@pytest.fixture
def apps() -> FakeApps:
    return FakeApps(
        movies=[
            movie(1, "Colour Test", 2023, COLOUR),
            movie(2, "Streaming Only: The Film", 2024, STREAMING),
            movie(3, "Bright Lights", 2019, BRIGHT),
            movie(9, "Not In Tailarr's Folder", 2001, "../elsewhere/Film (2001)"),
        ],
        series=[series(7, "Another Show", 2022, "Another Show (2022)")],
    )


@pytest.fixture
def library(samples_dir: Path, config: AppConfig) -> tuple[Path, Path]:
    movies, tv = Path(config.default_movies_dir), Path(config.default_tv_dir)
    for target, name in ((movies, "movies"), (tv, "tv")):
        shutil.rmtree(target)
        shutil.copytree(samples_dir / "data" / "media" / name, target, symlinks=True)
    return movies, tv


@pytest.fixture
def app_client(config: AppConfig, apps: FakeApps, library):
    client = page_client(create_app(config, transport=apps.transport()))
    movies, tv = library
    client.put(
        "/api/settings/library",
        json={
            "movies_dir": str(movies),
            "tv_dir": str(tv),
            "path_mappings": [
                {"remote": "/movies", "local": str(movies)},
                {"remote": "/tv", "local": str(tv)},
                {"remote": "/media/movies", "local": str(movies)},
                {"remote": "/media/tv", "local": str(tv)},
            ],
        },
    )
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    queue = client.app.state.job_queue  # type: ignore[attr-defined]
    queue.start()
    yield client
    queue.stop()


def _connect(client: TestClient, **extra) -> dict:
    body = {
        "radarr": {"url": "http://radarr:7878", "api_key": RADARR_KEY},
        "sonarr": {"url": "sonarr:8989", "api_key": SONARR_KEY},
        "plex": {"url": "http://plex:32400/", "api_key": PLEX_TOKEN},
        **extra,
    }
    response = client.put("/api/settings/connections", json=body)
    assert response.status_code == 200, response.text
    client.app.state.connections.sync()  # type: ignore[attr-defined]
    return response.json()


def _wait(client: TestClient, job_id: int, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def _settle(seconds: float = 0.5) -> None:
    time.sleep(seconds)  # after-job calls run in the background


def _film(client: TestClient, folder: str) -> dict:
    films = client.get("/api/films").json()["films"]
    return next(f for f in films if f["folder_name"] == folder)


def _test(client: TestClient, service: str, url: str, key: str | None) -> dict:
    return client.post(
        "/api/settings/connections/test", json={"service": service, "url": url, "api_key": key}
    ).json()


# -- settings and tests ------------------------------------------------------------------------


def test_connection_tests_explain_problems(app_client: TestClient) -> None:
    ok = _test(app_client, "radarr", "http://radarr:7878", RADARR_KEY)
    assert ok == {
        "ok": True,
        "message": "Connected to Radarr 5.9.1. It has 4 films.",
        "details": None,
    }
    assert _test(app_client, "sonarr", "http://sonarr:8989", SONARR_KEY)["message"].endswith(
        "It has 1 shows."
    )
    assert _test(app_client, "plex", "http://plex:32400", PLEX_TOKEN)["message"] == (
        "Connected to Plex 1.41.0."
    )
    wrong_key = _test(app_client, "radarr", "http://radarr:7878", "nope")
    assert not wrong_key["ok"] and "refused the API key" in wrong_key["message"]
    wrong_app = _test(app_client, "radarr", "http://sonarr:8989", SONARR_KEY)
    assert "belongs to Sonarr, not Radarr" in wrong_app["message"]
    unknown = _test(app_client, "radarr", "http://unknown-container:7878", RADARR_KEY)
    assert "can't find “unknown-container”" in unknown["message"]
    assert "same custom Docker network" in unknown["message"]
    assert "http://radarr:7878" in unknown["message"]
    refused = _test(app_client, "sonarr", "http://refused:8989", SONARR_KEY)
    assert "didn't answer" in refused["message"] and "8989" in refused["message"]
    assert "Fill in" in _test(app_client, "plex", "", PLEX_TOKEN)["message"]
    bad_token = _test(app_client, "plex", "http://plex:32400", "wrong")
    assert "refused the token" in bad_token["message"]


def test_keys_are_saved_but_never_sent_back(app_client: TestClient, config: AppConfig) -> None:
    saved = _connect(app_client)
    assert saved["radarr"] == {"url": "http://radarr:7878", "has_key": True}
    assert saved["sonarr"]["url"] == "http://sonarr:8989"  # http:// added
    assert saved["plex"]["url"] == "http://plex:32400"  # trailing slash removed
    page = app_client.get("/api/settings/connections").text
    assert RADARR_KEY not in page and PLEX_TOKEN not in page
    # Leaving the key empty keeps the saved one; a test uses it too.
    again = app_client.put(
        "/api/settings/connections",
        json={"radarr": {"url": "http://radarr:7878"}, "plex": {"url": ""}},
    ).json()
    assert again["radarr"]["has_key"] is True
    assert again["plex"] == {"url": "", "has_key": False}  # clearing the address forgets it
    assert _test(app_client, "radarr", "http://radarr:7878", None)["ok"] is True
    # Keys live only in the database in /config.
    assert RADARR_KEY.encode() in (config.config_dir / "tailarr.db").read_bytes()


def test_webhook_secret_can_be_renewed(app_client: TestClient) -> None:
    first = app_client.get("/api/settings/connections").json()["webhook_paths"]["radarr"]
    assert first.startswith("/api/webhooks/radarr?secret=")
    second = app_client.post("/api/settings/connections/new-secret").json()
    assert second["webhook_paths"]["radarr"] != first
    assert app_client.post(first, json={"eventType": "Test"}).status_code == 401
    assert app_client.post(second["webhook_paths"]["radarr"], json={"eventType": "Test"}).json()[
        "ok"
    ]


def test_path_mapping_test(app_client: TestClient, library) -> None:
    movies, _ = library
    found = app_client.post(
        "/api/settings/path-mappings/test", json={"path": f"/movies/{COLOUR}"}
    ).json()
    assert found == {
        "path": str(movies / COLOUR),
        "exists": True,
        "inside_library": True,
        "message": "Found it. Tailarr can use this path.",
    }
    missing = app_client.post("/api/settings/path-mappings/test", json={"path": "/films/x"}).json()
    assert missing["exists"] is False and "Add or fix a path mapping" in missing["message"]


# -- titles and posters -------------------------------------------------------------------------


def test_titles_and_posters_come_from_radarr_and_sonarr(app_client: TestClient) -> None:
    before = _film(app_client, STREAMING)
    assert before["title"] == "Streaming Only" and before["poster_url"] is None
    _connect(app_client)
    status = app_client.get("/api/settings/connections").json()["sync"]
    assert (status["films"], status["shows"], status["errors"]) == (3, 1, None)

    film = _film(app_client, STREAMING)
    assert film["title"] == "Streaming Only: The Film"
    poster = app_client.get(film["poster_url"])
    assert poster.status_code == 200 and poster.headers["content-type"] == "image/jpeg"
    detail = app_client.get(f"/api/films/{film['id']}").json()
    assert app_client.get(detail["backdrop_url"]).status_code == 200
    small = app_client.get(film["poster_url"] + "&size=full")
    assert small.status_code == 200
    # A film with its own poster keeps it.
    colour = _film(app_client, COLOUR)
    assert app_client.get(colour["poster_url"]).headers["content-type"] == "image/jpeg"
    shows = app_client.get("/api/tv").json()["shows"]
    assert next(s for s in shows if s["folder_name"] == "Another Show (2022)")["year"] == 2022
    # Disconnecting Radarr forgets its titles.
    app_client.put("/api/settings/connections", json={"radarr": {"url": ""}})
    app_client.app.state.connections.sync()  # type: ignore[attr-defined]
    assert _film(app_client, STREAMING)["title"] == "Streaming Only"


# -- after jobs ----------------------------------------------------------------------------------


def test_plex_refresh_after_a_copy_but_no_rescan(app_client: TestClient, apps: FakeApps) -> None:
    _connect(app_client)
    film = _film(app_client, COLOUR)
    job = app_client.post(
        f"/api/films/{film['id']}/hdr10-copy",
        json={"file": COLOUR_FILE, "confirmed": True, "overwrite": True},
    ).json()
    assert _wait(app_client, job["id"])["status"] == "done"
    _settle()
    assert apps.plex_refreshes == [{"section": "1", "path": f"/media/movies/{COLOUR}"}]
    assert apps.commands == []  # Radarr ignores extra copies: no rescan
    activity = app_client.get("/api/activity").json()
    assert activity[0]["source"] == "plex" and "look at" in activity[0]["message"]


def test_rescan_after_an_original_changes(app_client: TestClient, apps: FakeApps) -> None:
    _connect(app_client)
    film = _film(app_client, BRIGHT)
    media = app_client.get(f"/api/films/{film['id']}/media").json()
    french = next(t for t in media["tracks"] if t["language"] == "fre")
    job = app_client.post(
        f"/api/films/{film['id']}/track-settings",
        json={
            "file": media["file"],
            "changes": [{"uid": french["uid"], "default": True}],
            "confirmed": True,
        },
    ).json()
    assert _wait(app_client, job["id"])["status"] == "done"
    _settle()
    assert apps.commands == [{"app": "radarr", "name": "RescanMovie", "movieId": 3}]
    assert len(apps.plex_refreshes) == 1


def test_no_calls_when_switched_off(app_client: TestClient, apps: FakeApps) -> None:
    _connect(app_client, plex_refresh=False, arr_rescan=False)
    film = _film(app_client, BRIGHT)
    media = app_client.get(f"/api/films/{film['id']}/media").json()
    french = next(t for t in media["tracks"] if t["language"] == "fre")
    job = app_client.post(
        f"/api/films/{film['id']}/track-settings",
        json={
            "file": media["file"],
            "changes": [{"uid": french["uid"], "default": True}],
            "confirmed": True,
        },
    ).json()
    assert _wait(app_client, job["id"])["status"] == "done"
    _settle()
    assert apps.commands == [] and apps.plex_refreshes == []


def test_plex_folders_that_dont_match_refresh_the_whole_section(
    app_client: TestClient, apps: FakeApps
) -> None:
    apps.plex_sections[0]["Location"] = [{"path": "/somewhere/else"}]
    _connect(app_client)
    assert app_client.app.state.connections.refresh_plex(  # type: ignore[attr-defined]
        str(Path(app_client.get("/api/films").json()["root"]) / COLOUR)
    )
    assert apps.plex_refreshes == [{"section": "1", "path": None}]
    assert "whole film library" in app_client.get("/api/activity").json()[0]["message"]


def test_replace_summary_warns_about_dolby_vision_upgrades(
    app_client: TestClient, library, config: AppConfig
) -> None:
    movies, _ = library
    film = _film(app_client, COLOUR)
    original = movies / COLOUR / COLOUR_FILE
    stat = original.stat()
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        session.add(
            CopyRecord(
                path=str(movies / COLOUR / COLOUR_COPY),
                source_path=str(original),
                source_size=stat.st_size,
                source_mtime=stat.st_mtime,
                kind="hdr10_copy",
                created_at=time.time(),
            )
        )
        session.commit()
    url = f"/api/films/{film['id']}/replace-original/preview"
    assert app_client.post(url, json={"copy_file": COLOUR_COPY}).json()["may_redownload"] is None
    _connect(app_client)
    assert app_client.post(url, json={"copy_file": COLOUR_COPY}).json()["may_redownload"] == (
        "Radarr"
    )


# -- webhooks ------------------------------------------------------------------------------------


def _hook(client: TestClient, service: str, payload: dict, **kwargs):
    path = client.get("/api/settings/connections").json()["webhook_paths"][service]
    return client.post(path, json=payload, **kwargs)


def _record_copy(client: TestClient, original: Path, copy: Path, kind: str = "hdr10_copy") -> None:
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


def test_webhooks_need_the_secret(app_client: TestClient) -> None:
    assert app_client.post("/api/webhooks/radarr", json={"eventType": "Test"}).status_code == 401
    wrong = app_client.post("/api/webhooks/radarr?secret=nope", json={"eventType": "Test"})
    assert wrong.status_code == 401 and "Wrong or missing secret" in wrong.json()["detail"]
    test = _hook(app_client, "radarr", {"eventType": "Test"})
    assert test.json() == {
        "ok": True,
        "message": "Radarr sent a test message. The connection works.",
    }
    secret = (
        app_client.get("/api/settings/connections").json()["webhook_paths"]["radarr"].split("=")[1]
    )
    basic = base64.b64encode(f"tailarr:{secret}".encode()).decode()
    via_password = app_client.post(
        "/api/webhooks/sonarr",
        json={"eventType": "Test"},
        headers={"Authorization": f"Basic {basic}"},
    )
    assert via_password.status_code == 200
    via_header = app_client.post(
        "/api/webhooks/sonarr", json={"eventType": "Test"}, headers={"X-Tailarr-Secret": secret}
    )
    assert via_header.status_code == 200


def test_upgrade_moves_old_copies_to_the_recycle_folder(app_client: TestClient, library) -> None:
    movies, _ = library
    folder = movies / COLOUR
    original, copy = folder / COLOUR_FILE, folder / COLOUR_COPY
    _record_copy(app_client, original, copy)
    # Radarr imports a better release and deletes the old file.
    new = folder / "Colour Test (2023) Remux-2160p.mkv"
    os.link(original, new)  # (stand-in for the new download)
    original.unlink()
    response = _hook(
        app_client,
        "radarr",
        {
            "eventType": "Download",
            "isUpgrade": True,
            "movie": {"folderPath": f"/movies/{COLOUR}"},
            "movieFile": {"path": f"/movies/{COLOUR}/{new.name}"},
            "deletedFiles": [{"path": f"/movies/{COLOUR}/{COLOUR_FILE}"}],
        },
    ).json()
    assert "imported an upgrade" in response["message"]
    assert "1 Tailarr copy of the old file moved to the recycle folder" in response["message"]
    assert not copy.exists()
    assert (folder / ".tailarr-recycle" / COLOUR_COPY).exists()
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        assert session.exec(select(CopyRecord)).all() == []
        assert len(session.exec(select(RecycledFile)).all()) == 1
    # The film page shows the new file straight away.
    names = [
        f["name"]
        for f in app_client.get(f"/api/films/{_film(app_client, COLOUR)['id']}").json()["files"]
    ]
    assert names == [new.name]
    kinds = [a["kind"] for a in app_client.get("/api/activity").json()]
    assert "copy-tidied" in kinds and "webhook" in kinds


def test_copies_are_kept_when_the_original_is_still_there(app_client: TestClient, library) -> None:
    movies, _ = library
    folder = movies / COLOUR
    _record_copy(app_client, folder / COLOUR_FILE, folder / COLOUR_COPY)
    _hook(
        app_client,
        "radarr",
        {
            "eventType": "MovieFileDelete",
            "deleteReason": "upgrade",
            "movieFile": {"path": f"/movies/{COLOUR}/{COLOUR_FILE}"},
        },
    )
    assert (folder / COLOUR_COPY).exists()


def test_tidying_can_be_switched_off(app_client: TestClient, library) -> None:
    movies, _ = library
    folder = movies / COLOUR
    _record_copy(app_client, folder / COLOUR_FILE, folder / COLOUR_COPY)
    _connect(app_client, tidy_copies=False)
    (folder / COLOUR_FILE).unlink()
    _hook(
        app_client,
        "radarr",
        {"eventType": "MovieFileDelete", "movieFile": {"path": f"/movies/{COLOUR}/{COLOUR_FILE}"}},
    )
    assert (folder / COLOUR_COPY).exists()


def test_hardlinked_copies_are_never_moved(app_client: TestClient, library, tmp_path: Path) -> None:
    movies, _ = library
    folder = movies / COLOUR
    copy = folder / COLOUR_COPY
    _record_copy(app_client, folder / COLOUR_FILE, copy)
    os.link(copy, tmp_path / "elsewhere.mkv")
    (folder / COLOUR_FILE).unlink()
    _hook(
        app_client,
        "radarr",
        {"eventType": "MovieFileDelete", "movieFile": {"path": f"/movies/{COLOUR}/{COLOUR_FILE}"}},
    )
    assert copy.exists()
    assert any("hardlinked" in a["message"] for a in app_client.get("/api/activity").json())


def test_rename_renames_copies(app_client: TestClient, library) -> None:
    movies, _ = library
    folder = movies / COLOUR
    original, copy = folder / COLOUR_FILE, folder / COLOUR_COPY
    _record_copy(app_client, original, copy)
    # A copy made from the copy (tracks removed from the HDR10 copy).
    second = folder / "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10 - Tailarr.mkv"
    shutil.copy(copy, second)
    _record_copy(app_client, copy, second, kind="remove_tracks")
    renamed = folder / "Colour Test (2023) {tmdb-1} Remux.mkv"
    original.rename(renamed)
    result = _hook(
        app_client,
        "radarr",
        {
            "eventType": "Rename",
            "renamedMovieFiles": [
                {
                    "previousPath": f"/movies/{COLOUR}/{COLOUR_FILE}",
                    "path": f"/movies/{COLOUR}/{renamed.name}",
                }
            ],
        },
    ).json()
    assert "2 Tailarr copies renamed to match" in result["message"]
    new_copy = folder / "Colour Test (2023) {tmdb-1} Remux - HDR10.mkv"
    new_second = folder / "Colour Test (2023) {tmdb-1} Remux - HDR10 - Tailarr.mkv"
    assert new_copy.exists() and new_second.exists() and not copy.exists()
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        records = {r.path: r.source_path for r in session.exec(select(CopyRecord))}
    assert records == {str(new_copy): str(renamed), str(new_second): str(new_copy)}


def test_import_of_a_new_episode_shows_up_at_once(app_client: TestClient, library) -> None:
    _, tv = library
    season = tv / "Test Show" / "Season 02"
    shutil.copy(
        season / "Test Show - S02E01 - Brighter.mkv", season / "Test Show - S02E02 - Later.mkv"
    )
    result = _hook(
        app_client,
        "sonarr",
        {
            "eventType": "Download",
            "series": {"path": "/tv/Test Show"},
            "episodeFile": {"path": "/tv/Test Show/Season 02/Test Show - S02E02 - Later.mkv"},
        },
    ).json()
    assert "imported a new file" in result["message"]
    shows = app_client.get("/api/tv").json()["shows"]
    test_show = next(s for s in shows if s["title"] == "Test Show")
    assert test_show["episode_count"] == 6


def test_activity_list(app_client: TestClient) -> None:
    _hook(app_client, "radarr", {"eventType": "Test"})
    _hook(app_client, "sonarr", {"eventType": "Test"})
    entries = app_client.get("/api/activity?limit=1").json()
    assert len(entries) == 1 and entries[0]["source"] == "sonarr"
    radarr = app_client.get("/api/activity?source=radarr").json()
    assert [e["source"] for e in radarr] == ["radarr"]


def test_repeated_test_messages_are_logged_once(app_client: TestClient) -> None:
    # Radarr sends one when "Test" is pressed and another when the connection is saved.
    _hook(app_client, "radarr", {"eventType": "Test"})
    _hook(app_client, "radarr", {"eventType": "Test"})
    _hook(app_client, "sonarr", {"eventType": "Test"})
    messages = [a["message"] for a in app_client.get("/api/activity").json()]
    assert messages.count("Radarr sent a test message. The connection works.") == 1
    assert messages.count("Sonarr sent a test message. The connection works.") == 1
