"""Read and change the library settings."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from ..core.config import AppConfig
from ..core.paths import is_inside
from ..core.settings_store import (
    LibrarySettings,
    RecycleSettings,
    get_library_settings,
    get_recycle_settings,
    save_library_settings,
    save_recycle_settings,
)
from ..jobs import restore
from ..jobs.engine import JobFailed, JobQueue
from ..jobs.models import RecycledFile
from ..library.models import Film
from .deps import get_config, get_session
from .jobs import JobOut, get_queue, job_out

router = APIRouter(prefix="/api/settings")


@router.get("/library", response_model=LibrarySettings)
def read_library(
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> LibrarySettings:
    return get_library_settings(session, config)


@router.put("/library", response_model=LibrarySettings)
def update_library(
    settings: LibrarySettings,
    request: Request,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> LibrarySettings:
    before = get_library_settings(session, config)
    saved = save_library_settings(session, settings)
    if saved.movies_dir != before.movies_dir:
        # A different Films folder: look for the films in it straight away.
        request.app.state.film_scanner.start()
    if saved.tv_dir != before.tv_dir:
        request.app.state.tv_scanner.start()
    if saved.path_mappings != before.path_mappings:
        # Radarr/Sonarr paths may now match different folders.
        request.app.state.connections.start_sync()
    return saved


class RecycleOut(RecycleSettings):
    file_count: int  # originals waiting in recycle folders
    total_size: int  # bytes they take up


def _recycle_out(session: Session, settings: RecycleSettings) -> RecycleOut:
    files = session.exec(select(RecycledFile)).all()
    return RecycleOut(
        keep_days=settings.keep_days,
        file_count=len(files),
        total_size=sum(f.size for f in files),
    )


@router.get("/recycle", response_model=RecycleOut)
def read_recycle(session: Annotated[Session, Depends(get_session)]) -> RecycleOut:
    return _recycle_out(session, get_recycle_settings(session))


@router.put("/recycle", response_model=RecycleOut)
def update_recycle(
    settings: RecycleSettings, session: Annotated[Session, Depends(get_session)]
) -> RecycleOut:
    return _recycle_out(session, save_recycle_settings(session, settings))


# -- what's in the recycle folders, and putting files back ----------------------------------


class RecycledFileOut(BaseModel):
    id: int
    name: str  # the file's own name (where it goes back to)
    folder: str  # the film or season folder it came from
    original_path: str
    size: int
    recycled_at: datetime
    days_left: int  # until it's deleted for good
    available: bool  # still in the recycle folder
    clash: bool  # a file with its name is there now (usually the copy that replaced it)
    clash_size: int | None


class RestoreIn(BaseModel):
    confirmed: bool = False
    swap: bool = False  # move the file that's there now to the recycle folder first


def _library_roots(request: Request, session: Session) -> list[str]:
    library = get_library_settings(session, request.app.state.config)
    return [library.movies_dir, library.tv_dir]


def _recycled_out(record: RecycledFile, keep_days: int, now: float) -> RecycledFileOut:
    left = keep_days - (now - record.recycled_at) / 86400
    try:
        clash_size: int | None = os.stat(record.original_path).st_size
    except OSError:
        clash_size = None
    original = Path(record.original_path)
    return RecycledFileOut(
        id=record.id,  # type: ignore[arg-type]
        name=original.name,
        folder=original.parent.name,
        original_path=record.original_path,
        size=record.size,
        recycled_at=datetime.fromtimestamp(record.recycled_at, UTC),
        days_left=max(0, int(left + 0.999)),
        available=os.path.isfile(record.path),
        clash=clash_size is not None or os.path.lexists(record.original_path),
        clash_size=clash_size,
    )


@router.get("/recycle/files", response_model=list[RecycledFileOut])
def recycled_files(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> list[RecycledFileOut]:
    """Files waiting in the recycle folders inside the library, newest first."""
    keep_days = get_recycle_settings(session).keep_days
    roots = _library_roots(request, session)
    now = time.time()
    records = session.exec(
        select(RecycledFile).order_by(col(RecycledFile.recycled_at).desc())
    ).all()
    return [
        _recycled_out(r, keep_days, now)
        for r in records
        if any(is_inside(r.path, root) for root in roots)
    ]


@router.post("/recycle/files/{record_id}/restore", response_model=JobOut, status_code=202)
def restore_file(
    record_id: int,
    body: RestoreIn,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> JobOut:
    """Put a file back where it was (a job, so it shows in the Queue)."""
    if not body.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Putting a file back changes your library, so it needs your confirmation.",
        )
    try:
        record = restore.check_restorable(
            session.get(RecycledFile, record_id), _library_roots(request, session)
        )
    except JobFailed as error:
        raise HTTPException(status_code=409, detail=error.message) from error
    name = Path(record.original_path).name
    if os.path.lexists(record.original_path) and not body.swap:
        raise HTTPException(status_code=409, detail=restore.clash_message(name))
    folder = str(Path(record.original_path).parent)
    film = session.exec(select(Film).where(Film.folder == folder)).first()
    job = queue.submit(
        restore.KIND,
        title=restore.TITLE,
        subject=film.title if film is not None else Path(name).stem,
        path=record.original_path,
        params={"recycled_id": record_id, "swap": body.swap},
        film_id=film.id if film is not None else None,
    )
    return job_out(job)
