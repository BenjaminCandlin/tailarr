"""The film library: list, details, artwork and re-scanning."""

from __future__ import annotations

from datetime import UTC, datetime
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
from ..library.models import Film, FilmFile
from ..library.scanner import FilmScanner
from .deps import get_config, get_session

router = APIRouter(prefix="/api/films")

# Artwork URLs include the picture's modified time, so browsers can keep them for a long time.
_LONG_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


def get_scanner(request: Request) -> FilmScanner:
    return request.app.state.film_scanner


class ScanStatusOut(BaseModel):
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    film_count: int | None
    error: str | None


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


class FilmListOut(BaseModel):
    root: str
    films: list[FilmOut]
    scan: ScanStatusOut


class FilmFileOut(BaseModel):
    name: str
    size: int
    modified_at: datetime
    is_mkv: bool
    is_copy: bool
    is_main: bool
    hardlinked: bool


class FilmDetailOut(FilmOut):
    folder: str
    backdrop_url: str | None
    tmdb_id: int | None
    imdb_id: str | None
    files: list[FilmFileOut]


def _time(seconds: float | None) -> datetime | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, UTC)


def _scan_out(scanner: FilmScanner) -> ScanStatusOut:
    status = scanner.status()
    return ScanStatusOut(
        running=status.running,
        started_at=_time(status.started_at),
        finished_at=_time(status.finished_at),
        film_count=status.film_count,
        error=status.error,
    )


def _film_out(film: Film) -> dict:
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
        "added_at": _time(film.added_at),
        "file_count": film.file_count,
        "main_file": film.main_file,
        "is_mkv": bool(film.main_file and film.main_file.lower().endswith(".mkv")),
    }


def _films_root(session: Session, config: AppConfig) -> str:
    return get_library_settings(session, config).movies_dir


@router.get("", response_model=FilmListOut)
def list_films(
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    scanner: Annotated[FilmScanner, Depends(get_scanner)],
) -> FilmListOut:
    # Keep the list fresh without the owner having to press anything.
    scanner.start_if_stale()
    root = _films_root(session, config)
    films = [
        FilmOut(**_film_out(film))
        for film in session.exec(select(Film).order_by(Film.sort_title, Film.year)).all()
        if is_inside(film.folder, root)
    ]
    return FilmListOut(root=root, films=films, scan=_scan_out(scanner))


@router.get("/scan", response_model=ScanStatusOut)
def scan_status(scanner: Annotated[FilmScanner, Depends(get_scanner)]) -> ScanStatusOut:
    return _scan_out(scanner)


@router.post("/scan", response_model=ScanStatusOut, status_code=202)
def start_scan(scanner: Annotated[FilmScanner, Depends(get_scanner)]) -> ScanStatusOut:
    scanner.start()
    return _scan_out(scanner)


def _get_film(session: Session, config: AppConfig, film_id: int) -> Film:
    film = session.get(Film, film_id)
    if film is None or not is_inside(film.folder, _films_root(session, config)):
        raise HTTPException(
            status_code=404,
            detail="This film isn't in your library any more. It may have been moved or deleted.",
        )
    return film


@router.get("/{film_id}", response_model=FilmDetailOut)
def film_detail(
    film_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> FilmDetailOut:
    film = _get_film(session, config, film_id)
    files = session.exec(select(FilmFile).where(FilmFile.film_id == film.id)).all()
    backdrop = None
    if film.backdrop_path:
        backdrop = f"/api/films/{film.id}/backdrop?v={int(film.backdrop_mtime or 0)}"
    return FilmDetailOut(
        **_film_out(film),
        folder=film.folder,
        backdrop_url=backdrop,
        tmdb_id=film.tmdb_id,
        imdb_id=film.imdb_id,
        files=[
            FilmFileOut(
                name=f.name,
                size=f.size,
                modified_at=_time(f.mtime),  # type: ignore[arg-type]
                is_mkv=f.is_mkv,
                is_copy=f.is_copy,
                is_main=f.name == film.main_file,
                hardlinked=f.links > 1,
            )
            for f in sorted(files, key=lambda f: (f.name != film.main_file, f.is_copy, f.name))
        ],
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
