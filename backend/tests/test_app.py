from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tailarr.core.config import AppConfig
from tailarr.main import create_app


def _with_static(config: AppConfig) -> TestClient:
    static: Path = config.static_dir
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>Tailarr app</html>")
    (static / "assets" / "app.js").write_text("console.log('hi')")
    (static / "favicon.svg").write_text("<svg/>")
    return TestClient(create_app(config))


def test_pages_serve_the_app(config: AppConfig) -> None:
    client = _with_static(config)
    for page in ("/", "/films", "/tv", "/settings", "/queue/123"):
        response = client.get(page)
        assert response.status_code == 200
        assert "Tailarr app" in response.text


def test_static_files(config: AppConfig) -> None:
    client = _with_static(config)
    assert client.get("/assets/app.js").text == "console.log('hi')"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_unknown_api_is_404(config: AppConfig) -> None:
    client = _with_static(config)
    assert client.get("/api/nope").status_code == 404


def test_cannot_read_files_outside_static(config: AppConfig, tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("secret")
    client = _with_static(config)
    response = client.get("/..%2Fsecret.txt")
    assert "secret" not in response.text


def test_without_built_frontend(client: TestClient) -> None:
    assert client.get("/films").status_code == 503
    assert client.get("/api/health").status_code == 200
