"""Scanning the Films folder and the film API, on the generated sample library."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tailarr.core.config import AppConfig
from tailarr.library.artwork import find_backdrop, find_poster, thumbnail
from tailarr.library.scanner import STALE_AFTER_SECONDS, find_films
from tailarr.main import create_app

SAMPLE_FILMS = {
    "Blu-ray Night",
    "Bright Lights",
    "Colour Test",
    "Old Home Video",
    "Sample Multi-Language Film",
    "Streaming Only",
    "The Long Weekend",
    "The Quiet Hours",
    "Ärger im Paradies",
}


@pytest.fixture
def library(samples_dir: Path, config: AppConfig) -> Path:
    """A private copy of the sample Films folder (tests may change it)."""
    movies = Path(config.default_movies_dir)
    shutil.rmtree(movies)
    shutil.copytree(samples_dir / "data" / "media" / "movies", movies, symlinks=True)
    return movies


@pytest.fixture
def scanned(client: TestClient, library: Path) -> TestClient:
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    return client


def _films(client: TestClient) -> dict[str, dict]:
    return {film["title"]: film for film in client.get("/api/films").json()["films"]}


def test_finds_every_film_folder(library: Path) -> None:
    found = {Path(f.folder).name: f for f in find_films(library)}
    # Empty folders (Radarr creates them for films not downloaded yet) aren't films.
    assert "Not Downloaded Yet (2025)" not in found
    assert len(found) == len(SAMPLE_FILMS)

    colour = found["Colour Test (2023)"]
    assert colour.main_file.name == "Colour Test (2023) WEBDL-2160p DV HDR10.mkv"
    assert [f.is_copy for f in colour.files] == [False, True]  # original first, then copy

    bright = found["Bright Lights (2019)"]
    names = [f.name for f in bright.files]
    assert names == ["Bright Lights (2019) Bluray-2160p.mkv"]  # no temp file, no subtitles


def test_film_list(scanned: TestClient, library: Path) -> None:
    body = scanned.get("/api/films").json()
    assert body["root"] == str(library)
    assert body["scan"]["error"] is None
    assert body["scan"]["film_count"] == len(SAMPLE_FILMS)
    films = {film["title"]: film for film in body["films"]}
    assert set(films) == SAMPLE_FILMS

    weekend = films["The Long Weekend"]
    assert weekend["year"] == 1999
    assert weekend["folder_name"] == "The Long Weekend (1999) {tmdb-10001}"
    assert weekend["poster_url"].startswith(f"/api/films/{weekend['id']}/poster?v=")

    assert films["Colour Test"]["file_count"] == 2
    assert films["Streaming Only"]["poster_url"] is None
    assert films["Old Home Video"]["is_mkv"] is False
    assert films["Bright Lights"]["is_mkv"] is True
    assert films["The Quiet Hours"]["year"] == 2017  # from a download-style folder name

    # Sorted by title, ignoring "The" and accents.
    titles = [film["title"] for film in body["films"]]
    assert titles.index("Ärger im Paradies") < titles.index("Blu-ray Night")
    assert titles.index("The Long Weekend") < titles.index("Old Home Video")  # under L


def test_size_and_date_added(scanned: TestClient, library: Path) -> None:
    films = _films(scanned)
    folder = library / "Colour Test (2023)"
    total = sum(p.stat().st_size for p in folder.glob("*.mkv"))
    assert films["Colour Test"]["size"] == total
    assert (
        films["Colour Test"]["added_at"].endswith("Z")
        or "+00:00" in films["Colour Test"]["added_at"]
    )


def test_film_detail(scanned: TestClient, library: Path) -> None:
    film_id = _films(scanned)["Colour Test"]["id"]
    detail = scanned.get(f"/api/films/{film_id}").json()
    assert detail["folder"] == str(library / "Colour Test (2023)")
    assert detail["backdrop_url"].startswith(f"/api/films/{film_id}/backdrop?v=")
    files = detail["files"]
    assert files[0]["is_main"] and not files[0]["is_copy"]
    assert files[1]["name"].endswith(" - HDR10.mkv") and files[1]["is_copy"]
    assert scanned.get("/api/films/99999").status_code == 404


def test_hardlinked_file_is_marked(client: TestClient, library: Path, tmp_path: Path) -> None:
    film = library / "Colour Test (2023)" / "Colour Test (2023) WEBDL-2160p DV HDR10.mkv"
    seeding = tmp_path / "data" / "torrents" / "movies" / "Colour.Test.mkv"
    seeding.parent.mkdir(parents=True)
    os.link(film, seeding)
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    film_id = _films(client)["Colour Test"]["id"]
    files = client.get(f"/api/films/{film_id}").json()["files"]
    assert files[0]["hardlinked"] is True
    assert files[1]["hardlinked"] is False
    # The download folder itself never appears in the library.
    assert all("torrents" not in f["name"] for f in files)


def test_poster_thumbnail_and_full_size(scanned: TestClient, config: AppConfig) -> None:
    film = _films(scanned)["Colour Test"]
    small = scanned.get(film["poster_url"])
    assert small.status_code == 200
    assert small.headers["content-type"] == "image/jpeg"
    assert "immutable" in small.headers["cache-control"]
    with Image.open(__import__("io").BytesIO(small.content)) as image:
        assert image.size == (480, 720)
    # The small copy is kept in the config folder's cache.
    assert list((config.config_dir / "cache" / "posters").rglob("*.jpg"))

    full = scanned.get(f"/api/films/{film['id']}/poster?size=full")
    assert full.status_code == 200
    with Image.open(__import__("io").BytesIO(full.content)) as image:
        assert image.size == (600, 900)

    png = _films(scanned)["The Long Weekend"]
    assert scanned.get(png["poster_url"]).headers["content-type"] == "image/jpeg"

    no_poster = _films(scanned)["Streaming Only"]
    assert scanned.get(f"/api/films/{no_poster['id']}/poster").status_code == 404


def test_broken_poster_gives_404(scanned: TestClient, library: Path) -> None:
    (library / "Colour Test (2023)" / "poster.jpg").write_bytes(b"not a picture")
    scanned.app.state.film_scanner.run()  # type: ignore[attr-defined]
    film = _films(scanned)["Colour Test"]
    assert scanned.get(film["poster_url"]).status_code == 404


def test_poster_link_pointing_outside_is_refused(
    client: TestClient, library: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "data" / "torrents" / "poster.jpg"
    secret.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 90)).save(secret)
    (library / "Streaming Only (2024)" / "poster.jpg").symlink_to(secret)
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    assert _films(client)["Streaming Only"]["poster_url"] is None


def test_film_folder_link_pointing_outside_is_ignored(
    client: TestClient, library: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "data" / "torrents" / "Sneaky (2020)"
    outside.mkdir(parents=True)
    shutil.copyfile(
        library / "Bright Lights (2019)" / "Bright Lights (2019) Bluray-2160p.mkv",
        outside / "Sneaky (2020).mkv",
    )
    (library / "Sneaky (2020)").symlink_to(outside, target_is_directory=True)
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    assert "Sneaky" not in _films(client)


def test_rescan_picks_up_changes(scanned: TestClient, library: Path) -> None:
    shutil.rmtree(library / "Old Home Video (1995)")
    new = library / "Brand New (2026) {tmdb-42}"
    new.mkdir()
    shutil.copyfile(
        library / "Bright Lights (2019)" / "Bright Lights (2019) Bluray-2160p.mkv",
        new / "Brand New (2026).mkv",
    )
    response = scanned.post("/api/films/scan")
    assert response.status_code == 202
    scanned.app.state.film_scanner.wait(30)  # type: ignore[attr-defined]
    films = _films(scanned)
    assert "Old Home Video" not in films
    assert films["Brand New"]["year"] == 2026


def test_missing_films_folder_is_explained(client: TestClient, library: Path) -> None:
    shutil.rmtree(library)
    status = client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    assert status.error and "can't find your Films folder" in status.error
    body = client.get("/api/films").json()
    assert body["films"] == []
    assert "can't find your Films folder" in body["scan"]["error"]


def test_missing_folder_keeps_the_remembered_films(scanned: TestClient, library: Path) -> None:
    # If the array is stopped for a moment, the film list shouldn't be thrown away.
    hidden = library.with_name("movies-away")
    library.rename(hidden)
    scanned.app.state.film_scanner.run()  # type: ignore[attr-defined]
    hidden.rename(library)
    assert len(_films(scanned)) == len(SAMPLE_FILMS)


def test_changing_the_films_folder_rescans(scanned: TestClient, library: Path) -> None:
    other = library.parent / "films-4k"
    other.mkdir()
    (other / "Only Here (2022)").mkdir()
    shutil.copyfile(
        library / "Bright Lights (2019)" / "Bright Lights (2019) Bluray-2160p.mkv",
        other / "Only Here (2022)" / "Only Here (2022).mkv",
    )
    settings = scanned.get("/api/settings/library").json()
    response = scanned.put("/api/settings/library", json={**settings, "movies_dir": str(other)})
    assert response.status_code == 200
    scanned.app.state.film_scanner.wait(30)  # type: ignore[attr-defined]
    assert set(_films(scanned)) == {"Only Here"}


def test_list_is_refreshed_when_stale(client: TestClient, library: Path) -> None:
    scanner = client.app.state.film_scanner  # type: ignore[attr-defined]
    assert scanner.is_stale()  # never scanned
    client.get("/api/films")  # starts a background scan
    scanner.wait(30)
    assert not scanner.is_stale()
    assert len(_films(client)) == len(SAMPLE_FILMS)


def test_scan_status_survives_restart(scanned: TestClient, config: AppConfig) -> None:
    again = TestClient(create_app(config))
    status = again.get("/api/films/scan").json()
    assert status["film_count"] == len(SAMPLE_FILMS)
    assert status["running"] is False
    assert len(_films(again)) == len(SAMPLE_FILMS)


def test_stale_after_fifteen_minutes(scanned: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = scanned.app.state.film_scanner  # type: ignore[attr-defined]
    assert not scanner.is_stale()
    later = time.time() + STALE_AFTER_SECONDS + 1
    monkeypatch.setattr(time, "time", lambda: later)
    assert scanner.is_stale()


def test_artwork_names() -> None:
    files = ["Film (2020).mkv", "Folder.JPG", "fanart.jpg", "Film (2020)-poster.png"]
    assert find_poster(files, "Film (2020).mkv") == "Folder.JPG"
    assert find_poster(["Film (2020)-poster.png"], "Film (2020).mkv") == "Film (2020)-poster.png"
    assert find_poster(["Film (2020).jpg"], "Film (2020).mkv") == "Film (2020).jpg"
    assert find_poster(["fanart.jpg"], "Film (2020).mkv") is None
    assert find_backdrop(files, "Film (2020).mkv") == "fanart.jpg"


def test_thumbnail_permissions_follow_umask(tmp_path: Path) -> None:
    source = tmp_path / "poster.jpg"
    Image.new("RGB", (1000, 1500), "teal").save(source)
    old = os.umask(0o002)
    try:
        small = thumbnail(source, tmp_path / "cache")
    finally:
        os.umask(old)
    assert small is not None
    assert small.stat().st_mode & 0o777 == 0o664
    assert small.parent.stat().st_mode & 0o777 == 0o775
    # Made once, then reused.
    assert thumbnail(source, tmp_path / "cache") == small


def test_scan_starts_when_tailarr_starts(config: AppConfig, library: Path) -> None:
    app = create_app(config)
    with TestClient(app) as client:
        app.state.film_scanner.wait(30)
        assert len(_films(client)) == len(SAMPLE_FILMS)


def test_release_names_and_year_from_file_name(client: TestClient, library: Path) -> None:
    source = library / "Bright Lights (2019)" / "Bright Lights (2019) Bluray-2160p.mkv"
    release = library / "A.Beautiful.Mind.2001.1080p.BluRay.x264-WiKi"
    release.mkdir()
    shutil.copyfile(source, release / "a.beautiful.mind.2001.1080p.mkv")
    plain = library / "1917"
    plain.mkdir()
    shutil.copyfile(source, plain / "1917 (2019) Bluray-2160p.mkv")
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    films = _films(client)
    assert films["A Beautiful Mind"]["year"] == 2001
    assert films["1917"]["year"] == 2019  # the folder has no year; the file name does
