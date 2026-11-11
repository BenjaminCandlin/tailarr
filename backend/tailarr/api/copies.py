"""Copies of films: save a copy without some tracks, and replace an original with a copy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..core.config import AppConfig
from ..core.disk import SAFETY_MARGIN, free_space
from ..core.settings_store import get_recycle_settings
from ..jobs import hdr10_copy, remove_tracks, replace_original
from ..jobs.engine import JobFailed, JobQueue
from ..jobs.models import CopyRecord
from ..jobs.recycle import RECYCLE_FOLDER
from ..jobs.track_settings import TrackChange, TracksChangedError
from ..library.media_reader import MediaReader, details_of
from ..library.models import Film, FilmFile
from ..library.naming import is_tailarr_copy
from .deps import get_config, get_session
from .films import _get_film, _mkv_file, get_reader
from .jobs import JobOut, get_queue, job_out

router = APIRouter(prefix="/api/films")


def _subject(film: Film) -> str:
    return f"{film.title} ({film.year})" if film.year else film.title


def _cant_open(error: OSError) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail="This file can't be opened any more. Press “Check for new films” "
        "on the Films page to bring the list up to date.",
    )


# -- save a copy without some tracks ------------------------------------------------------


class RemoveTracksIn(BaseModel):
    file: str
    remove: list[str]  # unique IDs of the tracks to leave out
    changes: list[TrackChange] = []  # settings for the kept tracks, applied to the copy


class RemoveTracksConfirmIn(RemoveTracksIn):
    confirmed: bool = False
    overwrite: bool = False  # replace an existing Tailarr copy with the same name


class SettingChangeOut(BaseModel):
    label: str
    changes: list[str]


class RemoveTracksPreviewOut(BaseModel):
    film_id: int
    file: str
    new_file: str
    exists: bool  # a file with the new copy's name is already there (a Tailarr copy)
    updates_copy: bool  # the file being copied is itself that Tailarr copy
    removed: list[str]  # "Audio 3: Japanese – AAC, Stereo"
    kept: list[str]
    settings: list[SettingChangeOut]
    warnings: list[str]
    space_needed: int
    free_space: int
    enough_space: bool


def _copy_preview(
    session: Session, config: AppConfig, reader: MediaReader, film_id: int, body: RemoveTracksIn
) -> tuple[RemoveTracksPreviewOut, FilmFile]:
    film = _get_film(session, config, film_id)
    file = _mkv_file(session, config, film, body.file)
    try:
        record = reader.get(session, file.path)
        size = os.stat(file.path).st_size
    except OSError as error:
        raise _cant_open(error) from error
    details = details_of(record)
    if details is None:
        raise HTTPException(
            status_code=400, detail="Tailarr couldn't read this file, so it can't copy it."
        )
    try:
        plan = remove_tracks.plan_copy(details, body.remove, body.changes)
    except TracksChangedError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except remove_tracks.CopyRefusedError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    new_name = remove_tracks.output_name(file.name)
    new_path = Path(file.path).with_name(new_name)
    exists = new_path.exists()
    if exists and not is_tailarr_copy(new_name):
        raise HTTPException(
            status_code=409,
            detail=f"A file called “{new_name}” is already there and it isn't a copy "
            "made by Tailarr, so Tailarr won't replace it.",
        )
    free = free_space(new_path.parent)
    preview = RemoveTracksPreviewOut(
        film_id=film_id,
        file=file.name,
        new_file=new_name,
        exists=exists,
        updates_copy=new_name == file.name,
        removed=[remove_tracks.describe_track(t, details) for t in plan.removed],
        kept=[remove_tracks.describe_track(t, details) for t in plan.kept],
        settings=[
            SettingChangeOut(label=remove_tracks.track_label(t, details), changes=lines)
            for t, lines in plan.setting_changes()
        ],
        warnings=plan.warnings,
        space_needed=size + SAFETY_MARGIN,
        free_space=free,
        enough_space=free >= size + SAFETY_MARGIN,
    )
    return preview, file


@router.post("/{film_id}/remove-tracks/preview", response_model=RemoveTracksPreviewOut)
def preview_remove_tracks(
    film_id: int,
    body: RemoveTracksIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
) -> RemoveTracksPreviewOut:
    """The summary to confirm before making a copy without some tracks. Changes nothing."""
    return _copy_preview(session, config, reader, film_id, body)[0]


@router.post("/{film_id}/remove-tracks", response_model=JobOut, status_code=202)
def start_remove_tracks(
    film_id: int,
    body: RemoveTracksConfirmIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> JobOut:
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Please confirm the summary first.")
    preview, file = _copy_preview(session, config, reader, film_id, body)
    if preview.exists and not body.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"A copy called “{preview.new_file}” already exists. Tick "
            "“Replace the existing copy” to replace it.",
        )
    if not preview.enough_space:
        raise HTTPException(
            status_code=507,
            detail="Not enough free space on the disk for the copy. Free up some space and "
            "try again.",
        )
    film = _get_film(session, config, film_id)
    job = queue.submit(
        remove_tracks.KIND,
        title=remove_tracks.TITLE,
        subject=_subject(film),
        path=file.path,
        film_id=film_id,
        params={
            "remove": body.remove,
            "changes": [c.model_dump(exclude_none=True) for c in body.changes],
            "overwrite": body.overwrite,
        },
    )
    return job_out(job)


# -- replace the original with a copy ----------------------------------------------------


class ReplaceOriginalIn(BaseModel):
    copy_file: str  # the copy's file name, in the film's folder


class ReplaceOriginalConfirmIn(ReplaceOriginalIn):
    confirmed: bool = False
    understood: bool = False  # ticked "I understand the original will be moved..."


class ReplaceOriginalPreviewOut(BaseModel):
    film_id: int
    original: str
    original_size: int
    copy_file: str
    copy_size: int
    hardlinked: bool  # the original is also in the downloads folder (still seeding)
    keep_days: int
    recycle_folder: str


def _replace_preview(
    session: Session, config: AppConfig, film_id: int, body: ReplaceOriginalIn
) -> tuple[ReplaceOriginalPreviewOut, FilmFile, FilmFile, Film]:
    film = _get_film(session, config, film_id)
    copy = _mkv_file(session, config, film, body.copy_file)
    engine = session.get_bind()
    record = session.get(CopyRecord, copy.path)
    if record is None:
        raise HTTPException(status_code=400, detail=replace_original.NO_RECORD)
    if record.kind != replace_original.REPLACEABLE_KIND:
        raise HTTPException(status_code=400, detail=replace_original.NOT_REPLACEABLE)
    original = _mkv_file(session, config, film, Path(record.source_path).name)
    if original.path != record.source_path:
        raise HTTPException(status_code=400, detail=replace_original.NO_RECORD)
    try:
        replace_original.check_copy_record(engine, original.path, copy.path)  # type: ignore[arg-type]
        original_stat, copy_stat = os.stat(original.path), os.stat(copy.path)
    except JobFailed as error:
        raise HTTPException(status_code=409, detail=error.message) from error
    except OSError as error:
        raise _cant_open(error) from error
    preview = ReplaceOriginalPreviewOut(
        film_id=film_id,
        original=original.name,
        original_size=original_stat.st_size,
        copy_file=copy.name,
        copy_size=copy_stat.st_size,
        hardlinked=original_stat.st_nlink > 1,
        keep_days=get_recycle_settings(session).keep_days,
        recycle_folder=str(Path(original.path).parent / RECYCLE_FOLDER),
    )
    return preview, original, copy, film


@router.post("/{film_id}/replace-original/preview", response_model=ReplaceOriginalPreviewOut)
def preview_replace_original(
    film_id: int,
    body: ReplaceOriginalIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> ReplaceOriginalPreviewOut:
    """The summary to confirm before replacing an original with a copy. Changes nothing."""
    return _replace_preview(session, config, film_id, body)[0]


@router.post("/{film_id}/replace-original", response_model=JobOut, status_code=202)
def start_replace_original(
    film_id: int,
    body: ReplaceOriginalConfirmIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> JobOut:
    if not (body.confirmed and body.understood):
        raise HTTPException(
            status_code=400,
            detail="This replaces your original file, so it needs your confirmation first.",
        )
    _, original, copy, film = _replace_preview(session, config, film_id, body)
    job = queue.submit(
        replace_original.KIND,
        title=replace_original.TITLE,
        subject=_subject(film),
        path=original.path,
        film_id=film_id,
        params={"copy": copy.path},
    )
    return job_out(job)


# -- make a copy without Dolby Vision ----------------------------------------------------


class Hdr10CopyIn(BaseModel):
    file: str


class Hdr10CopyConfirmIn(Hdr10CopyIn):
    confirmed: bool = False
    overwrite: bool = False  # replace an existing Tailarr HDR10 copy


class SpaceNeedOut(BaseModel):
    label: str
    needed: int
    free: int
    enough: bool


class Hdr10CopyPreviewOut(BaseModel):
    film_id: int
    file: str
    new_file: str
    exists: bool
    dv_profile: str
    blu_ray_layers: bool  # profile 7 with an enhancement layer, which is left out too
    result: list[str]  # what players show the copy as, e.g. ["HDR10"], ["HDR10+", "HDR10"]
    kept: list[str]  # the other tracks, all kept
    chapters: int
    attachments: int
    uses_work_folder: bool
    space: list[SpaceNeedOut]
    enough_space: bool


def _hdr10_preview(
    session: Session, config: AppConfig, reader: MediaReader, film_id: int, file_name: str
) -> tuple[Hdr10CopyPreviewOut, FilmFile]:
    film = _get_film(session, config, film_id)
    file = _mkv_file(session, config, film, file_name)
    try:
        record = reader.get(session, file.path)
        size = os.stat(file.path).st_size
    except OSError as error:
        raise _cant_open(error) from error
    details = details_of(record)
    if details is None:
        raise HTTPException(
            status_code=400, detail="Tailarr couldn't read this file, so it can't copy it."
        )
    if not details.hdr_checked:
        raise HTTPException(
            status_code=400,
            detail="MediaInfo couldn't read this file, so Tailarr can't tell how its Dolby "
            "Vision is stored. Try \u201cTry again\u201d on the film page.",
        )
    try:
        plan = hdr10_copy.plan_hdr10(details)
    except hdr10_copy.Hdr10Refused as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    new_name = hdr10_copy.output_name(file.name)
    new_path = Path(file.path).with_name(new_name)
    exists = new_path.exists()
    if exists and not is_tailarr_copy(new_name):
        raise HTTPException(
            status_code=409,
            detail=f"A file called \u201c{new_name}\u201d is already there and it isn't a copy "
            "made by Tailarr, so Tailarr won't replace it.",
        )
    work = hdr10_copy.usable_work_folder(config.work_dir)
    needs = hdr10_copy.space_needs(size, new_path.parent, work)
    preview = Hdr10CopyPreviewOut(
        film_id=film_id,
        file=file.name,
        new_file=new_name,
        exists=exists,
        dv_profile=plan.profile,
        blu_ray_layers=details.hdr.dv_dual_layer,
        result=plan.expected_formats,
        kept=[
            remove_tracks.describe_track(t, details)
            for t in plan.kept_others
            if t not in plan.dropped
        ],
        chapters=details.chapters,
        attachments=len(details.attachments),
        uses_work_folder=work is not None,
        space=[
            SpaceNeedOut(label=n.label, needed=n.needed, free=n.free, enough=n.enough)
            for n in needs
        ],
        enough_space=all(n.enough for n in needs),
    )
    return preview, file


@router.post("/{film_id}/hdr10-copy/preview", response_model=Hdr10CopyPreviewOut)
def preview_hdr10_copy(
    film_id: int,
    body: Hdr10CopyIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
) -> Hdr10CopyPreviewOut:
    """The summary to confirm before making a copy without Dolby Vision. Changes nothing."""
    return _hdr10_preview(session, config, reader, film_id, body.file)[0]


@router.post("/{film_id}/hdr10-copy", response_model=JobOut, status_code=202)
def start_hdr10_copy(
    film_id: int,
    body: Hdr10CopyConfirmIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> JobOut:
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Please confirm the summary first.")
    preview, file = _hdr10_preview(session, config, reader, film_id, body.file)
    if preview.exists and not body.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"A copy called \u201c{preview.new_file}\u201d already exists. Tick "
            "\u201cReplace the existing copy\u201d to replace it.",
        )
    if not preview.enough_space:
        raise HTTPException(
            status_code=507,
            detail="Not enough free space for the HDR10 copy. Free up some space and try again.",
        )
    film = _get_film(session, config, film_id)
    job = queue.submit(
        hdr10_copy.KIND,
        title=hdr10_copy.TITLE,
        subject=_subject(film),
        path=file.path,
        film_id=film_id,
        params={"overwrite": body.overwrite},
    )
    return job_out(job)
