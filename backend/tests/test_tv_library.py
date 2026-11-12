"""The TV library: names, scanning, pages, episode actions and batch actions."""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tailarr.actions.plans import (
    DefaultTracksAction,
    Hdr10CopyAction,
    LanguageChoice,
    RemoveTracksAction,
    describe_action,
)
from tailarr.core.config import AppConfig
from tailarr.core.db import make_engine
from tailarr.jobs.engine import JobQueue
from tailarr.library.tv_naming import (
    episode_label,
    parse_episode,
    parse_show_folder,
    season_of_folder,
    strip_copy_suffix,
)
from tailarr.media.languages import normalize_language

ANOTHER = "Another Show"
TEST_SHOW = "Test Show"
S01E02 = "Another Show (2022) - S01E02 - Middle.mkv"


# -- names ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "season", "episode", "end", "title"),
    [
        ("Show (2020) - S01E02 - The Title.mkv", 1, 2, None, "The Title"),
        ("Show - S01E01-E02 - Double.mkv", 1, 1, 2, "Double"),
        ("Show - S01E01E02E03 - Triple.mkv", 1, 1, 3, "Triple"),
        ("show.s02e10.1080p.web-dl.x264-grp.mkv", 2, 10, None, ""),
        ("Show.S03E04.The.Name.1080p.WEB.mkv", 3, 4, None, "The Name"),
        ("Show - 1x05 - Old Style.mkv", 1, 5, None, "Old Style"),
        ("Show - S01E02 - Title [WEBDL-1080p][EAC3 5.1]-GRP.mkv", 1, 2, None, "Title"),
        ("Show - S01E02 - Title - HDR10.mkv", 1, 2, None, "Title"),
        ("Pilot.mkv", None, None, None, "Pilot"),
    ],
)
def test_parse_episode(name: str, season, episode, end, title) -> None:
    parsed = parse_episode(name)
    assert (parsed.season, parsed.episode, parsed.episode_end, parsed.title) == (
        season,
        episode,
        end,
        title,
    )


def test_season_folders_and_labels() -> None:
    assert season_of_folder("Season 01") == 1
    assert season_of_folder("season 12") == 12
    assert season_of_folder("Specials") == 0
    assert season_of_folder("S2") == 2
    assert season_of_folder("Extras") is None
    assert parse_episode("Pilot.mkv", 3).season == 3
    assert strip_copy_suffix("Ep - Tailarr - HDR10") == "Ep"
    assert episode_label(1, 2, None) == "S01E02"
    assert episode_label(1, 1, 2) == "S01E01–E02"
    assert episode_label(0, 3, None) == "Special 3"
    assert episode_label(None, None, None) == ""
    assert parse_show_folder("Show (2020) {tvdb-12345}")[:3] == ("Show", 2020, 12345)


def test_languages_match_whatever_code_is_used() -> None:
    assert normalize_language("fra") == "fre"
    assert normalize_language("fre") == "fre"
    assert normalize_language("fr") == "fre"
    assert normalize_language("pt-BR") == "por"
    assert normalize_language("") == "und"
    assert LanguageChoice(mode="only", languages=["en", "eng", "deu"]).languages == ["eng", "ger"]


def test_action_choices_are_checked() -> None:
    with pytest.raises(ValidationError, match="at least one language"):
        LanguageChoice(mode="only", languages=[])
    with pytest.raises(ValidationError, match="audio can't be removed"):
        RemoveTracksAction(audio=LanguageChoice(mode="none"))
    with pytest.raises(ValidationError, match="Choose which"):
        RemoveTracksAction()
    with pytest.raises(ValidationError, match="subtitle language"):
        DefaultTracksAction(subtitles="language")
    with pytest.raises(ValidationError, match="Choose a default"):
        DefaultTracksAction()
    action = RemoveTracksAction(subtitles=LanguageChoice(mode="only", languages=["eng"]))
    assert describe_action(action) == "Save a copy keeping only English subtitles"
    assert describe_action(Hdr10CopyAction()).startswith("Make a copy without Dolby Vision")
    assert (
        describe_action(DefaultTracksAction(audio_language="fre", subtitles="off"))
        == "Make the default French audio and no subtitles shown"
    )


# -- scanning -------------------------------------------------------------------------------


@pytest.fixture
def tv(samples_dir: Path, config: AppConfig) -> Path:
    root = Path(config.default_tv_dir)
    shutil.rmtree(root)
    shutil.copytree(samples_dir / "data" / "media" / "tv", root, symlinks=True)
    return root


def _start(client: TestClient) -> JobQueue:
    client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    queue: JobQueue = client.app.state.job_queue  # type: ignore[attr-defined]
    queue.start()
    return queue


