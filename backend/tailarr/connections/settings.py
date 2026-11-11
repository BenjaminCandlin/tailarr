"""Connection settings for Radarr, Sonarr and Plex, saved in the database under /config.

API keys and the Plex token only ever live in the database (safety rule 10). They are
never sent back to the web page: it only learns whether one is saved.
"""

from __future__ import annotations

import json
import secrets

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from ..core.db import Setting

CONNECTIONS_KEY = "connections"


def _clean_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value


class ServiceSettings(BaseModel):
    url: str = ""
    api_key: str = ""  # Radarr/Sonarr API key, or the Plex token

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _clean_url(value)

    @field_validator("api_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return value.strip()

    @property
    def configured(self) -> bool:
        return bool(self.url and self.api_key)


class ConnectionSettings(BaseModel):
    radarr: ServiceSettings = ServiceSettings()
    sonarr: ServiceSettings = ServiceSettings()
    plex: ServiceSettings = ServiceSettings()
    # After every job that changed files: ask Plex to look at that folder again.
    plex_refresh: bool = True
    # After Tailarr changes or replaces an original: ask Radarr/Sonarr to read it again.
    arr_rescan: bool = True
    # When Radarr/Sonarr upgrade or delete an original: move Tailarr's copies of it to the
    # recycle folder (they were made from the old file). Renamed originals: rename copies.
    tidy_copies: bool = True
    webhook_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(24))


def get_connections(session: Session) -> ConnectionSettings:
    row = session.get(Setting, CONNECTIONS_KEY)
    if row is None:
        settings = ConnectionSettings()
        save_connections(session, settings)  # keep the generated webhook secret
        return settings
    return ConnectionSettings.model_validate(json.loads(row.value))


def save_connections(session: Session, settings: ConnectionSettings) -> ConnectionSettings:
    row = session.get(Setting, CONNECTIONS_KEY) or Setting(key=CONNECTIONS_KEY, value="")
    row.value = settings.model_dump_json()
    session.add(row)
    session.commit()
    return settings
