"""Understanding TV folder and episode file names.

Sonarr names episodes like ``Show (2020) - S01E02 - Title.mkv`` inside
``Show (2020)/Season 01/``. Other common forms (``Show.S01E02.1080p``,
``1x02``, double episodes ``S01E01-E02``) are understood too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .naming import COPY_SUFFIXES, parse_film_folder

_SXXEYY = re.compile(
    r"(?<![a-z0-9])s(\d{1,4})[ ._-]*e(\d{1,4})((?:[ ._-]*-?[ ._-]*e?\d{1,4}(?![0-9p]))*)", re.I
)
_NXNN = re.compile(r"(?<![0-9])(\d{1,2})x(\d{2,3})(?![0-9p])", re.I)
_SEASON_FOLDER = re.compile(r"^(?:season|series|staffel|saison|temporada|s)[ ._-]*(\d{1,4})$", re.I)
_SPECIALS = {"specials", "special", "extras season", "season 0", "season 00"}


@dataclass(frozen=True)
class ParsedEpisode:
    season: int | None
    episode: int | None
    episode_end: int | None
    title: str


def season_of_folder(name: str) -> int | None:
    """'Season 01' -> 1, 'Specials' -> 0, 'S2' -> 2; anything else -> None."""
    clean = name.strip()
    if clean.casefold() in _SPECIALS:
        return 0
    match = _SEASON_FOLDER.match(clean)
    return int(match.group(1)) if match else None


def strip_copy_suffix(stem: str) -> str:
    """'Show - S01E01 - Pilot - HDR10' -> 'Show - S01E01 - Pilot' (copies group with originals)."""
    changed = True
    while changed:
        changed = False
        for suffix in COPY_SUFFIXES:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                changed = True
    return stem


def parse_episode(file_name: str, folder_season: int | None = None) -> ParsedEpisode:
    stem = strip_copy_suffix(Path(file_name).stem)
    match = _SXXEYY.search(stem)
    if match:
        season, first = int(match.group(1)), int(match.group(2))
        more = [int(n) for n in re.findall(r"\d{1,4}", match.group(3) or "")]
        last = max([first, *more]) if more and max(more) > first else None
        title = _title_after(stem[match.end() :])
        return ParsedEpisode(season, first, last, title)
    match = _NXNN.search(stem)
    if match:
        return ParsedEpisode(
            int(match.group(1)), int(match.group(2)), None, _title_after(stem[match.end() :])
        )
    return ParsedEpisode(folder_season, None, None, stem.strip(" -._"))


_TECH = re.compile(
    r"\b(?:\d{3,4}p|web-?dl|webrip|bluray|hdtv|remux|x26[45]|h\.?26[45]|hevc|dv|hdr10?\+?)\b.*$",
    re.I,
)


def _title_after(rest: str) -> str:
    """' - The Second One [WEBDL-1080p]' -> 'The Second One'."""
    # Sonarr puts quality and release group after the title: "Title [WEBDL-1080p]-GRP".
    rest = rest.split("[", 1)[0]
    rest = re.sub(r"\{[^}]*\}", "", rest)
    rest = rest.strip(" -._")
    if " " not in rest and "." in rest:
        rest = rest.replace(".", " ")
    rest = _TECH.sub("", rest).strip(" -._")
    return rest


def parse_show_folder(name: str) -> tuple[str, int | None, int | None, int | None, str | None]:
    """'Show (2020) {tvdb-123}' -> (title, year, tvdb id, tmdb id, imdb id)."""
    parsed = parse_film_folder(name)
    tvdb = re.search(r"[\[{]\s*tvdb(?:id)?[-=\s]*(\d+)\s*[\]}]", name, re.I)
    return (
        parsed.title,
        parsed.year,
        int(tvdb.group(1)) if tvdb else None,
        parsed.tmdb_id,
        parsed.imdb_id,
    )


def episode_label(season: int | None, episode: int | None, episode_end: int | None) -> str:
    """'S01E02', 'S01E01–E02', 'Special 3', or '' when unknown."""
    if episode is None:
        return ""
    if season == 0:
        return f"Special {episode}"
    if season is None:
        return f"Episode {episode}"
    label = f"S{season:02d}E{episode:02d}"
    if episode_end:
        label += f"–E{episode_end:02d}"
    return label


def season_label(season: int | None) -> str:
    if season is None:
        return "Other episodes"
    if season == 0:
        return "Specials"
    return f"Season {season}"
