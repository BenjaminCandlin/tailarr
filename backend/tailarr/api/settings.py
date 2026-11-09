"""Read and change the library settings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..core.config import AppConfig
from ..core.settings_store import LibrarySettings, get_library_settings, save_library_settings
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
    session: Annotated[Session, Depends(get_session)],
) -> LibrarySettings:
    return save_library_settings(session, settings)