@pytest.fixture
def app_client(client: TestClient, tv: Path):
    queue = _start(client)
    yield client
    queue.stop()


def _show(client: TestClient, title: str) -> dict:
    shows = client.get("/api/tv").json()["shows"]
    show_id = next(s["id"] for s in shows if s["title"] == title)
    return client.get(f"/api/tv/shows/{show_id}").json()


def _episode(show: dict, label: str) -> dict:
    return next(e for s in show["seasons"] for e in s["episodes"] if e["label"] == label)


def _wait(client: TestClient, job_id: int, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def test_scan_finds_shows_seasons_and_episodes(app_client: TestClient) -> None:
    listing = app_client.get("/api/tv").json()
    assert [s["title"] for s in listing["shows"]] == [ANOTHER, TEST_SHOW]
    assert listing["scan"]["error"] is None
    another = next(s for s in listing["shows"] if s["title"] == ANOTHER)
    assert another["year"] == 2022
    assert another["season_count"] == 1
    assert another["episode_count"] == 3  # the "- HDR10" copy belongs to S01E01
    assert another["poster_url"].startswith(f"/api/tv/shows/{another['id']}/poster")

    show = _show(app_client, TEST_SHOW)
    assert [s["label"] for s in show["seasons"]] == ["Specials", "Season 1", "Season 2"]
    season1 = show["seasons"][1]
    assert [e["label"] for e in season1["episodes"]] == ["S01E01", "S01E02", "S01E03"]
    assert [e["title"] for e in season1["episodes"]] == ["Pilot", "The Second One", "Many Voices"]
    assert show["seasons"][0]["episodes"][0]["label"] == "Special 1"
    assert show["season_count"] == 2  # specials don't count as a season

    another = _show(app_client, ANOTHER)
    start = _episode(another, "S01E01")
    assert start["has_copy"] is True
    detail = app_client.get(f"/api/episodes/{start['id']}").json()
    assert [f["name"] for f in detail["files"]] == [
        "Another Show (2022) - S01E01 - Start.mkv",
        "Another Show (2022) - S01E01 - Start - HDR10.mkv",
    ]
    assert detail["files"][0]["is_main"] and detail["files"][1]["is_copy"]
    assert detail["show_title"] == ANOTHER
    poster = app_client.get(another["poster_url"])
    assert poster.status_code == 200 and poster.headers["content-type"] == "image/jpeg"
    assert app_client.get(another["backdrop_url"]).status_code == 200


def test_episode_media_and_summaries(app_client: TestClient) -> None:
    another = _show(app_client, ANOTHER)
    middle = _episode(another, "S01E02")
    media = app_client.get(f"/api/episodes/{middle['id']}/media").json()
    assert media["hdr"]["dv_profile"] == "8.1"
    assert [t["type"] for t in media["tracks"]][:1] == ["video"]
    app_client.app.state.media_reader.run()  # type: ignore[attr-defined]
    listing = app_client.get("/api/tv").json()
    shown = next(s for s in listing["shows"] if s["title"] == ANOTHER)
    assert shown["media"]["hdr"][0] == "Dolby Vision"
    assert shown["dv_episodes"] == 3
    assert app_client.get("/api/episodes/99999").status_code == 404
    assert app_client.get("/api/tv/shows/99999").status_code == 404


def test_links_outside_the_tv_folder_are_ignored(client: TestClient, tv: Path, tmp_path: Path):
    outside = tmp_path / "data" / "torrents" / "Sneaky Show"
    (outside / "Season 01").mkdir(parents=True)
    shutil.copy(next(tv.rglob("*S01E01 - Pilot.mkv")), outside / "Season 01" / "S01E01.mkv")
    (tv / "Sneaky Show").symlink_to(outside)
    client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    titles = [s["title"] for s in client.get("/api/tv").json()["shows"]]
    assert "Sneaky Show" not in titles


def test_missing_tv_folder_keeps_last_list(app_client: TestClient, tv: Path) -> None:
    hidden = tv.with_name("tv-away")
    tv.rename(hidden)
    status = app_client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    assert "can't find your TV folder" in status.error
    assert len(app_client.get("/api/tv").json()["shows"]) == 2
    hidden.rename(tv)


def test_episode_ids_survive_rescans(app_client: TestClient, tv: Path) -> None:
    before = _episode(_show(app_client, TEST_SHOW), "S01E02")["id"]
    episode_folder = tv / TEST_SHOW / "Season 01"
    shutil.copy(
        episode_folder / "Test Show - S01E02 - The Second One.mkv",
        episode_folder / "Test Show - S01E02 - The Second One - Tailarr.mkv",
    )
    app_client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    after = _episode(_show(app_client, TEST_SHOW), "S01E02")
    assert after["id"] == before
    assert after["has_copy"] is True
    assert after["file_count"] == 2


# -- actions on one episode ---------------------------------------------------------------------


def test_hdr10_copy_of_an_episode(app_client: TestClient, tv: Path) -> None:
    middle = _episode(_show(app_client, ANOTHER), "S01E02")
    preview = app_client.post(
        f"/api/episodes/{middle['id']}/hdr10-copy/preview", json={"file": S01E02}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["new_file"] == "Another Show (2022) - S01E02 - Middle - HDR10.mkv"
    started = app_client.post(
        f"/api/episodes/{middle['id']}/hdr10-copy", json={"file": S01E02, "confirmed": True}
    )
    assert started.status_code == 202, started.text
    assert started.json()["episode_id"] == middle["id"]
    assert started.json()["subject"] == "Another Show – S01E02 – Middle"
    job = _wait(app_client, started.json()["id"])
    assert job["status"] == "done", job
    # The episode page shows the copy straight away, with the same episode id.
    detail = app_client.get(f"/api/episodes/{middle['id']}").json()
    copy = next(f for f in detail["files"] if f["is_copy"])
    assert copy["name"].endswith(" - HDR10.mkv")
    assert copy["copy_of"] == S01E02
    assert copy["media"]["hdr"] == ["HDR10"]


def test_track_settings_on_an_episode_need_confirmation(app_client: TestClient) -> None:
    pilot = _episode(_show(app_client, TEST_SHOW), "S01E03")
    media = app_client.get(f"/api/episodes/{pilot['id']}/media").json()
    french = next(t for t in media["tracks"] if t["language"] == "fre" and t["type"] == "audio")
    body = {"file": media["file"], "changes": [{"uid": french["uid"], "default": True}]}
    assert (
        app_client.post(f"/api/episodes/{pilot['id']}/track-settings", json=body).status_code == 400
    )
    job = app_client.post(
        f"/api/episodes/{pilot['id']}/track-settings", json={**body, "confirmed": True}
    ).json()
    assert _wait(app_client, job["id"])["status"] == "done"
    media = app_client.get(f"/api/episodes/{pilot['id']}/media").json()
    assert next(t for t in media["tracks"] if t["uid"] == french["uid"])["default"] is True


# -- batch actions ------------------------------------------------------------------------------


def _batch(client: TestClient, show: dict, body: dict, *, start: bool = False):
    path = f"/api/tv/shows/{show['id']}/batch" + ("" if start else "/preview")
    if start:
        body = {**body, "confirmed": True}
    return client.post(path, json=body)


def test_batch_hdr10_preview_lists_every_episode(app_client: TestClient) -> None:
    another = _show(app_client, ANOTHER)
    response = _batch(app_client, another, {"season": 1, "action": {"type": "hdr10_copy"}})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["scope"] == "Another Show, Season 1"
    assert preview["changes_originals"] is False
    by_label = {f["label"].split(" – ")[0]: f for f in preview["files"]}
    assert by_label["S01E01"]["will_run"] is False
    assert "already exists" in by_label["S01E01"]["reason"]
    assert by_label["S01E02"]["will_run"] is True
    assert by_label["S01E02"]["new_file"].endswith(" - HDR10.mkv")
    assert by_label["S01E03"]["will_run"] is False
    assert "profile 5" in by_label["S01E03"]["reason"]
    assert (preview["will_run"], preview["skipped"]) == (1, 2)
    assert preview["enough_space"] is True
    # Replacing existing copies makes S01E01 run too.
    again = _batch(
        app_client, another, {"season": 1, "action": {"type": "hdr10_copy", "overwrite": True}}
    ).json()
    assert again["will_run"] == 2


def test_batch_remove_subtitles_runs_as_a_group(app_client: TestClient, tv: Path) -> None:
    show = _show(app_client, TEST_SHOW)
    body = {
        "action": {
            "type": "remove_tracks",
            "subtitles": {"mode": "only", "languages": ["eng"]},
        }
    }
    preview = _batch(app_client, show, body).json()
    assert preview["action"] == "Save a copy keeping only English subtitles"
    runs = [f for f in preview["files"] if f["will_run"]]
    assert [f["label"] for f in runs] == ["S01E03 – Many Voices"]
    assert any("French" in line for line in runs[0]["lines"])
    assert any("Spanish" in line for line in runs[0]["lines"])
    skipped = [f for f in preview["files"] if not f["will_run"]]
    assert all("Nothing to remove" in f["reason"] for f in skipped)

    assert _batch(app_client, show, body | {"confirmed": False}, start=False).status_code == 200
    refused = app_client.post(f"/api/tv/shows/{show['id']}/batch", json=body)
    assert refused.status_code == 400
    started = _batch(app_client, show, body, start=True)
    assert started.status_code == 202, started.text
    group = started.json()
    assert group["jobs"] == 1
    jobs = app_client.get("/api/jobs").json()
    assert jobs["groups"][0]["title"] == f"{preview['action']}: Test Show"
    job = next(j for j in jobs["jobs"] if j["group_id"] == group["group_id"])
    assert _wait(app_client, job["id"])["status"] == "done"
    copy = tv / TEST_SHOW / "Season 01" / "Test Show - S01E03 - Many Voices - Tailarr.mkv"
    assert copy.is_file()
    # Clearing the history also forgets the group.
    app_client.delete("/api/jobs/finished")
    assert app_client.get("/api/jobs").json()["groups"] == []


def test_batch_default_tracks_respects_seeding_files(
    app_client: TestClient, tv: Path, tmp_path: Path
) -> None:
    episode = tv / "Another Show (2022)" / "Season 01" / S01E02
    seeding = tmp_path / "data" / "torrents" / "tv" / "Another.Show.S01E02.mkv"
    seeding.parent.mkdir(parents=True)
    os.link(episode, seeding)
    app_client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    show = _show(app_client, ANOTHER)
    body = {"season": 1, "action": {"type": "default_tracks", "audio_language": "fre"}}
    preview = _batch(app_client, show, body).json()
    assert preview["changes_originals"] is True
    by_label = {f["label"].split(" – ")[0]: f for f in preview["files"]}
    assert by_label["S01E01"]["will_run"] is True
    assert "French" in " ".join(by_label["S01E01"]["lines"])
    assert by_label["S01E02"]["will_run"] is False and by_label["S01E02"]["hardlinked"]
    assert by_label["S01E03"]["will_run"] is False
    assert "No French audio" in by_label["S01E03"]["reason"]
    assert preview["hardlinked_skipped"] == 1
    allowed = _batch(app_client, show, {**body, "allow_hardlinked": True}).json()
    assert allowed["will_run"] == 2
    seeding_inode = seeding.stat().st_ino
    started = _batch(app_client, show, body, start=True).json()
    assert started["jobs"] == 1
    for job in app_client.get("/api/jobs").json()["jobs"]:
        assert _wait(app_client, job["id"])["status"] == "done"
    # The seeding episode wasn't touched.
    assert seeding.stat().st_ino == seeding_inode and seeding.stat().st_nlink == 2
    media = app_client.get(f"/api/episodes/{_episode(show, 'S01E02')['id']}/media").json()
    assert next(t for t in media["tracks"] if t["language"] == "fre")["default"] is False


def test_cancel_a_group(app_client: TestClient) -> None:
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    queue.stop()  # nothing runs, so every job is still waiting
    show = _show(app_client, ANOTHER)
    group = _batch(
        app_client,
        show,
        {"action": {"type": "hdr10_copy", "overwrite": True}},
        start=True,
    ).json()
    assert group["jobs"] == 2
    response = app_client.post(f"/api/jobs/groups/{group['group_id']}/cancel")
    assert response.json() == {"cancelled": 2}
    statuses = {j["status"] for j in app_client.get("/api/jobs").json()["jobs"]}
    assert statuses == {"cancelled"}


def test_languages_list(client: TestClient) -> None:
    languages = client.get("/api/languages").json()
    assert languages[0] == {"code": "eng", "name": "English", "common": True}
    codes = [item["code"] for item in languages]
    assert len(codes) == len(set(codes)) > 100
    assert "fra" not in codes  # one code per language


# -- database ------------------------------------------------------------------------------


def test_new_job_columns_are_added_keeping_history(tmp_path: Path) -> None:
    db = tmp_path / "tailarr.db"
    make_engine(db).dispose()
    with sqlite3.connect(db) as connection:
        connection.execute("ALTER TABLE job DROP COLUMN episode_id")
        connection.execute(
            "INSERT INTO job (kind, title, subject, path, status, step, step_number, step_count,"
            " cancellable, cancel_requested, created_at, params, temp_paths)"
            " VALUES ('x', 'Old job', 'Film', '/f.mkv', 'done', '', 0, 0, 0, 0, 1, '{}', '[]')"
        )
    make_engine(db).dispose()
    with sqlite3.connect(db) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(job)")]
        rows = connection.execute("SELECT title, episode_id FROM job").fetchall()
    assert "episode_id" in columns
    assert rows == [("Old job", None)]
