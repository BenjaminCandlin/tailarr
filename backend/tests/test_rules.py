"""Rules: saving, plain-English sentences, previews on the sample library, and running."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tailarr.core.config import AppConfig
from tailarr.rules.engine import describe_rule
from tailarr.rules.models import Condition, RuleIn

DV_RULE = {
    "name": "HDR10 copies of Dolby Vision films",
    "scope": "films",
    "conditions": [{"type": "has_dolby_vision"}],
    "action": {"type": "hdr10_copy"},
}
SUBS_RULE = {
    "name": "Only English subtitles",
    "scope": "both",
    "conditions": [{"type": "has_subtitles_not_in", "languages": ["eng"]}],
    "action": {"type": "remove_tracks", "subtitles": {"mode": "only", "languages": ["eng"]}},
}


@pytest.fixture
def app_client(client: TestClient, samples_dir: Path, config: AppConfig):
    for name, target in (("movies", config.default_movies_dir), ("tv", config.default_tv_dir)):
        shutil.rmtree(target)
        shutil.copytree(samples_dir / "data" / "media" / name, target, symlinks=True)
    state = client.app.state  # type: ignore[attr-defined]
    state.film_scanner.run()
    state.tv_scanner.run()
    state.media_reader.run()
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


def test_rules_are_described_in_plain_english() -> None:
    assert describe_rule(RuleIn.model_validate(DV_RULE)) == (
        "When a new film is added, if it has Dolby Vision: make a copy without Dolby Vision "
        "(HDR10 copy)."
    )
    assert describe_rule(RuleIn.model_validate(SUBS_RULE)) == (
        "When a new film or episode is added, if it has subtitles that aren't English: save a "
        "copy keeping only English subtitles."
    )
    defaults = RuleIn.model_validate(
        {
            "name": "French audio",
            "scope": "tv",
            "action": {"type": "default_tracks", "audio_language": "fra"},
            "allow_originals": True,
        }
    )
    assert describe_rule(defaults) == (
        "When a new episode is added: make the default French audio."
    )


def test_rules_that_change_originals_need_permission() -> None:
    with pytest.raises(ValidationError, match="Allowed to change original files"):
        RuleIn.model_validate(
            {"name": "x", "action": {"type": "default_tracks", "subtitles": "off"}}
        )
    # Seeding files can only be allowed together with originals.
    rule = RuleIn.model_validate({**DV_RULE, "allow_hardlinked": True})
    assert rule.allow_hardlinked is False
    with pytest.raises(ValidationError, match="at least one language"):
        Condition(type="has_audio_not_in")
    with pytest.raises(ValidationError):
        RuleIn.model_validate({**DV_RULE, "name": "   "})


def test_create_list_change_and_delete(client: TestClient) -> None:
    created = client.post("/api/rules", json=DV_RULE)
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["enabled"] is False  # new rules start switched off
    assert rule["sentence"].startswith("When a new film is added")
    assert rule["changes_originals"] is False
    assert [r["id"] for r in client.get("/api/rules").json()] == [rule["id"]]
    on = client.post(f"/api/rules/{rule['id']}/enabled", json={"enabled": True}).json()
    assert on["enabled"] is True
    changed = client.put(f"/api/rules/{rule['id']}", json={**DV_RULE, "name": "DV → HDR10"})
    assert changed.json()["name"] == "DV → HDR10"
    bad = client.post(
        "/api/rules", json={"name": "x", "action": {"type": "default_tracks", "subtitles": "off"}}
    )
    assert bad.status_code == 422
    assert "Allowed to change original files" in bad.text
    assert client.delete(f"/api/rules/{rule['id']}").status_code == 204
    assert client.get(f"/api/rules/{rule['id']}").status_code == 404


def test_preview_dolby_vision_rule(app_client: TestClient) -> None:
    preview = app_client.post("/api/rules/preview", json=DV_RULE).json()
    by_label = {i["label"]: i for i in preview["items"]}
    # Films with Dolby Vision: Colour Test (8.1, copy exists), Streaming Only (profile 5),
    # Blu-ray Night (profile 7).
    assert set(by_label) == {
        "Colour Test (2023)",
        "Streaming Only (2024)",
        "Blu-ray Night (2018)",
    }
    assert by_label["Blu-ray Night (2018)"]["will_run"] is True
    assert "already exists" in by_label["Colour Test (2023)"]["reason"]
    assert "profile 5" in by_label["Streaming Only (2024)"]["reason"]
    assert (preview["will_run"], preview["skipped"]) == (1, 2)
    assert preview["not_matching"] == 6
    assert preview["not_read"] == 0
    assert preview["items"][0]["will_run"] is True  # files that change come first
    # Nothing was changed by previewing.
    assert app_client.get("/api/jobs").json()["jobs"] == []


def test_preview_subtitle_rule_covers_films_and_episodes(app_client: TestClient) -> None:
    preview = app_client.post("/api/rules/preview", json=SUBS_RULE).json()
    kinds = sorted((i["kind"], i["label"]) for i in preview["items"])
    assert kinds == [
        ("episode", "Test Show – S01E03 – Many Voices"),
        ("film", "Sample Multi-Language Film (2021)"),
    ]
    assert all(i["will_run"] for i in preview["items"])
    tv_only = app_client.post("/api/rules/preview", json={**SUBS_RULE, "scope": "tv"}).json()
    assert [i["kind"] for i in tv_only["items"]] == ["episode"]


def test_run_now_queues_a_group_and_records_activity(app_client: TestClient, config) -> None:
    rule = app_client.post("/api/rules", json={**SUBS_RULE, "scope": "tv"}).json()
    assert app_client.post(f"/api/rules/{rule['id']}/run", json={}).status_code == 400
    started = app_client.post(f"/api/rules/{rule['id']}/run", json={"confirmed": True})
    assert started.status_code == 202, started.text
    assert started.json()["jobs"] == 1
    jobs = _wait_all(app_client)
    assert [j["status"] for j in jobs] == ["done"]
    groups = app_client.get("/api/jobs").json()["groups"]
    assert groups[0]["title"] == "Rule “Only English subtitles”: run by hand"
    copy = (
        Path(config.default_tv_dir)
        / "Test Show"
        / "Season 01"
        / ("Test Show - S01E03 - Many Voices - Tailarr.mkv")
    )
    assert copy.is_file()
    activity = app_client.get(f"/api/activity?rule_id={rule['id']}").json()
    assert activity and activity[0]["source"] == "rule"
    assert app_client.get(f"/api/rules/{rule['id']}").json()["last_run_at"] is not None
    # Running again finds nothing to do: the copy is there.
    app_client.post("/api/tv/scan")
    app_client.app.state.tv_scanner.wait(30)  # type: ignore[attr-defined]
    again = app_client.post(f"/api/rules/{rule['id']}/run", json={"confirmed": True})
    assert again.status_code == 400 and "nothing to do" in again.text


def test_default_tracks_rule_and_seeding_files(
    app_client: TestClient, tmp_path: Path, config
) -> None:
    episode = (
        Path(config.default_tv_dir)
        / "Another Show (2022)"
        / "Season 01"
        / "Another Show (2022) - S01E02 - Middle.mkv"
    )
    seeding = tmp_path / "data" / "torrents" / "x.mkv"
    seeding.parent.mkdir(parents=True)
    seeding.hardlink_to(episode)
    app_client.app.state.tv_scanner.run()  # type: ignore[attr-defined]
    rule = {
        "name": "French audio",
        "scope": "tv",
        "action": {"type": "default_tracks", "audio_language": "fre"},
        "allow_originals": True,
    }
    preview = app_client.post("/api/rules/preview", json=rule).json()
    assert preview["changes_originals"] is True
    middle = next(i for i in preview["items"] if "Middle" in i["label"])
    assert middle["will_run"] is False and middle["hardlinked"] is True
    allowed = app_client.post("/api/rules/preview", json={**rule, "allow_hardlinked": True}).json()
    assert next(i for i in allowed["items"] if "Middle" in i["label"])["will_run"] is True


def test_any_conditions(app_client: TestClient) -> None:
    rule = {
        "name": "DV or HDR10+",
        "scope": "films",
        "match": "any",
        "conditions": [{"type": "has_dolby_vision"}, {"type": "has_hdr10plus"}],
        "action": {"type": "hdr10_copy"},
    }
    assert describe_rule(RuleIn.model_validate(rule)) == (
        "When a new film is added, if it has Dolby Vision or it has HDR10+: make a copy "
        "without Dolby Vision (HDR10 copy)."
    )
    any_preview = app_client.post("/api/rules/preview", json=rule).json()
    all_preview = app_client.post("/api/rules/preview", json={**rule, "match": "all"}).json()
    # HDR10+ films without Dolby Vision match "any" (and are then skipped: no Dolby Vision).
    assert any_preview["not_matching"] < all_preview["not_matching"]
    saved = app_client.post("/api/rules", json=rule).json()
    assert saved["match"] == "any"
