"""Big libraries stay quick: thousands of films and episodes (rows only, no real files)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from tailarr.core.config import AppConfig
from tailarr.library.media_reader import SUMMARY_VERSION
from tailarr.library.models import Episode, EpisodeFile, Film, FilmFile, MediaRecord, Show
from tailarr.media.probe import read_file

FILMS = 4000
EPISODES = 6000


def _fill(client: TestClient, config: AppConfig, samples_dir: Path) -> None:
    raw = json.dumps(read_file(samples_dir / "files" / "dv_p8.mkv"))
    movies, tv = Path(config.default_movies_dir), Path(config.default_tv_dir)
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        for i in range(FILMS):
            folder = movies / f"Film {i:05d} (2020)"
            film = Film(
                id=i + 1,
                folder=str(folder),
                folder_name=folder.name,
                title=f"Film {i:05d}",
                sort_title=f"film {i:05d}",
                year=2020,
                main_file=f"Film {i:05d}.mkv",
                size=10**10,
                added_at=1e9 + i,
                file_count=1,
            )
            path = str(folder / film.main_file)
            session.add(film)
            session.add(
                FilmFile(
                    film_id=i + 1,
                    name=film.main_file,
                    path=path,
                    size=10**10,
                    mtime=1e9 + i,
                    is_mkv=True,
                    is_copy=False,
                )
            )
            session.add(
                MediaRecord(
                    path=path,
                    size=10**10,
                    mtime=1e9 + i,
                    read_at=1,
                    raw=raw,
                    summary_version=SUMMARY_VERSION,
                    hdr="Dolby Vision,HDR10",
                    dv_profile="8.1",
                    resolution="4K",
                )
            )
        show = Show(
            id=1,
            folder=str(tv / "Big Show"),
            folder_name="Big Show",
            title="Big Show",
            sort_title="big show",
            season_count=60,
            episode_count=EPISODES,
        )
        session.add(show)
        for i in range(EPISODES):
            season, number = i // 100 + 1, i % 100 + 1
            folder = tv / "Big Show" / f"Season {season:02d}"
            name = f"Big Show - S{season:02d}E{number:02d}.mkv"
            session.add(
                Episode(
                    id=i + 1,
                    show_id=1,
                    key=f"{folder}/{name}",
                    folder=str(folder),
                    season=season,
                    episode=number,
                    main_file=name,
                    size=10**9,
                    file_count=1,
                )
            )
            session.add(
                EpisodeFile(
                    episode_id=i + 1,
                    show_id=1,
                    name=name,
                    path=str(folder / name),
                    size=10**9,
                    mtime=1e9,
                    is_mkv=True,
                    is_copy=False,
                )
            )
        session.commit()


def _timed(client: TestClient, method: str, path: str, **kwargs) -> float:
    start = time.perf_counter()
    response = client.request(method, path, **kwargs)
    assert response.status_code == 200, response.text
    return time.perf_counter() - start


def test_big_library_is_quick(client: TestClient, config: AppConfig, samples_dir: Path) -> None:
    _fill(client, config, samples_dir)
    # Pretend scans just happened, so listing doesn't start a real one.
    for scanner in ("film_scanner", "tv_scanner"):
        getattr(client.app.state, scanner).is_stale = lambda: False  # type: ignore[attr-defined]
    films = _timed(client, "GET", "/api/films")
    assert len(client.get("/api/films").json()["films"]) == FILMS
    shows = _timed(client, "GET", "/api/tv")
    show = _timed(client, "GET", "/api/tv/shows/1")
    preview = _timed(
        client,
        "POST",
        "/api/rules/preview",
        json={
            "name": "x",
            "scope": "films",
            "conditions": [{"type": "has_dolby_vision"}],
            "action": {"type": "hdr10_copy"},
        },
    )
    print(f"films {films:.2f}s, tv {shows:.2f}s, show {show:.2f}s, rule preview {preview:.2f}s")
    # Generous limits for slow test machines; on a normal PC these take well under a second.
    assert films < 5, films
    assert shows < 5, shows
    assert show < 5, show
    assert preview < 20, preview
