"""The TV library: shows, seasons and episodes, artwork, re-scanning, and batch actions.

The actions on one episode's files are in actions.py (shared with films), under
``/api/episodes/{id}/…``.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, col, select

from ..actions.plans import (
    Action,
    FilePlan,
    changes_originals,
    describe_action,
    plan_file,
    space_totals,
)
from ..core.config import AppConfig
from ..core.paths import is_inside
from ..core.settings_store import get_library_settings
from ..jobs.engine import JobQueue
from ..jobs.hdr10_copy import usable_work_folder
from ..jobs.models import JobGroup
from ..library.artwork import thumbnail
from ..library.media_reader import MediaReader, details_of
from ..library.models import Episode, EpisodeFile, Show
from ..library.tv_naming import episode_label, season_label
from ..library.tv_scanner import TvScanner
from ..media.languages import language_choices
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
from .jobs import get_queue

router = APIRouter(prefix="/api/tv")
episodes_router = APIRouter(prefix="/api/episodes")
languages_router = APIRouter(prefix="/api/languages")

_LONG_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


def get_tv_scanner(request: Request) -> TvScanner:
    return request.app.state.tv_scanner


def _tv_root(session: Session, config: AppConfig) -> str:
    return get_library_settings(session, config).tv_dir


# -- answers ------------------------------------------------------------------------------


class ShowOut(BaseModel):
    id: int
    title: str
    year: int | None
    folder_name: str
    poster_url: str | None
    size: int
    added_at: datetime
    season_count: int
    episode_count: int
    # Across the episodes' own files: HDR formats found, best picture size, and counts.
    media: MediaSummaryOut
    dv_episodes: int


class TvListOut(BaseModel):
    root: str
    shows: list[ShowOut]
    scan: ScanStatusOut
    reading: ReadingStatusOut


class EpisodeOut(BaseModel):
    id: int
    season: int | None
    episode: int | None
    episode_end: int | None
    label: str  # "S01E02"
    title: str
    main_file: str | None
    is_mkv: bool
    size: int
    added_at: datetime
    file_count: int
    has_copy: bool
    media: MediaSummaryOut


class SeasonOut(BaseModel):
    season: int | None
    label: str  # "Season 1", "Specials"
    size: int
    episodes: list[EpisodeOut]


class ShowDetailOut(ShowOut):
    folder: str
    backdrop_url: str | None
    tvdb_id: int | None
    seasons: list[SeasonOut]


class EpisodeDetailOut(EpisodeOut):
    show_id: int
    show_title: str
    show_year: int | None
    poster_url: str | None
    backdrop_url: str | None
    folder: str
    files: list[FileOut]


def _poster_url(show: Show) -> str | None:
    if not show.poster_path:
        return None
    return f"/api/tv/shows/{show.id}/poster?v={int(show.poster_mtime or 0)}"


def _backdrop_url(show: Show) -> str | None:
    if not show.backdrop_path:
        return None
    return f"/api/tv/shows/{show.id}/backdrop?v={int(show.backdrop_mtime or 0)}"


_RESOLUTION_ORDER = ["4K", "1440p", "1080p", "720p", "576p", "480p", "SD"]


def _combine(summaries: list[MediaSummaryOut]) -> MediaSummaryOut:
    read = [s for s in summaries if s.read]
    formats: list[str] = []
    for summary in read:
        for f in summary.hdr:
            if f not in formats:
                formats.append(f)
    order = ["Dolby Vision", "HDR10+", "HDR10", "HLG"]
    formats.sort(key=lambda f: order.index(f) if f in order else len(order))
    resolutions = [s.resolution for s in read if s.resolution]
    best = min(
        resolutions,
        key=lambda r: _RESOLUTION_ORDER.index(r) if r in _RESOLUTION_ORDER else 99,
        default=None,
    )
    return MediaSummaryOut(
        read=bool(read) and len(read) == len(summaries),
        error=any(s.error for s in read),
        hdr=formats,
        resolution=best,
    )


def _episode_out(
    episode: Episode, main: EpisodeFile | None, media: MediaSummaryOut, has_copy: bool
) -> dict:
    return {
        "id": episode.id,
        "season": episode.season,
        "episode": episode.episode,
        "episode_end": episode.episode_end,
        "label": episode_label(episode.season, episode.episode, episode.episode_end),
        "title": episode.title,
        "main_file": episode.main_file,
        "is_mkv": bool(main and main.is_mkv),
        "size": episode.size,
        "added_at": time_of(episode.added_at),
        "file_count": episode.file_count,
        "has_copy": has_copy,
        "media": media,
    }


def _show_out(show: Show, media: MediaSummaryOut, dv_episodes: int) -> dict:
    return {
        "id": show.id,
        "title": show.title,
        "year": show.year,
        "folder_name": show.folder_name,
        "poster_url": _poster_url(show),
        "size": show.size,
        "added_at": time_of(show.added_at),
        "season_count": show.season_count,
        "episode_count": show.episode_count,
        "media": media,
        "dv_episodes": dv_episodes,
    }


def _episode_sort(episode: Episode) -> tuple:
    return (
        episode.season if episode.season is not None else 10_000,
        episode.episode if episode.episode is not None else 10_000,
        episode.title.casefold(),
    )


def _main_files(session: Session, show_ids: list[int] | None = None) -> dict[int, EpisodeFile]:
    query = select(EpisodeFile)
    if show_ids is not None:
        query = query.where(col(EpisodeFile.show_id).in_(show_ids))
    files = session.exec(query).all()
    episodes = {e.id: e for e in session.exec(select(Episode)).all()} if files else {}
    mains: dict[int, EpisodeFile] = {}
    for f in files:
        episode = episodes.get(f.episode_id)
        if episode is not None and f.name == episode.main_file:
            mains[f.episode_id] = f
    return mains


def _copies_of(session: Session, show_id: int) -> set[int]:
    rows = session.exec(
        select(EpisodeFile.episode_id).where(
            EpisodeFile.show_id == show_id, col(EpisodeFile.is_copy).is_(True)
        )
    ).all()
    return set(rows)


# -- list and scan ------------------------------------------------------------------------


@router.get("", response_model=TvListOut)
def list_shows(
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    scanner: Annotated[TvScanner, Depends(get_tv_scanner)],
    reader: Annotated[MediaReader, Depends(get_reader)],
) -> TvListOut:
    scanner.start_if_stale()
    root = _tv_root(session, config)
    mains = _main_files(session)
    records = records_for(session, [f.path for f in mains.values()])
    per_show: dict[int, list[MediaSummaryOut]] = {}
    for main in mains.values():
        per_show.setdefault(main.show_id, []).append(
            summary_of(records.get(main.path), main.size, main.mtime)
        )
    shows = []
    for show in session.exec(select(Show).order_by(Show.sort_title, Show.year)).all():
        if not is_inside(show.folder, root):
            continue
        summaries = per_show.get(show.id or 0, [])
        dv = sum(1 for s in summaries if "Dolby Vision" in s.hdr)
        shows.append(ShowOut(**_show_out(show, _combine(summaries), dv)))
    return TvListOut(root=root, shows=shows, scan=scan_out(scanner), reading=reading_out(reader))


@router.get("/scan", response_model=ScanStatusOut)
def tv_scan_status(scanner: Annotated[TvScanner, Depends(get_tv_scanner)]) -> ScanStatusOut:
    return scan_out(scanner)


@router.post("/scan", response_model=ScanStatusOut, status_code=202)
def start_tv_scan(scanner: Annotated[TvScanner, Depends(get_tv_scanner)]) -> ScanStatusOut:
    scanner.start()
    return scan_out(scanner)


# -- one show -----------------------------------------------------------------------------


def _get_show(session: Session, config: AppConfig, show_id: int) -> Show:
    show = session.get(Show, show_id)
    if show is None or not is_inside(show.folder, _tv_root(session, config)):
        raise HTTPException(
            status_code=404,
            detail="This show isn't in your library any more. It may have been moved or deleted.",
        )
    return show


def _episodes(session: Session, show: Show, season: int | None = None) -> list[Episode]:
    query = select(Episode).where(Episode.show_id == show.id)
    episodes = list(session.exec(query).all())
    if season is not None:
        episodes = [e for e in episodes if e.season == season]
    return sorted(episodes, key=_episode_sort)


@router.get("/shows/{show_id}", response_model=ShowDetailOut)
def show_detail(
    show_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> ShowDetailOut:
    show = _get_show(session, config, show_id)
    episodes = _episodes(session, show)
    mains = _main_files(session, [show_id])
    records = records_for(session, [f.path for f in mains.values()])
    with_copies = _copies_of(session, show_id)
    seasons: dict[int | None, SeasonOut] = {}
    all_media: list[MediaSummaryOut] = []
    for episode in episodes:
        main = mains.get(episode.id or 0)
        media = summary_of(records.get(main.path), main.size, main.mtime) if main else NOT_READ
        all_media.append(media)
        season = seasons.get(episode.season)
        if season is None:
            season = seasons[episode.season] = SeasonOut(
                season=episode.season, label=season_label(episode.season), size=0, episodes=[]
            )
        season.size += episode.size
        season.episodes.append(
            EpisodeOut(**_episode_out(episode, main, media, episode.id in with_copies))
        )
    dv = sum(1 for m in all_media if "Dolby Vision" in m.hdr)
    return ShowDetailOut(
        **_show_out(show, _combine(all_media), dv),
        folder=show.folder,
        backdrop_url=_backdrop_url(show),
        tvdb_id=show.tvdb_id,
        seasons=list(seasons.values()),
    )


def _artwork(session: Session, config: AppConfig, show_id: int, kind: str) -> Path:
    show = _get_show(session, config, show_id)
    stored = show.poster_path if kind == "poster" else show.backdrop_path
    # Check again at the moment of reading: only pictures inside the TV folder are served.
    if not stored or not is_inside(stored, _tv_root(session, config)) or not Path(stored).is_file():
        raise HTTPException(status_code=404, detail="No picture for this show.")
    return Path(stored)


@router.get("/shows/{show_id}/poster", response_model=None)
def show_poster(
    show_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    size: Literal["small", "full"] = "small",
) -> Response:
    source = _artwork(session, config, show_id, "poster")
    if size == "small":
        small = thumbnail(source, config.config_dir / "cache" / "posters")
        if small is None:
            raise HTTPException(status_code=404, detail="This poster picture can't be read.")
        return FileResponse(small, media_type="image/jpeg", headers=_LONG_CACHE)
    return FileResponse(source, headers=_LONG_CACHE)


@router.get("/shows/{show_id}/backdrop", response_model=None)
def show_backdrop(
    show_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    return FileResponse(_artwork(session, config, show_id, "backdrop"), headers=_LONG_CACHE)


# -- one episode --------------------------------------------------------------------------


def _get_episode(session: Session, config: AppConfig, episode_id: int) -> tuple[Episode, Show]:
    episode = session.get(Episode, episode_id)
    show = session.get(Show, episode.show_id) if episode else None
    if episode is None or show is None or not is_inside(episode.folder, _tv_root(session, config)):
        raise not_found("episode")
    return episode, show


def _episode_files(session: Session, episode: Episode) -> list[EpisodeFile]:
    files = session.exec(select(EpisodeFile).where(EpisodeFile.episode_id == episode.id)).all()
    return sorted(files, key=lambda f: (f.name != episode.main_file, f.is_copy, f.name))


def episode_subject(episode: Episode, show: Show) -> str:
    """'Test Show – S01E02 – The Second One'."""
    parts = [show.title, episode_label(episode.season, episode.episode, episode.episode_end)]
    if episode.title:
        parts.append(episode.title)
    return " – ".join(p for p in parts if p)


def load_episode(session: Session, config: AppConfig, episode_id: int) -> Item:
    """An episode as an "item", for the actions shared with films."""
    episode, show = _get_episode(session, config, episode_id)
    return Item(
        kind="episode",
        id=episode_id,
        subject=episode_subject(episode, show),
        folder=episode.folder,
        root=_tv_root(session, config),
        main_file=episode.main_file,
        files=list(_episode_files(session, episode)),
    )


@episodes_router.get("/{episode_id}", response_model=EpisodeDetailOut)
def episode_detail(
    episode_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> EpisodeDetailOut:
    episode, show = _get_episode(session, config, episode_id)
    files = _episode_files(session, episode)
    out_files = files_out(session, list(files), episode.main_file)
    main_out = next((f for f in out_files if f.is_main), None)
    main = next((f for f in files if f.name == episode.main_file), None)
    return EpisodeDetailOut(
        **_episode_out(
            episode,
            main,
            main_out.media if main_out else NOT_READ,
            any(f.is_copy for f in files),
        ),
        show_id=show.id,  # type: ignore[arg-type]
        show_title=show.title,
        show_year=show.year,
        poster_url=_poster_url(show),
        backdrop_url=_backdrop_url(show),
        folder=episode.folder,
        files=out_files,
    )


# -- batch actions on a season or a whole show ----------------------------------------------


class BatchIn(BaseModel):
    season: int | None = None  # None: the whole show
    action: Action
    # Tick "I understand" for files that are also in the downloads folder (still seeding).
    allow_hardlinked: bool = False


class BatchConfirmIn(BatchIn):
    confirmed: bool = False


class BatchFileOut(BaseModel):
    episode_id: int
    label: str  # "S01E02 – The Second One"
    file: str
    will_run: bool
    lines: list[str]
    reason: str | None
    hardlinked: bool
    new_file: str | None


class SpaceTotalOut(BaseModel):
    label: str
    needed: int
    free: int
    enough: bool


class BatchPreviewOut(BaseModel):
    title: str  # "Make a copy without Dolby Vision: Test Show, Season 1"
    action: str
    scope: str  # "Test Show, Season 1"
    changes_originals: bool
    files: list[BatchFileOut]
    will_run: int
    skipped: int
    hardlinked_skipped: int  # seeding files left out because "I understand" isn't ticked
    space: list[SpaceTotalOut]
    enough_space: bool


class BatchStartedOut(BaseModel):
    group_id: str
    title: str
    jobs: int


def _scope(show: Show, season: int | None) -> str:
    return show.title if season is None else f"{show.title}, {season_label(season)}"


def _batch_plans(
    session: Session,
    config: AppConfig,
    reader: MediaReader,
    show: Show,
    body: BatchIn,
) -> tuple[list[tuple[Episode, FilePlan]], list[SpaceTotalOut]]:
    episodes = _episodes(session, show, body.season)
    if body.season is not None and not episodes:
        raise HTTPException(status_code=404, detail="This show has no episodes in that season.")
    root = _tv_root(session, config)
    plans: list[tuple[Episode, FilePlan]] = []
    for episode in episodes:
        files = _episode_files(session, episode)
        main = next((f for f in files if f.name == episode.main_file), None)
        if main is None or not is_inside(main.path, root):
            continue
        details, error = None, None
        try:
            record = reader.get(session, main.path)
            details = details_of(record)
            error = record.error
        except OSError:
            error = "This file can't be opened any more."
        plans.append(
            (
                episode,
                plan_file(
                    body.action,
                    main.path,
                    details,
                    is_copy=main.is_copy,
                    allow_hardlinked=body.allow_hardlinked,
                    read_error=error,
                ),
            )
        )
    totals = space_totals([p for _, p in plans], usable_work_folder(config.work_dir))
    space = [
        SpaceTotalOut(label=t.label, needed=t.needed, free=t.free, enough=t.enough) for t in totals
    ]
    return plans, space


def _batch_preview(
    session: Session, config: AppConfig, reader: MediaReader, show_id: int, body: BatchIn
) -> tuple[BatchPreviewOut, list[tuple[Episode, FilePlan]], Show]:
    show = _get_show(session, config, show_id)
    plans, space = _batch_plans(session, config, reader, show, body)
    action = describe_action(body.action)
    scope = _scope(show, body.season)
    files = []
    for episode, plan in plans:
        label = episode_label(episode.season, episode.episode, episode.episode_end)
        files.append(
            BatchFileOut(
                episode_id=episode.id,  # type: ignore[arg-type]
                label=" – ".join(p for p in (label, episode.title) if p) or plan.name,
                file=plan.name,
                will_run=plan.will_run,
                lines=plan.lines,
                reason=plan.reason,
                hardlinked=plan.hardlinked,
                new_file=plan.new_file,
            )
        )
    preview = BatchPreviewOut(
        title=f"{action}: {scope}",
        action=action,
        scope=scope,
        changes_originals=changes_originals(body.action),
        files=files,
        will_run=sum(1 for _, p in plans if p.will_run),
        skipped=sum(1 for _, p in plans if not p.will_run),
        hardlinked_skipped=sum(1 for _, p in plans if not p.will_run and p.hardlinked),
        space=space,
        enough_space=all(s.enough for s in space),
    )
    return preview, plans, show


@router.post("/shows/{show_id}/batch/preview", response_model=BatchPreviewOut)
def preview_batch(
    show_id: int,
    body: BatchIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
) -> BatchPreviewOut:
    """What an action would do to every episode of a season or show. Changes nothing.

    Episodes Tailarr hasn't read yet are read now, which can take a while for a big show.
    """
    return _batch_preview(session, config, reader, show_id, body)[0]


@router.post("/shows/{show_id}/batch", response_model=BatchStartedOut, status_code=202)
def start_batch(
    show_id: int,
    body: BatchConfirmIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    reader: Annotated[MediaReader, Depends(get_reader)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> BatchStartedOut:
    """Queue one job per episode (shown as a group in the queue), after confirmation."""
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Please confirm the summary first.")
    preview, plans, show = _batch_preview(session, config, reader, show_id, body)
    if preview.will_run == 0:
        raise HTTPException(status_code=400, detail="There's nothing to do for these episodes.")
    if not preview.enough_space:
        raise HTTPException(
            status_code=507,
            detail="Not enough free space for all of these copies. Free up some space, or "
            "choose one season at a time.",
        )
    group = JobGroup(id=uuid.uuid4().hex, title=preview.title, created_at=time.time())
    session.add(group)
    session.commit()
    count = 0
    for episode, plan in plans:
        if not plan.will_run or plan.job_kind is None:
            continue
        queue.submit(
            plan.job_kind,
            title=plan.job_title or plan.job_kind,
            subject=episode_subject(episode, show),
            path=plan.path,
            params=plan.params,
            episode_id=episode.id,
            group_id=group.id,
        )
        count += 1
    return BatchStartedOut(group_id=group.id, title=group.title, jobs=count)


# -- languages for pickers ----------------------------------------------------------------


class LanguageOut(BaseModel):
    code: str
    name: str
    common: bool


@languages_router.get("", response_model=list[LanguageOut])
def languages() -> list[LanguageOut]:
    choices = language_choices()
    from ..media.languages import COMMON_LANGUAGES

    return [LanguageOut(code=c, name=n, common=c in COMMON_LANGUAGES) for c, n in choices]
