from __future__ import annotations

import os
import shutil

import pytest
from fastapi.testclient import TestClient

from tailarr.core.config import AppConfig

from .conftest import REQUIRE_ALL_TOOLS


def test_health_lists_every_tool(client: TestClient) -> None:
    body = client.get("/api/health").json()
    names = [t["name"] for t in body["tools"]]
    assert names == ["mkvmerge", "mkvextract", "mkvpropedit", "mediainfo", "dovi_tool"]
    for tool in body["tools"]:
        assert tool["label"] and tool["purpose"]
        if tool["name"] != "dovi_tool":
            assert tool["ok"], tool
            assert tool["version"]


def test_dovi_tool_detected() -> None:
    if shutil.which("dovi_tool") is None:
        if REQUIRE_ALL_TOOLS:
            pytest.fail("dovi_tool must be installed (TAILARR_REQUIRE_ALL_TOOLS=1)")
        pytest.skip("dovi_tool isn't installed on this machine (it is in CI and the image)")
    from tailarr.media.tools import TOOLS, tool_version

    assert tool_version(next(t for t in TOOLS if t.name == "dovi_tool"))


def test_folders_reported(client: TestClient, config: AppConfig) -> None:
    body = client.get("/api/health").json()
    folders = {f["key"]: f for f in body["folders"]}
    assert set(folders) == {"movies", "tv", "config", "work"}
    assert folders["movies"]["path"] == config.default_movies_dir
    assert folders["movies"]["ok"] and folders["tv"]["ok"] and folders["config"]["ok"]
    # The work folder is optional: not mounted is fine.
    assert folders["work"]["exists"] is False
    assert folders["work"]["ok"] is True


def test_missing_films_folder_is_flagged(client: TestClient, config: AppConfig) -> None:
    shutil.rmtree(config.default_movies_dir)
    body = client.get("/api/health").json()
    films = next(f for f in body["folders"] if f["key"] == "movies")
    assert films["exists"] is False
    assert films["ok"] is False
    assert body["ok"] is False


def test_health_follows_saved_settings(client: TestClient, tmp_path) -> None:
    other = tmp_path / "elsewhere" / "films"
    other.mkdir(parents=True)
    tv = tmp_path / "elsewhere" / "tv"
    tv.mkdir()
    client.put("/api/settings/library", json={"movies_dir": str(other), "tv_dir": str(tv)})
    body = client.get("/api/health").json()
    films = next(f for f in body["folders"] if f["key"] == "movies")
    assert films["path"] == str(other)


def test_running_as(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["running_as"]["uid"] == os.getuid()
    assert len(body["running_as"]["umask"]) == 3


def test_overall_ok_when_everything_present(client: TestClient) -> None:
    body = client.get("/api/health").json()
    if shutil.which("dovi_tool") is None and not REQUIRE_ALL_TOOLS:
        assert body["ok"] is False  # correctly reports the missing tool
    else:
        assert body["ok"] is True
