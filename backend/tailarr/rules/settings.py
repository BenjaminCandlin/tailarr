"""Settings for automatic rules: how long a file must sit still, and folder watching."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlmodel import Session

from ..core.db import Setting

AUTOMATION_KEY = "automation"


class AutomationSettings(BaseModel):
    # A new file counts as "finished copying" once its size and date haven't changed for
    # this long (and MKVToolNix can read it).
    settle_seconds: int = Field(default=60, ge=0, le=3600)
    # Look for new files in the Films/TV folders without Radarr/Sonarr webhooks.
    watch_folders: bool = False
    # Only files that appeared after watching was switched on count as new.
    watch_since: float | None = None
    # With watching on: look through the folders this often, in case a change was missed.
    rescan_minutes: int = Field(default=15, ge=5, le=1440)


def get_automation(session: Session) -> AutomationSettings:
    row = session.get(Setting, AUTOMATION_KEY)
    if row is None:
        return AutomationSettings()
    return AutomationSettings.model_validate(json.loads(row.value))


def save_automation(session: Session, settings: AutomationSettings) -> AutomationSettings:
    session.merge(Setting(key=AUTOMATION_KEY, value=settings.model_dump_json()))
    session.commit()
    return settings
