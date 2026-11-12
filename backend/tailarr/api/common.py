"""Pieces shared by the film and TV pages: file summaries, track details and "items".

An *item* is one film or one episode: a folder holding its own video file and any
copies Tailarr made of it. Every action (change track settings, remove tracks,
make an HDR10 copy, replace the original) works on an item's files the same way,
whether it's a film or an episode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import defer
from sqlmodel import Session, col, select

from ..core.config import AppConfig
from ..jobs.models import CopyRecord
from ..library.media_reader import MediaReader, is_current
from ..library.models import EpisodeFile, FilmFile, MediaRecord
from ..library.scanner import LibraryScanner
from ..media.describe import HdrInfo
from ..media.probe import MediaDetails

LibraryFile = FilmFile | EpisodeFile


def get_reader(request: Request) -> MediaReader:
    return request.app.state.media_reader


def time_of(seconds: float | None) -> datetime | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, UTC)


class ScanStatusOut(BaseModel):
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    film_count: int | None  # how many films (or shows) the last scan found
    error: str | None


def scan_out(scanner: LibraryScanner) -> ScanStatusOut:
    status = scanner.status()
    return ScanStatusOut(
        running=status.running,
        started_at=time_of(status.started_at),
        finished_at=time_of(status.finished_at),
        film_count=status.film_count,
        error=status.error,
    )


class ReadingStatusOut(BaseModel):
    """Progress of reading tracks/HDR details of new or changed files in the background."""

    running: bool
    done: int
    total: int


def reading_out(reader: MediaReader) -> ReadingStatusOut:
    status = reader.status()
    return ReadingStatusOut(running=status.running, done=status.done, total=status.total)


class MediaSummaryOut(BaseModel):
    """The headline facts about one file, for badges and filters."""

    read: bool  # False: Tailarr hasn't read this file's details yet
    error: bool = False
    hdr: list[str] = []  # "Dolby Vision", "HDR10+", "HDR10", "HLG"; empty = SDR
    dv_profile: str | None = None  # "8.1", "7", "5"
    resolution: str | None = None  # "4K", "1080p", ...


NOT_READ = MediaSummaryOut(read=False)


def summary_of(record: MediaRecord | None, size: int, mtime: float) -> MediaSummaryOut:
    if record is None or not is_current(record, size, mtime):
        return NOT_READ
    return MediaSummaryOut(
        read=True,
        error=record.error is not None,
        hdr=[f for f in record.hdr.split(",") if f],
        dv_profile=record.dv_profile,
        resolution=record.resolution,
    )


def records_for(session: Session, paths: list[str] | None = None) -> dict[str, MediaRecord]:
    query = select(MediaRecord)
    if paths is not None:
        query = query.where(col(MediaRecord.path).in_(paths))
    # The stored tool output isn't needed for summaries; don't load it.
    query = query.options(defer(MediaRecord.raw), defer(MediaRecord.error_details))  # type: ignore[arg-type]
    return {r.path: r for r in session.exec(query).all()}


class FileOut(BaseModel):
    name: str
    size: int
    modified_at: datetime
    is_mkv: bool
    is_copy: bool
    is_main: bool
    hardlinked: bool
    media: MediaSummaryOut
    # For copies Tailarr made: the file it was made from, and whether that original can
    # be replaced with this copy (the original is still there, unchanged since).
    copy_of: str | None = None
    can_replace_original: bool = False


def files_out(session: Session, files: list[LibraryFile], main_file: str | None) -> list[FileOut]:
    records = records_for(session, [f.path for f in files])
    copies = {
        c.path: c
        for c in session.exec(
            select(CopyRecord).where(col(CopyRecord.path).in_([f.path for f in files]))
        ).all()
    }
    by_path = {f.path: f for f in files}

    def replaceable(record: CopyRecord | None) -> bool:
        source = by_path.get(record.source_path) if record else None
        return (
            record is not None
            and source is not None
            and source.size == record.source_size
            and abs(source.mtime - record.source_mtime) < 1e-3
        )

    return [
        FileOut(
            name=f.name,
            size=f.size,
            modified_at=time_of(f.mtime),  # type: ignore[arg-type]
            is_mkv=f.is_mkv,
            is_copy=f.is_copy,
            is_main=f.name == main_file,
            hardlinked=f.links > 1,
            media=summary_of(records.get(f.path), f.size, f.mtime),
            copy_of=Path(copies[f.path].source_path).name if f.path in copies else None,
            can_replace_original=replaceable(copies.get(f.path)),
        )
        for f in files
    ]


# -- items ------------------------------------------------------------------------------


@dataclass
class Item:
    """One film or one episode, with its files."""

    kind: Literal["film", "episode"]
    id: int
    subject: str  # "Blade Runner (1982)", "Test Show – S01E02 – The Second One"
    folder: str
    root: str  # the Films or TV folder it belongs to
    main_file: str | None
    files: list[LibraryFile]

    @property
    def job_link(self) -> dict[str, int]:
        """The column a job uses to point back at this item."""
        return {"film_id": self.id} if self.kind == "film" else {"episode_id": self.id}

    @property
    def scan_hint(self) -> str:
        if self.kind == "film":
            return "Press “Check for new films” on the Films page"
        return "Press “Check for new episodes” on the TV page"


# Loads an item by id, raising a 404 HTTPException if it isn't in the library.
ItemLoader = Callable[[Session, AppConfig, int], Item]


def not_found(kind: str) -> HTTPException:
    what = "film" if kind == "film" else "episode"
    return HTTPException(
        status_code=404,
        detail=f"This {what} isn't in your library any more. It may have been moved or deleted.",
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


def hdr_out(hdr: HdrInfo) -> HdrOut:
    return HdrOut(
        formats=hdr.formats,
        dv_profile=hdr.dv_label,
        dv_fallback=hdr.dv_fallback,
        dv_dual_layer=hdr.dv_dual_layer,
        can_remove_dv=hdr.can_remove_dv,
    )


def media_out(file: LibraryFile, record: MediaRecord, details: MediaDetails | None) -> MediaOut:
    out = MediaOut(
        file=file.name,
        size=record.size,
        read_at=time_of(record.read_at),  # type: ignore[arg-type]
        error=record.error,
        error_details=record.error_details,
    )
    if details is None:
        return out
    out.container = details.container
    out.title = details.title
    out.duration = details.duration
    out.resolution = details.resolution
    out.hdr = hdr_out(details.hdr)
    out.hdr_checked = details.hdr_checked
    out.chapters = details.chapters
    out.attachments = [AttachmentOut(**vars(a)) for a in details.attachments]
    out.tracks = [
        TrackOut(
            **{
                k: v
                for k, v in vars(t).items()
                if k not in ("default_duration", "display_dimensions", "hdr")
            },
            hdr=hdr_out(t.hdr) if t.hdr else None,
        )
        for t in details.tracks
    ]
    return out
