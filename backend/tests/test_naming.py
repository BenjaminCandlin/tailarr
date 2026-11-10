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
        # Bracketed years and release-style names.
        ("12 Years A Slave [2013]", "12 Years A Slave", 2013, None, None),
        ("300.2006.1080p.Bluray.x264.DTS.dxva", "300", 2006, None, None),
        (
            "300.Rise.Of.An.Empire.2014.1080p.BluRay.DTS-HD.MA.7.1",
            "300 Rise Of An Empire",
            2014,
            None,
            None,
        ),
        ("A.Beautiful.Mind.2001.1080p.BluRay.x264-WiKi", "A Beautiful Mind", 2001, None, None),
        ("Blade.Runner.2049.2017.2160p.UHD", "Blade Runner 2049", 2017, None, None),
        ("Blade Runner 2049", "Blade Runner 2049", None, None, None),  # 2049 isn't a year yet
        ("Wonder.Woman.1984.2020.1080p", "Wonder Woman 1984", 2020, None, None),
        ("Movie_Name_2010_720p", "Movie Name", 2010, None, None),
        ("Some Film 1080p BluRay", "Some Film", None, None, None),
        ("Alien³ (1992)", "Alien³", 1992, None, None),
        (
            "28 Years Later - The Bone Temple (2026)",
            "28 Years Later - The Bone Temple",
            2026,
            None,
            None,
        ),
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
