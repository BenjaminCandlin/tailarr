"""Everything that can be done to one film or episode's files.

The same endpoints exist for films (``/api/films/{id}/…``) and episodes
(``/api/episodes/{id}/…``):

* ``media``: the tracks, chapters, attachments and HDR details of a file;
* ``track-settings``: change default/forced flags and names in place;
* ``remove-tracks``: save a copy without some tracks;
* ``replace-original``: replace the original with a copy Tailarr made;
* ``hdr10-copy``: make a copy without Dolby Vision.

Each has a ``/preview`` that changes nothing (for the summary shown first), and
the action itself only queues a job after the owner confirmed.
"""

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..core.config import AppConfig
from ..core.disk import SAFETY_MARGIN, free_space
from ..core.paths import is_inside
from ..core.settings_store import get_recycle_settings
from ..jobs import hdr10_copy, remove_tracks, replace_original
from ..jobs import track_settings as track_settings_job
from ..jobs.engine import JobFailed, JobQueue
from ..jobs.models import CopyRecord
from ..jobs.recycle import RECYCLE_FOLDER
from ..jobs.track_settings import HARDLINK_REFUSAL, TrackChange, TracksChangedError
from ..library.media_reader import MediaReader, details_of
from ..library.naming import is_tailarr_copy
from ..media.probe import MediaDetails
from .common import Item, ItemLoader, LibraryFile, MediaOut, get_reader, media_out
from .deps import get_config, get_session
from .jobs import JobOut, get_queue, job_out


def _cant_open(item: Item) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"This file can't be opened any more. {item.scan_hint} to bring the list "
        "up to date.",
    )


def _file(item: Item, name: str) -> LibraryFile:
    match = next((f for f in item.files if f.name == name), None)
    if match is None or not is_inside(match.path, item.root):
        raise HTTPException(status_code=404, detail="This file isn't in this folder.")
    return match


def _mkv_file(item: Item, name: str) -> LibraryFile:
    match = _file(item, name)
    if not match.is_mkv:
        raise HTTPException(status_code=400, detail="Tailarr can only change MKV files.")
    return match


def _details(
    session: Session, reader: MediaReader, item: Item, file: LibraryFile
) -> tuple[MediaDetails, os.stat_result]:
    try:
        record = reader.get(session, file.path)
        stat = os.stat(file.path)
    except OSError as error:
        raise _cant_open(item) from error
    details = details_of(record)
    if details is None:
        raise HTTPException(
            status_code=400, detail="Tailarr couldn't read this file, so it can't change it."
        )
    return details, stat


# -- requests and answers ----------------------------------------------------------------


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

    file: str
    path: str
    tracks: list[PlannedTrackOut]
    hardlinked: bool  # the file is also in another folder (usually still seeding)
    free_space: int  # bytes free on the disk holding the file


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


class ReplaceOriginalIn(BaseModel):
    copy_file: str  # the copy's file name, in the same folder


class ReplaceOriginalConfirmIn(ReplaceOriginalIn):
    confirmed: bool = False
    understood: bool = False  # ticked "I understand the original will be moved..."


class ReplaceOriginalPreviewOut(BaseModel):
    original: str
    original_size: int
    copy_file: str
    copy_size: int
    hardlinked: bool  # the original is also in the downloads folder (still seeding)
    keep_days: int
    recycle_folder: str
    # An HDR10 copy: replacing the original removes Dolby Vision from the film for good.
    loses_dolby_vision: bool


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


