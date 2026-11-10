"""Understanding film folder and file names.

Radarr names film folders like ``Film Title (2020)``, and the TRaSH Guides
naming scheme adds database ids such as ``{tmdb-12345}`` or ``{imdb-tt0123456}``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Files Tailarr can show in a film folder. Only MKV files can be changed.
VIDEO_EXTENSIONS = frozenset({".mkv", ".mp4", ".m4v", ".avi", ".ts", ".m2ts", ".mov", ".wmv"})

# Copies Tailarr makes end with one of these before ".mkv".
COPY_SUFFIXES = (" - HDR10", " - Tailarr")

# Tailarr's own half-written files (never shown, never processed).
TEMP_PREFIX = ".tailarr-tmp-"

_ID_TAG = re.compile(r"[\[{]\s*(tmdb|imdb|tvdb)(?:id)?[-=\s]*([^\]}]+?)\s*[\]}]", re.I)
_OTHER_TAG = re.compile(r"\s*[\[{][^\]}]*[\]}]")
_YEAR = re.compile(r"^(?P<title>.*?)[\s._]*\((?P<year>(?:18|19|20)\d{2})\)\s*$")
_ARTICLES = ("the ", "a ", "an ")


@dataclass(frozen=True)
class ParsedName:
    title: str
    year: int | None
    tmdb_id: int | None
    imdb_id: str | None


def parse_film_folder(name: str) -> ParsedName:
    """Split a folder name such as 'Film (2020) {tmdb-123}' into its parts."""
    tmdb_id: int | None = None
    imdb_id: str | None = None
    for kind, value in _ID_TAG.findall(name):
        kind = kind.lower()
        if kind.startswith("tmdb") and value.isdigit():
            tmdb_id = int(value)
        elif kind.startswith("imdb") and re.fullmatch(r"tt\d+", value):
            imdb_id = value
    rest = _OTHER_TAG.sub("", name).strip()
    year: int | None = None
    match = _YEAR.match(rest)
    if match and match.group("title").strip():
        rest, year = match.group("title").strip(), int(match.group("year"))
    title = rest.strip(" -._") or name.strip()
    return ParsedName(title=title, year=year, tmdb_id=tmdb_id, imdb_id=imdb_id)


def sort_key(title: str) -> str:
    """'The Matrix' sorts under M, and accents don't change the order."""
    key = fold(title)
    for article in _ARTICLES:
        if key.startswith(article) and len(key) > len(article):
            return key[len(article) :]
    return key


def fold(text: str) -> str:
    """Lower-case text without accents, for searching and sorting ('Ärger' -> 'arger')."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def is_video(name: str) -> bool:
    lower = name.lower()
    return not name.startswith(".") and any(lower.endswith(ext) for ext in VIDEO_EXTENSIONS)


def is_tailarr_copy(name: str) -> bool:
    stem = name[:-4] if name.lower().endswith(".mkv") else None
    return stem is not None and stem.endswith(COPY_SUFFIXES)
