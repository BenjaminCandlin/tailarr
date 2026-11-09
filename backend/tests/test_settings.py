from __future__ import annotations

from fastapi.testclient import TestClient

from tailarr.core.config import AppConfig
from tailarr.main import create_app


def test_defaults_come_from_config(client: TestClient, config: AppConfig) -> None:
    body = client.get("/api/settings/library").json()
    assert body == {
        "movies_dir": config.default_movies_dir,
        "tv_dir": config.default_tv_dir,
        "path_mappings": [],
    }


def test_default_paths_follow_trash_layout() -> None:
    import os

    saved = {
        k: os.environ.pop(k) for k in ("TAILARR_MOVIES_DIR", "TAILARR_TV_DIR") if k in os.environ
    }
    try:
        config = AppConfig.from_env()
        assert config.default_movies_dir == "/data/media/movies"
        assert config.default_tv_dir == "/data/media/tv"
    finally:
        os.environ.update(saved)


def test_save_and_reload(client: TestClient, config: AppConfig) -> None:
    new = {
        "movies_dir": "/data/media/films/",
        "tv_dir": "/data/media/shows",
        "path_mappings": [{"remote": "/movies", "local": "/data/media/films"}],
    }
    response = client.put("/api/settings/library", json=new)
    assert response.status_code == 200
    assert response.json()["movies_dir"] == "/data/media/films"  # trailing slash tidied

    # A fresh app on the same config folder remembers the settings.
    again = TestClient(create_app(config)).get("/api/settings/library").json()
    assert again["tv_dir"] == "/data/media/shows"
    assert again["path_mappings"] == [{"remote": "/movies", "local": "/data/media/films"}]


def _put(client: TestClient, movies: str, tv: str) -> tuple[int, str]:
    response = client.put("/api/settings/library", json={"movies_dir": movies, "tv_dir": tv})
    return response.status_code, response.text


def test_rejects_unsafe_folders(client: TestClient) -> None:
    assert _put(client, "media/movies", "/data/media/tv")[0] == 422  # not a full path
    assert _put(client, "/data", "/data/media/tv")[0] == 422  # whole share is too broad
    assert _put(client, "/", "/data/media/tv")[0] == 422
    assert _put(client, "/data/media/../torrents", "/data/media/tv")[0] == 422
    status, text = _put(client, "/data/media", "/data/media/tv")  # nested
    assert status == 422
    assert "separate folders" in text
    assert _put(client, "/data/media/tv", "/data/media/tv")[0] == 422  # same


def test_rejects_relative_mapping(client: TestClient) -> None:
    response = client.put(
        "/api/settings/library",
        json={
            "movies_dir": "/data/media/movies",
            "tv_dir": "/data/media/tv",
            "path_mappings": [{"remote": "movies", "local": "/data/media/movies"}],
        },
    )
    assert response.status_code == 422
