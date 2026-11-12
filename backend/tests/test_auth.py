"""The optional login, cross-site protection, and housekeeping."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tailarr.core.auth import check_password, hash_password
from tailarr.core.housekeeping import clean_caches, clean_job_history, clean_rule_memory
from tailarr.jobs.models import Job, JobGroup
from tailarr.main import create_app
from tailarr.rules.models import RuleRun
from tests.conftest import page_client

PASSWORD = "correct horse"


def _turn_on(client: TestClient) -> None:
    response = client.put(
        "/api/settings/login", json={"enabled": True, "username": "ben", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


def test_passwords_are_hashed() -> None:
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored and stored.startswith("scrypt$")
    assert check_password(PASSWORD, stored)
    assert not check_password("wrong", stored)
    assert not check_password(PASSWORD, "nonsense")


def test_changes_need_tailarrs_own_page(config) -> None:
    bare = TestClient(create_app(config))  # like another website posting to Tailarr
    refused = bare.post("/api/films/scan")
    assert refused.status_code == 403
    assert "didn't come from Tailarr's own page" in refused.json()["detail"]
    assert bare.get("/api/films").status_code == 200  # reading is fine
    # Webhooks don't need it (they have their own secret).
    assert bare.post("/api/webhooks/radarr", json={"eventType": "Test"}).status_code == 401


def test_login_is_off_by_default(client: TestClient) -> None:
    assert client.get("/api/auth/status").json() == {
        "login_enabled": False,
        "logged_in": True,
        "username": None,
    }
    assert client.get("/api/films").status_code == 200


def test_login_protects_everything_but_ping_and_webhooks(client: TestClient, config) -> None:
    _turn_on(client)
    assert client.get("/api/films").status_code == 200  # this browser stayed logged in
    stranger = page_client(create_app(config))
    assert stranger.get("/api/films").status_code == 401
    assert stranger.get("/api/films").json()["detail"] == "Please log in."
    assert stranger.get("/api/settings/connections").status_code == 401
    assert stranger.get("/api/ping").json() == {"ok": True}
    assert stranger.get("/api/auth/status").json()["logged_in"] is False
    # Pages themselves load (they show the login form).
    assert stranger.get("/films").status_code in (200, 503)
    path = client.get("/api/settings/connections").json()["webhook_paths"]["radarr"]
    assert stranger.post(path, json={"eventType": "Test"}).status_code == 200

    wrong = stranger.post("/api/auth/login", json={"username": "ben", "password": "nope"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == "Wrong username or password."
    ok = stranger.post("/api/auth/login", json={"username": "Ben", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["logged_in"] is True
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert stranger.get("/api/films").status_code == 200
    stranger.post("/api/auth/logout")
    assert stranger.get("/api/films").status_code == 401


def test_too_many_wrong_passwords_slow_down(client: TestClient, config) -> None:
    _turn_on(client)
    stranger = page_client(create_app(config))
    for _ in range(5):
        stranger.post("/api/auth/login", json={"username": "ben", "password": "guess"})
    locked = stranger.post("/api/auth/login", json={"username": "ben", "password": PASSWORD})
    assert locked.status_code == 429 and "Too many wrong passwords" in locked.json()["detail"]


def test_login_settings_are_checked(client: TestClient) -> None:
    short = client.put(
        "/api/settings/login", json={"enabled": True, "username": "ben", "password": "short"}
    )
    assert short.status_code == 400 and "at least 8" in short.json()["detail"]
    assert (
        client.put("/api/settings/login", json={"enabled": True, "password": PASSWORD}).status_code
        == 400
    )
    _turn_on(client)
    assert client.get("/api/settings/login").json() == {"enabled": True, "username": "ben"}
    off = client.put("/api/settings/login", json={"enabled": False})
    assert off.json()["enabled"] is False
    assert client.get("/api/auth/status").json()["login_enabled"] is False


def test_forgotten_password_reset(client: TestClient, config, monkeypatch) -> None:
    _turn_on(client)
    monkeypatch.setenv("TAILARR_DISABLE_LOGIN", "1")
    restarted = page_client(create_app(config))
    assert restarted.get("/api/films").status_code == 200
    assert restarted.get("/api/auth/status").json()["login_enabled"] is False


# -- housekeeping -------------------------------------------------------------------------


def test_old_job_history_is_tidied(client: TestClient) -> None:
    engine = client.app.state.engine  # type: ignore[attr-defined]
    now = time.time()
    with Session(engine) as session:
        session.add(JobGroup(id="old", title="Old group", created_at=now - 40 * 86400))
        for status, finished in (
            ("done", now - 40 * 86400),
            ("failed", now - 86400),
            ("queued", None),
        ):
            session.add(
                Job(
                    kind="x",
                    title=status,
                    subject="s",
                    path="/f.mkv",
                    status=status,
                    created_at=now - 50 * 86400,
                    finished_at=finished,
                    group_id="old" if status == "done" else None,
                )
            )
        session.commit()
    assert clean_job_history(engine, now) == 1
    titles = [j["title"] for j in client.get("/api/jobs").json()["jobs"]]
    assert sorted(titles) == ["failed", "queued"]
    with Session(engine) as session:
        assert session.get(JobGroup, "old") is None


def test_caches_and_rule_memory_are_tidied(client: TestClient, config, tmp_path: Path) -> None:
    engine = client.app.state.engine  # type: ignore[attr-defined]
    posters = config.config_dir / "cache" / "posters" / "ab"
    posters.mkdir(parents=True)
    old, fresh = posters / "old.jpg", posters / "fresh.jpg"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    long_ago = time.time() - 100 * 86400
    os.utime(old, (long_ago, long_ago))
    arr = config.config_dir / "cache" / "arr"
    arr.mkdir(parents=True)
    (arr / "radarr-1-poster-abc.jpg").write_bytes(b"x")
    assert clean_caches(engine, config) == 2
    assert fresh.exists() and not old.exists()
    kept = tmp_path / "kept.mkv"
    kept.write_bytes(b"x")
    with Session(engine) as session:
        for path in (kept, tmp_path / "gone.mkv"):
            session.add(RuleRun(rule_id=1, path=str(path), size=1, mtime=1, at=1, outcome="queued"))
        session.commit()
    assert clean_rule_memory(engine) == 1


@pytest.mark.parametrize("path", ["/api/health", "/api/ping"])
def test_health_and_ping(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200
