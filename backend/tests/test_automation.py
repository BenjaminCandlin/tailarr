"""Rules running by themselves: webhooks, folder watching, "finished copying", once per file."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tailarr.core.config import AppConfig
from tailarr.jobs.models import CopyRecord
from tailarr.rules.automation import is_candidate_name
from tailarr.rules.models import RuleRun

SUBS_RULE = {
    "name": "Only English subtitles",
    "enabled": True,
    "scope": "both",
    "conditions": [{"type": "has_subtitles_not_in", "languages": ["eng"]}],
    "action": {"type": "remove_tracks", "subtitles": {"mode": "only", "languages": ["eng"]}},
}
DV_RULE = {
    "name": "HDR10 copies",
    "enabled": True,
    "scope": "films",
    "conditions": [{"type": "has_dolby_vision"}],
    "action": {"type": "hdr10_copy"},
}
COLOUR = "Colour Test (2023)"
COLOUR_FILE = "Colour Test (2023) WEBDL-2160p DV HDR10.mkv"
COLOUR_COPY = "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv"


@pytest.fixture
def app_client(client: TestClient, samples_dir: Path, config: AppConfig):
    for name, target in (("movies", config.default_movies_dir), ("tv", config.default_tv_dir)):
        shutil.rmtree(target)
        shutil.copytree(samples_dir / "data" / "media" / name, target, symlinks=True)
    state = client.app.state  # type: ignore[attr-defined]
    state.film_scanner.run()
    state.tv_scanner.run()
    client.put("/api/settings/automation", json={"settle_seconds": 0})
    state.job_queue.start()
    yield client
    state.auto_runner.stop()
    state.job_queue.stop()


def _runner(client: TestClient):
    return client.app.state.auto_runner  # type: ignore[attr-defined]


def _hook(client: TestClient, service: str, payload: dict):
    path = client.get("/api/settings/connections").json()["webhook_paths"][service]
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _wait_all(client: TestClient, timeout: float = 120) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()["jobs"]
        if all(j["status"] not in ("queued", "running") for j in jobs):
            return jobs
        time.sleep(0.1)
    raise AssertionError("jobs didn't finish")


def _new_episode(config: AppConfig) -> Path:
    season = Path(config.default_tv_dir) / "Test Show" / "Season 01"
    new = season / "Test Show - S01E04 - Even More Voices.mkv"
    shutil.copy(season / "Test Show - S01E03 - Many Voices.mkv", new)
    return new


def test_names_that_are_never_picked_up() -> None:
    assert is_candidate_name("/tv/Show/Season 01/Show - S01E01.mkv")
    assert not is_candidate_name("/tv/Show/Season 01/Show - S01E01 - HDR10.mkv")
    assert not is_candidate_name("/tv/Show/Season 01/Show - S01E01 - Tailarr.mkv")
    assert not is_candidate_name("/tv/Show/Season 01/.tailarr-tmp-3-1.mkv")
    assert not is_candidate_name("/tv/Show/Season 01/.tailarr-recycle/Show - S01E01.mkv")
    assert not is_candidate_name("/tv/Show/Season 01/Show - S01E01.mp4")


def test_a_sonarr_import_runs_enabled_rules_once(app_client: TestClient, config) -> None:
    rule = app_client.post("/api/rules", json=SUBS_RULE).json()
    app_client.post("/api/rules", json={**SUBS_RULE, "name": "Off rule", "enabled": False})
    new = _new_episode(config)
    payload = {
        "eventType": "Download",
        "series": {"path": str(new.parents[1])},
        "episodeFile": {"path": str(new)},
    }
    _hook(app_client, "sonarr", payload)
    assert [p.path for p in _runner(app_client).pending()] == [str(new)]
    assert _runner(app_client).tick() == 1
    jobs = _wait_all(app_client)
    assert len(jobs) == 1 and jobs[0]["status"] == "done"
    assert jobs[0]["episode_id"] is not None
    assert new.with_name(new.stem + " - Tailarr.mkv").is_file()
    group = app_client.get("/api/jobs").json()["groups"][0]["title"]
    assert group.startswith("Rule “Only English subtitles”: Sonarr import, Test Show – S01E04")
    # The same message again: the rule has already looked at this file.
    _hook(app_client, "sonarr", payload)
    _runner(app_client).tick()
    assert len(app_client.get("/api/jobs").json()["jobs"]) == 1
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        runs = session.exec(select(RuleRun)).all()
    assert [(r.rule_id, r.outcome) for r in runs] == [(rule["id"], "queued")]
    activity = app_client.get(f"/api/activity?rule_id={rule['id']}").json()
    assert activity[0]["rule_name"] == "Only English subtitles"
    assert activity[0]["job_status"] == "done"
    assert activity[0]["episode_id"] == jobs[0]["episode_id"]


def test_files_must_finish_copying(app_client: TestClient, config) -> None:
    app_client.post("/api/rules", json=SUBS_RULE)
    app_client.put("/api/settings/automation", json={"settle_seconds": 60})
    new = _new_episode(config)
    runner = _runner(app_client)
    assert runner.add(str(new), "test")
    now = time.time()
    assert runner.tick(now) == 0  # just seen
    assert runner.tick(now + 30) == 0  # not long enough
    with new.open("ab") as handle:  # still being copied
        handle.write(b"\0" * 10)
    assert runner.tick(now + 61) == 0  # changed, so the clock starts again
    assert runner.tick(now + 200) == 1


def test_unreadable_files_are_reported(app_client: TestClient, config) -> None:
    app_client.post("/api/rules", json=SUBS_RULE)
    junk = Path(config.default_tv_dir) / "Test Show" / "Season 01" / "Test Show - S01E09.mkv"
    junk.write_bytes(b"not a video")
    runner = _runner(app_client)
    runner.add(str(junk), "test")
    runner.tick()
    problems = app_client.get("/api/activity?problems=true").json()
    assert problems and "couldn't read" in problems[0]["message"]


def test_radarr_upgrade_tidies_old_copy_and_makes_a_new_one(app_client: TestClient, config) -> None:
    app_client.post("/api/rules", json=DV_RULE)
    folder = Path(config.default_movies_dir) / COLOUR
    original = folder / COLOUR_FILE
    stat = original.stat()
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        session.add(
            CopyRecord(
                path=str(folder / COLOUR_COPY),
                source_path=str(original),
                source_size=stat.st_size,
                source_mtime=stat.st_mtime,
                kind="hdr10_copy",
                created_at=time.time(),
            )
        )
        session.commit()
    # Radarr's upgrade: a new file arrives, the old one is deleted.
    new = folder / "Colour Test (2023) Remux-2160p DV.mkv"
    shutil.copy(original, new)
    original.unlink()
    result = _hook(
        app_client,
        "radarr",
        {
            "eventType": "Download",
            "isUpgrade": True,
            "movieFile": {"path": str(new)},
            "deletedFiles": [{"path": str(original)}],
        },
    )
    assert "moved to the recycle folder" in result["message"]
    assert _runner(app_client).tick() == 1
    jobs = _wait_all(app_client)
    assert [j["status"] for j in jobs] == ["done"]
    assert (folder / "Colour Test (2023) Remux-2160p DV - HDR10.mkv").is_file()
    assert (folder / ".tailarr-recycle" / COLOUR_COPY).is_file()
    group = app_client.get("/api/jobs").json()["groups"][0]["title"]
    assert "Radarr upgrade" in group


def test_tailarrs_own_changes_dont_start_rules(app_client: TestClient, config) -> None:
    app_client.post(
        "/api/rules",
        json={
            "name": "French audio",
            "enabled": True,
            "scope": "tv",
            "action": {"type": "default_tracks", "audio_language": "fre"},
            "allow_originals": True,
        },
    )
    episode = (
        Path(config.default_tv_dir)
        / "Test Show"
        / "Season 01"
        / ("Test Show - S01E03 - Many Voices.mkv")
    )
    runner = _runner(app_client)
    runner.add(str(episode), "test")
    runner.tick()
    jobs = _wait_all(app_client)
    assert [j["status"] for j in jobs] == ["done"]
    # The job changed the file (new date): Tailarr remembers that change was its own.
    runner.add(str(episode), "test")
    runner.tick()
    assert len(app_client.get("/api/jobs").json()["jobs"]) == 1
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        outcomes = [r.outcome for r in session.exec(select(RuleRun))]
    assert outcomes == ["queued", "tailarr-change"]


def test_folder_watching(app_client: TestClient, config) -> None:
    app_client.post("/api/rules", json=SUBS_RULE)
    settings = app_client.put(
        "/api/settings/automation", json={"settle_seconds": 0, "watch_folders": True}
    ).json()
    assert settings["watch_folders"] is True and settings["watch_since"] is not None
    runner = _runner(app_client)
    try:
        time.sleep(0.5)
        new = _new_episode(config)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not runner.pending():
            time.sleep(0.1)
        assert [p.path for p in runner.pending()] == [str(new)]
        status = app_client.get("/api/settings/automation").json()
        assert status["waiting"][0]["file"] == new.name
        runner.tick()
        assert len(_wait_all(app_client)) == 1
    finally:
        app_client.put("/api/settings/automation", json={"watch_folders": False})


def test_folder_check_finds_new_files_without_watching_events(
    app_client: TestClient, config
) -> None:
    app_client.post("/api/rules", json=SUBS_RULE)
    app_client.put("/api/settings/automation", json={"settle_seconds": 0, "watch_folders": True})
    runner = _runner(app_client)
    runner._stop_observer()  # pretend inotify missed it (as it can on /mnt/user)
    new = _new_episode(config)
    os.utime(new, (time.time() + 5, time.time() + 5))
    app_client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    assert str(new) in [p.path for p in runner.pending()]
    # Files that were already there when watching started aren't treated as new.
    assert len(runner.pending()) == 1
    app_client.put("/api/settings/automation", json={"watch_folders": False})
