"""The film library: list, details, artwork and re-scanning."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import defer
from sqlmodel import Session, col, select

from ..core.config import AppConfig
from ..core.disk import free_space
from ..core.paths import is_inside
from ..core.settings_store import get_library_settings
from ..jobs.engine import JobQueue
from ..jobs.track_settings import HARDLINK_REFUSAL, TrackChange, TracksChangedError
from ..jobs.track_settings import KIND as TRACK_SETTINGS
from ..jobs.track_settings import TITLE as TRACK_SETTINGS_TITLE
from ..jobs.track_settings import plan as plan_track_settings
from ..library.artwork import thumbnail
from ..library.media_reader import MediaReader, details_of, is_current
from ..library.models import Film, FilmFile, MediaRecord
from ..library.scanner import FilmScanner
from ..media.describe import HdrInfo
from ..media.probe import MediaDetails
from .deps import get_config, get_session
from .jobs import JobOut, get_queue, job_out

router = APIRouter(prefix="/api/films")

# Artwork URLs include the picture's modified time, so browsers can keep them for a long time.
_LONG_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


def get_scanner(request: Request) -> FilmScanner:
    return request.app.state.film_scanner


def get_reader(request: Request) -> MediaReader:
    return request.app.state.media_reader


class ScanStatusOut(BaseModel):
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    film_count: int | None
    error: str | None


class ReadingStatusOut(BaseModel):
    """Progress of reading tracks/HDR details of new or changed files in the background."""

    running: bool
    done: int
    total: int


class MediaSummaryOut(BaseModel):
    """The headline facts about one file, for badges and filters."""

    read: bool  # False: Tailarr hasn't read this file's details yet
    error: bool = False
    hdr: list[str] = []  # "Dolby Vision", "HDR10+", "HDR10", "HLG"; empty = SDR
    dv_profile: str | None = None  # "8.1", "7", "5"
    resolution: str | None = None  # "4K", "1080p", ...


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


class FilmFileOut(BaseModel):
    name: str
    size: int
    modified_at: datetime
    is_mkv: bool
    is_copy: bool
    is_main: bool
    hardlinked: bool
    media: MediaSummaryOut


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


_NOT_READ = MediaSummaryOut(read=False)


def _summary(record: MediaRecord | None, size: int, mtime: float) -> MediaSummaryOut:
    if record is None or not is_current(record, size, mtime):
        return _NOT_READ
    return MediaSummaryOut(
        read=True,
        error=record.error is not None,
        hdr=[f for f in record.hdr.split(",") if f],
        dv_profile=record.dv_profile,
        resolution=record.resolution,
    )


def _records(session: Session, paths: list[str] | None = None) -> dict[str, MediaRecord]:
    query = select(MediaRecord)
    if paths is not None:
        query = query.where(col(MediaRecord.path).in_(paths))
    # The stored tool output isn't needed for summaries; don't load it.
    query = query.options(defer(MediaRecord.raw), defer(MediaRecord.error_details))  # type: ignore[arg-type]
    return {r.path: r for r in session.exec(query).all()}


def _film_out(film: Film, media: MediaSummaryOut = _NOT_READ) -> dict:
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
    records = _records(session)
    films = []
    for film in session.exec(select(Film).order_by(Film.sort_title, Film.year)).all():
        if not is_inside(film.folder, root):
            continue
        main = main_files.get((film.id, film.main_file or ""))
        media = _summary(records.get(main.path), main.size, main.mtime) if main else _NOT_READ
        films.append(FilmOut(**_film_out(film, media)))
    status = reader.status()
    return FilmListOut(
        root=root,
        films=films,
        scan=_scan_out(scanner),
        reading=ReadingStatusOut(running=status.running, done=status.done, total=status.total),
    )


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


def _files(session: Session, film: Film) -> list[FilmFile]:
    files = session.exec(select(FilmFile).where(FilmFile.film_id == film.id)).all()
    return sorted(files, key=lambda f: (f.name != film.main_file, f.is_copy, f.name))


@router.get("/{film_id}", response_model=FilmDetailOut)
def film_detail(
    film_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> FilmDetailOut:
    film = _get_film(session, config, film_id)
    files = _files(session, film)
    records = _records(session, [f.path for f in files])
    backdrop = None
    if film.backdrop_path:
        backdrop = f"/api/films/{film.id}/backdrop?v={int(film.backdrop_mtime or 0)}"
    main = next((f for f in files if f.name == film.main_file), None)
    main_media = _summary(records.get(main.path), main.size, main.mtime) if main else _NOT_READ
    return FilmDetailOut(
        **_film_out(film, main_media),
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
                media=_summary(records.get(f.path), f.size, f.mtime),
            )
            for f in files
        ],
    )


# -- what's inside a file ----------------------------------------------------------


class HdrOut(BaseModel):
    formats: list[str]  # empty = SDR
    dv_profile: str | None
    dv_fallback: str | None  # what non-Dolby Vision players show: "HDR10", "SDR", "HLG" or None
    dv_dual_layer: bool
    can_remove_dv: bool


class TrackOut(BaseModel):
    id: int
    uid: str
    type: Literal["video", "audio", "subtitles"]
    codec: str
    codec_id: str
    language: str
    language_name: str
    name: str
    default: bool
    forced: bool
    enabled: bool
    hearing_impaired: bool
    visual_impaired: bool
    commentary: bool
    original: bool
    width: int | None
    height: int | None
    resolution: str | None
    frame_rate: str | None
    bit_depth: int | None
    hdr: HdrOut | None
    channels: int | None
    channel_layout: str | None
    sample_rate: int | None
    picture_based: bool | None


class AttachmentOut(BaseModel):
    name: str
    mime_type: str
    size: int


class MediaOut(BaseModel):
    file: str
    size: int
    read_at: datetime
    # When the file couldn't be read: a plain-English reason, plus the tools' own words.
    error: str | None = None
    error_details: str | None = None
    container: str | None = None
    title: str | None = None
    duration: float | None = None  # seconds
    resolution: str | None = None
    hdr: HdrOut | None = None
    hdr_checked: bool = True
    tracks: list[TrackOut] = []
    chapters: int = 0
    attachments: list[AttachmentOut] = []


def _hdr_out(hdr: HdrInfo) -> HdrOut:
    return HdrOut(
        formats=hdr.formats,
        dv_profile=hdr.dv_label,
        dv_fallback=hdr.dv_fallback,
        dv_dual_layer=hdr.dv_dual_layer,
        can_remove_dv=hdr.can_remove_dv,
    )


def _media_out(file: FilmFile, record: MediaRecord, details: MediaDetails | None) -> MediaOut:
    out = MediaOut(
        file=file.name,
        size=record.size,
        read_at=_time(record.read_at),  # type: ignore[arg-type]
        error=record.error,
        error_details=record.error_details,
    )
    if details is None:
        return out
    out.container = details.container
    out.title = details.title
    out.duration = details.duration
    out.resolution = details.resolution
    out.hdr = _hdr_out(details.hdr)
    out.hdr_checked = details.hdr_checked
    out.chapters = details.chapters
    out.attachments = [AttachmentOut(**vars(a)) for a in details.attachments]
    out.tracks = [
        TrackOut(**{**vars(t), "hdr": _hdr_out(t.hdr) if t.hdr else None})  # type: ignore[arg-type]
        for t in details.tracks
    ]
    return out


@router.get("/{film_id}/media", response_model=MediaOut)
def film_media(
    film_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
    file: str | None = None,
    refresh: bool = False,
) -> MediaOut:
    """The tracks, chapters, attachments and HDR details of one of the film's files.

    Reads the file now if Tailarr doesn't know it yet (this can take a few seconds
    if the disk has to spin up). `refresh=true` reads it again regardless.
    """
    film = _get_film(session, config, film_id)
    files = _files(session, film)
    wanted = file or film.main_file
    match = next((f for f in files if f.name == wanted), None)
    root = _films_root(session, config)
    if match is None or not is_inside(match.path, root):
        raise HTTPException(status_code=404, detail="This file isn't in the film's folder.")
    try:
        record = reader.get(session, match.path, refresh=refresh)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="This file isn't there any more. Press \u201cCheck for new films\u201d "
            "on the Films page to bring the list up to date.",
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Tailarr couldn't open this file ({error.strerror or error}). "
            "Check that the disk holding it is available.",
        ) from error
    return _media_out(match, record, details_of(record))


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


# -- changing track settings ---------------------------------------------------------


class TrackSettingsIn(BaseModel):
    file: str
    changes: list[TrackChange]


class TrackSettingsConfirmIn(TrackSettingsIn):
    # The owner pressed the confirm button in the summary.
    confirmed: bool = False
    # The owner ticked "I understand" for a hardlinked (seeding) file.
    allow_hardlinked: bool = False


class PlannedTrackOut(BaseModel):
    uid: str
    label: str
    changes: list[str]


class TrackSettingsPreviewOut(BaseModel):
    """What saving would do, for the summary shown before anything changes."""

    film_id: int
    file: str
    path: str
    tracks: list[PlannedTrackOut]
    hardlinked: bool  # the file is also in another folder (usually still seeding)
    free_space: int  # bytes free on the disk holding the file


def _mkv_file(session: Session, config: AppConfig, film: Film, name: str) -> FilmFile:
    match = next((f for f in _files(session, film) if f.name == name), None)
    if match is None or not is_inside(match.path, _films_root(session, config)):
        raise HTTPException(status_code=404, detail="This file isn't in the film's folder.")
    if not match.is_mkv:
        raise HTTPException(
            status_code=400, detail="Tailarr can only change track settings in MKV files."
        )
    return match


def _preview(
    session: Session, config: AppConfig, reader: MediaReader, film_id: int, body: TrackSettingsIn
) -> TrackSettingsPreviewOut:
    film = _get_film(session, config, film_id)
    file = _mkv_file(session, config, film, body.file)
    if not body.changes:
        raise HTTPException(status_code=400, detail="No track settings were changed.")
    try:
        record = reader.get(session, file.path)
        stat = os.stat(file.path)
    except OSError as error:
        raise HTTPException(
            status_code=404,
            detail="This file can't be opened any more. Press “Check for new films” "
            "on the Films page to bring the list up to date.",
        ) from error
    details = details_of(record)
    if details is None:
        raise HTTPException(
            status_code=400, detail="Tailarr couldn't read this file, so it can't change it."
        )
    try:
        planned = plan_track_settings(details, body.changes)
    except TracksChangedError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not planned:
        raise HTTPException(
            status_code=400, detail="Nothing to change: the tracks already have these settings."
        )
    return TrackSettingsPreviewOut(
        film_id=film_id,
        file=file.name,
        path=file.path,
        tracks=[PlannedTrackOut(uid=p.uid, label=p.label, changes=p.changes) for p in planned],
        hardlinked=stat.st_nlink > 1,
        free_space=free_space(Path(file.path).parent),
    )


@router.post("/{film_id}/track-settings/preview", response_model=TrackSettingsPreviewOut)
def preview_track_settings(
    film_id: int,
    body: TrackSettingsIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
) -> TrackSettingsPreviewOut:
    """The summary to confirm before changing a file's track settings. Changes nothing."""
    return _preview(session, config, reader, film_id, body)


@router.post("/{film_id}/track-settings", response_model=JobOut, status_code=202)
def change_track_settings(
    film_id: int,
    body: TrackSettingsConfirmIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> JobOut:
    """Queue a job that changes the original file's track settings (after confirmation)."""
    if not body.confirmed:
        raise HTTPException(
            status_code=400,
            detail="This changes the original file, so it needs your confirmation first.",
        )
    preview = _preview(session, config, reader, film_id, body)
    if preview.hardlinked and not body.allow_hardlinked:
        raise HTTPException(status_code=409, detail=HARDLINK_REFUSAL)
    film = _get_film(session, config, film_id)
    subject = f"{film.title} ({film.year})" if film.year else film.title
    job = queue.submit(
        TRACK_SETTINGS,
        title=TRACK_SETTINGS_TITLE,
        subject=subject,
        path=preview.path,
        film_id=film_id,
        params={
            "changes": [c.model_dump(exclude_none=True) for c in body.changes],
            "allow_hardlinked": body.allow_hardlinked,
        },
    )
    return job_out(job)
