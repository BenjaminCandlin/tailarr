from __future__ import annotations

import pytest

from tailarr.library.naming import (
    fold,
    is_tailarr_copy,
    is_video,
    parse_film_folder,
    sort_key,
)


@pytest.mark.parametrize(
    ("folder", "title", "year", "tmdb", "imdb"),
    [
        ("The Matrix (1999)", "The Matrix", 1999, None, None),
        ("The Matrix (1999) {tmdb-603}", "The Matrix", 1999, 603, None),
        ("The Matrix (1999) {imdb-tt0133093}", "The Matrix", 1999, None, "tt0133093"),
        ("The Matrix (1999) [tmdbid-603]", "The Matrix", 1999, 603, None),
        ("Blade Runner 2049 (2017)", "Blade Runner 2049", 2017, None, None),
        ("2001 A Space Odyssey (1968)", "2001 A Space Odyssey", 1968, None, None),
        ("1917 (2019)", "1917", 2019, None, None),
        ("Just A Folder", "Just A Folder", None, None, None),
        ("(2020)", "(2020)", None, None, None),
        ("Ärger im Paradies (2020)", "Ärger im Paradies", 2020, None, None),
        ("Film (2020) {edition-Director's Cut}", "Film", 2020, None, None),
    ],
)
def test_parse_film_folder(
    folder: str, title: str, year: int | None, tmdb: int | None, imdb: str | None
) -> None:
    parsed = parse_film_folder(folder)
    assert (parsed.title, parsed.year, parsed.tmdb_id, parsed.imdb_id) == (title, year, tmdb, imdb)


def test_sort_ignores_articles_and_accents() -> None:
    titles = ["The Zoo", "Ärger", "A Beach", "Apple", "An Ant", "The"]
    assert sorted(titles, key=sort_key) == ["An Ant", "Apple", "Ärger", "A Beach", "The", "The Zoo"]
    assert fold("Amélie") == "amelie"


def test_video_and_copy_names() -> None:
    assert is_video("Film (2020).mkv")
    assert is_video("Film (2020).MP4")
    assert not is_video("Film (2020).en.srt")
    assert not is_video(".hidden.mkv")
    assert not is_video("poster.jpg")
    assert is_tailarr_copy("Film (2020) - HDR10.mkv")
    assert is_tailarr_copy("Film (2020) - Tailarr.mkv")
    assert not is_tailarr_copy("Film (2020).mkv")
    assert not is_tailarr_copy("Film (2020) - HDR10.mp4")
