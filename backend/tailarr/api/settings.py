"""Read and change the library settings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from ..core.config import AppConfig
from ..core.settings_store import (
    LibrarySettings,
    RecycleSettings,
    get_library_settings,
    get_recycle_settings,
    save_library_settings,
    save_recycle_settings,
)
from ..jobs.models import RecycledFile
from .deps import get_config, get_session

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
