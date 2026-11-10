"""Database tables for the library.

These tables are a *cache* of what is on disk, rebuilt by scanning. When their
layout changes, LIBRARY_CACHE_VERSION goes up and the tables are simply
emptied and refilled by the next scan (no migrations needed).
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel

LIBRARY_CACHE_VERSION = 1


class Film(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    folder: str = Field(index=True, unique=True)  # full path of the film's folder
    folder_name: str
    title: str
    sort_title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    poster_path: str | None = None
    poster_mtime: float | None = None
    backdrop_path: str | None = None
    backdrop_mtime: float | None = None
    main_file: str | None = None  # name of the film's own video file (not a copy)
    size: int = 0  # total size of the video files, in bytes
    added_at: float = 0  # modified time of the main video file (seconds since 1970)
    file_count: int = 0


class FilmFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    film_id: int = Field(index=True, foreign_key="film.id")
    name: str
    path: str
    size: int
    mtime: float
    is_mkv: bool
    is_copy: bool  # a copy Tailarr made ("- HDR10.mkv", "- Tailarr.mkv")
    links: int = 1  # more than 1: the same file also exists elsewhere (e.g. still seeding)


CACHE_TABLES = (FilmFile, Film)
