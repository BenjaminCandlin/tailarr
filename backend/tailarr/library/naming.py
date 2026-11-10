"""Understanding film folder and file names.

Radarr names film folders like ``Film Title (2020)``, and the TRaSH Guides
naming scheme adds database ids such as ``{tmdb-12345}`` or ``{imdb-tt0123456}``.
"""

from __future__ import annotations

import datetime
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
# A year in brackets: "Film (2020)", "Film [2020]".
_BRACKET_YEAR = re.compile(r"[(\[{]\s*((?:19|20)\d{2})\s*[)\]}]")
# Words that start the technical part of a release name ("Film.2020.1080p.BluRay.x264-GROUP").
_RELEASE_WORDS = re.compile(
    r"^(?:\d{3,4}p|4k|uhd|hdr|hdr10|dv|bluray|blu-ray|bdrip|brrip|remux|web|web-?dl|webrip|"
    r"hdtv|dvdrip|x264|x265|h\.?264|h\.?265|hevc|avc|xvid|proper|repack|extended|unrated|"
    r"imax|10bit|dts|truehd|atmos|aac|ac3|dd5\.1|ddp5\.1)$",
    re.I,
)
_ARTICLES = ("the ", "a ", "an ")


@dataclass(frozen=True)
class ParsedName:
    title: str
    year: int | None
    tmdb_id: int | None
    imdb_id: str | None


def _latest_year() -> int:
    return datetime.date.today().year + 1


def _release_words(text: str) -> list[str]:
    """'A.Beautiful.Mind.2001.1080p' -> ['A', 'Beautiful', 'Mind', '2001', '1080p']."""
    if " " not in text.strip() or text.count(".") + text.count("_") > text.count(" "):
        text = re.sub(r"[._]+", " ", text)
    return text.split()


def _split_title_year(text: str) -> tuple[str, int | None]:
    # 1. A year in brackets is the most reliable sign.
    matches = list(_BRACKET_YEAR.finditer(text))
    for match in reversed(matches):
        title = _OTHER_TAG.sub("", text[: match.start()]).strip(" -._")
        if title and int(match.group(1)) <= _latest_year():
            return title, int(match.group(1))
    text = _OTHER_TAG.sub("", text).strip()

    # 2. Release names: the last plausible year with words before it ends the title.
    words = _release_words(text)
    for i in range(len(words) - 1, 0, -1):
        word = words[i].strip("()")
        if re.fullmatch(r"(?:19|20)\d{2}", word) and 1900 <= int(word) <= _latest_year():
            rest = words[i + 1 :]
            # Only treat it as the year if nothing but technical words (or nothing) follows,
            # or the name clearly is a release name.
            if not rest or _RELEASE_WORDS.match(rest[0]) or len(words) != len(text.split()):
                return " ".join(words[:i]).strip(" -"), int(word)

    # 3. No year: still drop technical words ("Film 1080p BluRay" -> "Film").
    for i, word in enumerate(words):
        if i > 0 and _RELEASE_WORDS.match(word):
            return " ".join(words[:i]).strip(" -"), None
    return " ".join(words).strip(" -"), None


def parse_film_folder(name: str) -> ParsedName:
    """Split a folder (or file) name into title, year and database ids.

    Handles Radarr names ("Film (2020)", "Film (2020) {tmdb-123}"), bracketed
    years ("Film [2020]") and release names ("Film.2020.1080p.BluRay.x264-GRP").
    """
    tmdb_id: int | None = None
    imdb_id: str | None = None
    for kind, value in _ID_TAG.findall(name):
        kind = kind.lower()
        if kind.startswith("tmdb") and value.isdigit():
            tmdb_id = int(value)
        elif kind.startswith("imdb") and re.fullmatch(r"tt\d+", value):
            imdb_id = value
    title, year = _split_title_year(name)
    return ParsedName(title=title or name.strip(), year=year, tmdb_id=tmdb_id, imdb_id=imdb_id)


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
