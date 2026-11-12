"""Tables for what Tailarr learns from Radarr/Sonarr, and the activity log."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class ExternalInfo(SQLModel, table=True):
    """What Radarr (a film) or Sonarr (a show) knows about one folder.

    Keyed by the folder as Tailarr sees it (after path mapping), so it survives library
    re-scans. Refreshed by the sync after connecting, and every few hours.
    """

    folder: str = Field(primary_key=True)
    source: str  # "radarr" or "sonarr"
    arr_id: int  # Radarr's movie id or Sonarr's series id
    title: str
    year: int | None = None
    poster_file: str | None = None  # cached copy in /config/cache/arr
    backdrop_file: str | None = None
    synced_at: float = 0


class ActivityEntry(SQLModel, table=True):
    """Something Tailarr did by itself, or was told: shown in the activity log."""

    id: int | None = Field(default=None, primary_key=True)
    at: float = Field(index=True)
    source: str  # "radarr", "sonarr", "plex", "tailarr" or "rule"
    kind: str  # e.g. "webhook", "refresh", "rescan", "copy-tidied", "copy-renamed"
    message: str  # plain English
    ok: bool = True
    details: str | None = None  # technical details
    path: str | None = None
    job_id: int | None = None
    rule_id: int | None = None
