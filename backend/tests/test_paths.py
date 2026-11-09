from __future__ import annotations

import os
from pathlib import Path

import pytest

from tailarr.core.paths import (
    PathMapping,
    PathNotAllowedError,
    ensure_inside,
    is_inside,
    map_remote_path,
)


def test_inside_and_outside(tmp_path: Path) -> None:
    films = tmp_path / "data" / "media" / "movies"
    films.mkdir(parents=True)
    assert is_inside(films / "Film (2020)" / "Film.mkv", films)
    assert is_inside(films, films)
    assert not is_inside(tmp_path / "data" / "torrents" / "x.mkv", films)
    # A folder whose name merely starts the same way is not inside.
    assert not is_inside(tmp_path / "data" / "media" / "movies-4k" / "x.mkv", films)


def test_dot_dot_cannot_escape(tmp_path: Path) -> None:
    films = tmp_path / "movies"
    films.mkdir()
    sneaky = films / ".." / "torrents" / "x.mkv"
    with pytest.raises(PathNotAllowedError) as err:
        ensure_inside(sneaky, [films])
    assert "isn't allowed" in str(err.value)


def test_symlink_cannot_escape(tmp_path: Path) -> None:
    films = tmp_path / "movies"
    downloads = tmp_path / "torrents"
    films.mkdir()
    downloads.mkdir()
    os.symlink(downloads, films / "link")
    with pytest.raises(PathNotAllowedError):
        ensure_inside(films / "link" / "x.mkv", [films])


def test_ensure_inside_returns_resolved_path(tmp_path: Path) -> None:
    films = tmp_path / "movies"
    tv = tmp_path / "tv"
    films.mkdir()
    tv.mkdir()
    result = ensure_inside(tv / "Show" / "." / "e.mkv", [films, tv])
    assert result == str((tv / "Show" / "e.mkv").resolve())


def test_mapping_not_needed_with_shared_data_mount() -> None:
    path = "/data/media/movies/Film (2020)/Film (2020).mkv"
    assert map_remote_path(path, []) == path


def test_mapping_longest_prefix_wins() -> None:
    mappings = [
        PathMapping("/movies", "/data/media/movies"),
        PathMapping("/movies/4k", "/data/media/movies-4k"),
    ]
    assert map_remote_path("/movies/Film/f.mkv", mappings) == "/data/media/movies/Film/f.mkv"
    assert map_remote_path("/movies/4k/Film/f.mkv", mappings) == "/data/media/movies-4k/Film/f.mkv"


def test_mapping_matches_whole_folders_only() -> None:
    mappings = [PathMapping("/movies", "/data/media/movies")]
    assert map_remote_path("/movies-4k/f.mkv", mappings) == "/movies-4k/f.mkv"
    assert map_remote_path("/movies", mappings) == "/data/media/movies"
