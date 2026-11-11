"""The film library: list, details, artwork and re-scanning.

The actions on a film's files (tracks, copies, HDR10) are in actions.py, shared with TV.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.config import AppConfig
from ..core.paths import is_inside
from ..core.settings_store import get_library_settings
from ..library.artwork import thumbnail
from ..library.media_reader import MediaReader
from ..library.models import Film, FilmFile
from ..library.scanner import FilmScanner
from .common import (
    NOT_READ,
    FileOut,
    Item,
    MediaSummaryOut,
    ReadingStatusOut,
    ScanStatusOut,
    files_out,
    get_reader,
    not_found,
    reading_out,
    records_for,
    scan_out,
    summary_of,
    time_of,
)
from .deps import get_config, get_session

router = APIRouter(prefix="/api/films")

# Artwork URLs include the picture's modified time, so browsers can keep them for a long time.
_LONG_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


def get_scanner(request: Request) -> FilmScanner:
    return request.app.state.film_scanner


class FilmOut(BaseModel):
    id: int
    title: str
    year: int | None
    folder_name: str
    poster_url: str | None
    size: int
    added_at: datetime
    file_count: int
    main_file: str | None
    is_mkv: bool
    media: MediaSummaryOut


class FilmListOut(BaseModel):
    root: str
    films: list[FilmOut]
    scan: ScanStatusOut
    reading: ReadingStatusOut


class FilmDetailOut(FilmOut):
    folder: str
    backdrop_url: str | None
    tmdb_id: int | None
    imdb_id: str | None
    files: list[FileOut]


def _film_out(film: Film, media: MediaSummaryOut = NOT_READ) -> dict:
    poster = None
    if film.poster_path:
        poster = f"/api/films/{film.id}/poster?v={int(film.poster_mtime or 0)}"
    return {
        "id": film.id,
        "title": film.title,
        "year": film.year,
        "folder_name": film.folder_name,
        "poster_url": poster,
        "size": film.size,
        "added_at": time_of(film.added_at),
        "file_count": film.file_count,
        "main_file": film.main_file,
        "is_mkv": bool(film.main_file and film.main_file.lower().endswith(".mkv")),
        "media": media,
    }


def _films_root(session: Session, config: AppConfig) -> str:
    return get_library_settings(session, config).movies_dir


@router.get("", response_model=FilmListOut)
def list_films(
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    scanner: Annotated[FilmScanner, Depends(get_scanner)],
    reader: Annotated[MediaReader, Depends(get_reader)],
) -> FilmListOut:
    # Keep the list fresh without the owner having to press anything.
    scanner.start_if_stale()
    root = _films_root(session, config)
    main_files = {
        (f.film_id, f.name): f
        for f in session.exec(select(FilmFile)).all()  # one query, not one per film
    }
    records = records_for(session)
    films = []
    for film in session.exec(select(Film).order_by(Film.sort_title, Film.year)).all():
        if not is_inside(film.folder, root):
            continue
        main = main_files.get((film.id, film.main_file or ""))
        media = summary_of(records.get(main.path), main.size, main.mtime) if main else NOT_READ
        films.append(FilmOut(**_film_out(film, media)))
    return FilmListOut(root=root, films=films, scan=scan_out(scanner), reading=reading_out(reader))


@router.get("/scan", response_model=ScanStatusOut)
def scan_status(scanner: Annotated[FilmScanner, Depends(get_scanner)]) -> ScanStatusOut:
    return scan_out(scanner)


@router.post("/scan", response_model=ScanStatusOut, status_code=202)
def start_scan(scanner: Annotated[FilmScanner, Depends(get_scanner)]) -> ScanStatusOut:
    scanner.start()
    return scan_out(scanner)


def _get_film(session: Session, config: AppConfig, film_id: int) -> Film:
    film = session.get(Film, film_id)
    if film is None or not is_inside(film.folder, _films_root(session, config)):
        raise not_found("film")
    return film


def _files(session: Session, film: Film) -> list[FilmFile]:
    files = session.exec(select(FilmFile).where(FilmFile.film_id == film.id)).all()
    return sorted(files, key=lambda f: (f.name != film.main_file, f.is_copy, f.name))


def subject_of(film: Film) -> str:
    return f"{film.title} ({film.year})" if film.year else film.title


def load_film(session: Session, config: AppConfig, film_id: int) -> Item:
    """A film as an "item", for the actions shared with TV episodes."""
    film = _get_film(session, config, film_id)
    return Item(
        kind="film",
        id=film_id,
        subject=subject_of(film),
        folder=film.folder,
        root=_films_root(session, config),
        main_file=film.main_file,
        files=list(_files(session, film)),
    )


@router.get("/{film_id}", response_model=FilmDetailOut)
def film_detail(
    film_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> FilmDetailOut:
    film = _get_film(session, config, film_id)
    files = _files(session, film)
    backdrop = None
    if film.backdrop_path:
        backdrop = f"/api/films/{film.id}/backdrop?v={int(film.backdrop_mtime or 0)}"
    out_files = files_out(session, list(files), film.main_file)
    main = next((f for f in out_files if f.is_main), None)
    return FilmDetailOut(
        **_film_out(film, main.media if main else NOT_READ),
        folder=film.folder,
        backdrop_url=backdrop,
        tmdb_id=film.tmdb_id,
        imdb_id=film.imdb_id,
        files=out_files,
    )


def _artwork(
    session: Session, config: AppConfig, film_id: int, kind: Literal["poster", "backdrop"]
) -> Path:
    film = _get_film(session, config, film_id)
    stored = film.poster_path if kind == "poster" else film.backdrop_path
    root = _films_root(session, config)
    # Check again at the moment of reading: only pictures inside the Films folder are served.
    if not stored or not is_inside(stored, root) or not Path(stored).is_file():
        raise HTTPException(status_code=404, detail="No picture for this film.")
    return Path(stored)


@router.get("/{film_id}/poster", response_model=None)
def film_poster(
    film_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    size: Literal["small", "full"] = "small",
) -> Response:
    source = _artwork(session, config, film_id, "poster")
    if size == "small":
        small = thumbnail(source, config.config_dir / "cache" / "posters")
        if small is None:
            raise HTTPException(status_code=404, detail="This poster picture can't be read.")
        return FileResponse(small, media_type="image/jpeg", headers=_LONG_CACHE)
    return FileResponse(source, headers=_LONG_CACHE)


@router.get("/{film_id}/backdrop", response_model=None)
def film_backdrop(
    film_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    return FileResponse(_artwork(session, config, film_id, "backdrop"), headers=_LONG_CACHE)