def make_router(prefix: str, load_item: ItemLoader) -> APIRouter:
    """The action endpoints for one kind of item (films or episodes)."""
    router = APIRouter(prefix=prefix)

    def item_of(
        item_id: int,
        config: Annotated[AppConfig, Depends(get_config)],
        session: Annotated[Session, Depends(get_session)],
    ) -> Item:
        return load_item(session, config, item_id)

    ItemDep = Annotated[Item, Depends(item_of)]
    SessionDep = Annotated[Session, Depends(get_session)]
    ReaderDep = Annotated[MediaReader, Depends(get_reader)]
    QueueDep = Annotated[JobQueue, Depends(get_queue)]
    ConfigDep = Annotated[AppConfig, Depends(get_config)]

    # -- what's inside ----------------------------------------------------------------

    @router.get("/{item_id}/media", response_model=MediaOut)
    def item_media(
        item: ItemDep,
        session: SessionDep,
        reader: ReaderDep,
        file: str | None = None,
        refresh: bool = False,
    ) -> MediaOut:
        """The tracks, chapters, attachments and HDR details of one of the item's files.

        Reads the file now if Tailarr doesn't know it yet (this can take a few seconds
        if the disk has to spin up). `refresh=true` reads it again regardless.
        """
        match = _file(item, file or item.main_file or "")
        try:
            record = reader.get(session, match.path, refresh=refresh)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"This file isn't there any more. {item.scan_hint} to bring the list "
                "up to date.",
            ) from error
        except OSError as error:
            raise HTTPException(
                status_code=503,
                detail=f"Tailarr couldn't open this file ({error.strerror or error}). "
                "Check that the disk holding it is available.",
            ) from error
        return media_out(match, record, details_of(record))

    # -- change track settings in place ---------------------------------------------------

    def settings_preview(
        session: Session, reader: MediaReader, item: Item, body: TrackSettingsIn
    ) -> TrackSettingsPreviewOut:
        file = _mkv_file(item, body.file)
        if not body.changes:
            raise HTTPException(status_code=400, detail="No track settings were changed.")
        details, stat = _details(session, reader, item, file)
        try:
            planned = track_settings_job.plan(details, body.changes)
        except TracksChangedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not planned:
            raise HTTPException(
                status_code=400, detail="Nothing to change: the tracks already have these settings."
            )
        return TrackSettingsPreviewOut(
            file=file.name,
            path=file.path,
            tracks=[PlannedTrackOut(uid=p.uid, label=p.label, changes=p.changes) for p in planned],
            hardlinked=stat.st_nlink > 1,
            free_space=free_space(Path(file.path).parent),
        )

    @router.post("/{item_id}/track-settings/preview", response_model=TrackSettingsPreviewOut)
    def preview_track_settings(
        item: ItemDep, body: TrackSettingsIn, session: SessionDep, reader: ReaderDep
    ) -> TrackSettingsPreviewOut:
        """The summary to confirm before changing a file's track settings. Changes nothing."""
        return settings_preview(session, reader, item, body)

    @router.post("/{item_id}/track-settings", response_model=JobOut, status_code=202)
    def change_track_settings(
        item: ItemDep,
        body: TrackSettingsConfirmIn,
        session: SessionDep,
        reader: ReaderDep,
        queue: QueueDep,
    ) -> JobOut:
        """Queue a job that changes the original file's track settings (after confirmation)."""
        if not body.confirmed:
            raise HTTPException(
                status_code=400,
                detail="This changes the original file, so it needs your confirmation first.",
            )
        preview = settings_preview(session, reader, item, body)
        if preview.hardlinked and not body.allow_hardlinked:
            raise HTTPException(status_code=409, detail=HARDLINK_REFUSAL)
        job = queue.submit(
            track_settings_job.KIND,
            title=track_settings_job.TITLE,
            subject=item.subject,
            path=preview.path,
            params={
                "changes": [c.model_dump(exclude_none=True) for c in body.changes],
                "allow_hardlinked": body.allow_hardlinked,
            },
            **item.job_link,
        )
        return job_out(job)

    # -- save a copy without some tracks ------------------------------------------------

    def copy_preview(
        session: Session, reader: MediaReader, item: Item, body: RemoveTracksIn
    ) -> tuple[RemoveTracksPreviewOut, LibraryFile]:
        file = _mkv_file(item, body.file)
        details, stat = _details(session, reader, item, file)
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
            space_needed=stat.st_size + SAFETY_MARGIN,
            free_space=free,
            enough_space=free >= stat.st_size + SAFETY_MARGIN,
        )
        return preview, file

    @router.post("/{item_id}/remove-tracks/preview", response_model=RemoveTracksPreviewOut)
    def preview_remove_tracks(
        item: ItemDep, body: RemoveTracksIn, session: SessionDep, reader: ReaderDep
    ) -> RemoveTracksPreviewOut:
        """The summary to confirm before making a copy without some tracks. Changes nothing."""
        return copy_preview(session, reader, item, body)[0]

    @router.post("/{item_id}/remove-tracks", response_model=JobOut, status_code=202)
    def start_remove_tracks(
        item: ItemDep,
        body: RemoveTracksConfirmIn,
        session: SessionDep,
        reader: ReaderDep,
        queue: QueueDep,
    ) -> JobOut:
        if not body.confirmed:
            raise HTTPException(status_code=400, detail="Please confirm the summary first.")
        preview, file = copy_preview(session, reader, item, body)
        if preview.exists and not body.overwrite:
            raise HTTPException(
                status_code=409,
                detail=f"A copy called “{preview.new_file}” already exists. Tick "
                "“Replace the existing copy” to replace it.",
            )
        if not preview.enough_space:
            raise HTTPException(
                status_code=507,
                detail="Not enough free space on the disk for the copy. Free up some space "
                "and try again.",
            )
        job = queue.submit(
            remove_tracks.KIND,
            title=remove_tracks.TITLE,
            subject=item.subject,
            path=file.path,
            params={
                "remove": body.remove,
                "changes": [c.model_dump(exclude_none=True) for c in body.changes],
                "overwrite": body.overwrite,
            },
            **item.job_link,
        )
        return job_out(job)

    # -- replace the original with a copy -------------------------------------------------

    def replace_preview(
        session: Session, item: Item, body: ReplaceOriginalIn
    ) -> tuple[ReplaceOriginalPreviewOut, LibraryFile, LibraryFile]:
        copy = _mkv_file(item, body.copy_file)
        engine = session.get_bind()
        record = session.get(CopyRecord, copy.path)
        if record is None:
            raise HTTPException(status_code=400, detail=replace_original.NO_RECORD)
        original = _mkv_file(item, Path(record.source_path).name)
        if original.path != record.source_path:
            raise HTTPException(status_code=400, detail=replace_original.NO_RECORD)
        try:
            replace_original.check_copy_record(engine, original.path, copy.path)  # type: ignore[arg-type]
            original_stat, copy_stat = os.stat(original.path), os.stat(copy.path)
        except JobFailed as error:
            raise HTTPException(status_code=409, detail=error.message) from error
        except OSError as error:
            raise _cant_open(item) from error
        preview = ReplaceOriginalPreviewOut(
            original=original.name,
            original_size=original_stat.st_size,
            copy_file=copy.name,
            copy_size=copy_stat.st_size,
            hardlinked=original_stat.st_nlink > 1,
            keep_days=get_recycle_settings(session).keep_days,
            recycle_folder=str(Path(original.path).parent / RECYCLE_FOLDER),
            loses_dolby_vision=record.kind == replace_original.LOSES_DOLBY_VISION_KIND,
        )
        return preview, original, copy

    @router.post("/{item_id}/replace-original/preview", response_model=ReplaceOriginalPreviewOut)
    def preview_replace_original(
        item: ItemDep, body: ReplaceOriginalIn, session: SessionDep
    ) -> ReplaceOriginalPreviewOut:
        """The summary to confirm before replacing an original with a copy. Changes nothing."""
        return replace_preview(session, item, body)[0]

    @router.post("/{item_id}/replace-original", response_model=JobOut, status_code=202)
    def start_replace_original(
        item: ItemDep, body: ReplaceOriginalConfirmIn, session: SessionDep, queue: QueueDep
    ) -> JobOut:
        if not (body.confirmed and body.understood):
            raise HTTPException(
                status_code=400,
                detail="This replaces your original file, so it needs your confirmation first.",
            )
        _, original, copy = replace_preview(session, item, body)
        job = queue.submit(
            replace_original.KIND,
            title=replace_original.TITLE,
            subject=item.subject,
            path=original.path,
            params={"copy": copy.path},
            **item.job_link,
        )
        return job_out(job)

    # -- make a copy without Dolby Vision -----------------------------------------------

    def hdr10_preview(
        session: Session, config: AppConfig, reader: MediaReader, item: Item, file_name: str
    ) -> tuple[Hdr10CopyPreviewOut, LibraryFile]:
        file = _mkv_file(item, file_name)
        details, stat = _details(session, reader, item, file)
        if not details.hdr_checked:
            raise HTTPException(
                status_code=400,
                detail="MediaInfo couldn't read this file, so Tailarr can't tell how its Dolby "
                "Vision is stored. Try “Try again” on the page.",
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
                detail=f"A file called “{new_name}” is already there and it isn't a copy "
                "made by Tailarr, so Tailarr won't replace it.",
            )
        work = hdr10_copy.usable_work_folder(config.work_dir)
        needs = hdr10_copy.space_needs(stat.st_size, new_path.parent, work)
        preview = Hdr10CopyPreviewOut(
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

    @router.post("/{item_id}/hdr10-copy/preview", response_model=Hdr10CopyPreviewOut)
    def preview_hdr10_copy(
        item: ItemDep, body: Hdr10CopyIn, config: ConfigDep, session: SessionDep, reader: ReaderDep
    ) -> Hdr10CopyPreviewOut:
        """The summary to confirm before making a copy without Dolby Vision. Changes nothing."""
        return hdr10_preview(session, config, reader, item, body.file)[0]

    @router.post("/{item_id}/hdr10-copy", response_model=JobOut, status_code=202)
    def start_hdr10_copy(
        item: ItemDep,
        body: Hdr10CopyConfirmIn,
        config: ConfigDep,
        session: SessionDep,
        reader: ReaderDep,
        queue: QueueDep,
    ) -> JobOut:
        if not body.confirmed:
            raise HTTPException(status_code=400, detail="Please confirm the summary first.")
        preview, file = hdr10_preview(session, config, reader, item, body.file)
        if preview.exists and not body.overwrite:
            raise HTTPException(
                status_code=409,
                detail=f"A copy called “{preview.new_file}” already exists. Tick "
                "“Replace the existing copy” to replace it.",
            )
        if not preview.enough_space:
            raise HTTPException(
                status_code=507,
                detail="Not enough free space for the HDR10 copy. Free up some space and try "
                "again.",
            )
        job = queue.submit(
            hdr10_copy.KIND,
            title=hdr10_copy.TITLE,
            subject=item.subject,
            path=file.path,
            params={"overwrite": body.overwrite},
            **item.job_link,
        )
        return job_out(job)

    return router
