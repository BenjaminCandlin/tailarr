"""Settings and status for rules running by themselves."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..rules.automation import AutoRunner
from ..rules.settings import AutomationSettings, get_automation, save_automation
from .common import time_of
from .deps import get_session

router = APIRouter()


def get_runner(request: Request) -> AutoRunner:
    return request.app.state.auto_runner


class AutomationIn(BaseModel):
    settle_seconds: int = Field(default=120, ge=0, le=3600)
    watch_folders: bool = False
    rescan_minutes: int = Field(default=15, ge=5, le=1440)


class PendingOut(BaseModel):
    file: str
    reason: str
    since: datetime


class AutomationOut(BaseModel):
    settle_seconds: int
    watch_folders: bool
    watch_since: datetime | None
    rescan_minutes: int
    waiting: list[PendingOut]  # new files waiting until they've finished copying


def _out(settings: AutomationSettings, runner: AutoRunner) -> AutomationOut:
    return AutomationOut(
        settle_seconds=settings.settle_seconds,
        watch_folders=settings.watch_folders,
        watch_since=time_of(settings.watch_since),
        rescan_minutes=settings.rescan_minutes,
        waiting=[
            PendingOut(file=p.path.rsplit("/", 1)[-1], reason=p.reason, since=time_of(p.first_seen))  # type: ignore[arg-type]
            for p in runner.pending()
        ],
    )


@router.get("/api/settings/automation", response_model=AutomationOut)
def read_automation(
    session: Annotated[Session, Depends(get_session)],
    runner: Annotated[AutoRunner, Depends(get_runner)],
) -> AutomationOut:
    return _out(get_automation(session), runner)


@router.put("/api/settings/automation", response_model=AutomationOut)
def update_automation(
    body: AutomationIn,
    session: Annotated[Session, Depends(get_session)],
    runner: Annotated[AutoRunner, Depends(get_runner)],
) -> AutomationOut:
    saved = get_automation(session)
    settings = AutomationSettings(
        settle_seconds=body.settle_seconds,
        watch_folders=body.watch_folders,
        rescan_minutes=body.rescan_minutes,
        # Switching watching on: only files that appear from now on count as new.
        watch_since=(saved.watch_since or time.time()) if body.watch_folders else None,
    )
    save_automation(session, settings)
    runner.apply_watch_settings()
    return _out(settings, runner)
