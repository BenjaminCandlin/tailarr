"""Settings and actions for the Radarr, Sonarr and Plex connections, webhooks and activity."""

from __future__ import annotations

import base64
import hmac
import os
import secrets
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from ..connections import webhooks
from ..connections.clients import ConnectionProblem
from ..connections.models import ActivityEntry
from ..connections.service import Connections
from ..connections.settings import (
    ConnectionSettings,
    ServiceSettings,
    get_connections,
    save_connections,
)
from ..core.config import AppConfig
from ..core.paths import is_inside, map_remote_path
from ..core.settings_store import get_library_settings
from .common import time_of
from .deps import get_config, get_session

router = APIRouter()

Service = Literal["radarr", "sonarr", "plex"]


def get_connections_service(request: Request) -> Connections:
    return request.app.state.connections


class ServiceOut(BaseModel):
    url: str
    has_key: bool  # a key/token is saved (it's never sent back to the page)


class SyncOut(BaseModel):
    running: bool
    finished_at: datetime | None
    films: int | None
    shows: int | None
    errors: dict[str, str] | None


class ConnectionsOut(BaseModel):
    radarr: ServiceOut
    sonarr: ServiceOut
    plex: ServiceOut
    plex_refresh: bool
    arr_rescan: bool
    tidy_copies: bool
    # Paths to add after Tailarr's own address, for Radarr/Sonarr's Webhook connection.
    webhook_paths: dict[str, str]
    sync: SyncOut


class ServiceIn(BaseModel):
    url: str = ""
    api_key: str | None = None  # None or "": keep the saved one


class ConnectionsIn(BaseModel):
    radarr: ServiceIn = ServiceIn()
    sonarr: ServiceIn = ServiceIn()
    plex: ServiceIn = ServiceIn()
    plex_refresh: bool = True
    arr_rescan: bool = True
    tidy_copies: bool = True


def _out(settings: ConnectionSettings, service: Connections) -> ConnectionsOut:
    status = service.status()
    return ConnectionsOut(
        radarr=ServiceOut(url=settings.radarr.url, has_key=bool(settings.radarr.api_key)),
        sonarr=ServiceOut(url=settings.sonarr.url, has_key=bool(settings.sonarr.api_key)),
        plex=ServiceOut(url=settings.plex.url, has_key=bool(settings.plex.api_key)),
        plex_refresh=settings.plex_refresh,
        arr_rescan=settings.arr_rescan,
        tidy_copies=settings.tidy_copies,
        webhook_paths={
            name: f"/api/webhooks/{name}?secret={settings.webhook_secret}"
            for name in ("radarr", "sonarr")
        },
        sync=SyncOut(
            running=status.running,
            finished_at=time_of(status.finished_at),
            films=status.films,
            shows=status.shows,
            errors=status.errors,
        ),
    )


def _merge(saved: ServiceSettings, incoming: ServiceIn) -> ServiceSettings:
    key = incoming.api_key if incoming.api_key else saved.api_key
    if not incoming.url.strip():
        key = ""  # clearing the address forgets the key too
    return ServiceSettings(url=incoming.url, api_key=key)


@router.get("/api/settings/connections", response_model=ConnectionsOut)
def read_connections(
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[Connections, Depends(get_connections_service)],
) -> ConnectionsOut:
    return _out(get_connections(session), service)


@router.put("/api/settings/connections", response_model=ConnectionsOut)
def update_connections(
    body: ConnectionsIn,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[Connections, Depends(get_connections_service)],
) -> ConnectionsOut:
    saved = get_connections(session)
    settings = ConnectionSettings(
        radarr=_merge(saved.radarr, body.radarr),
        sonarr=_merge(saved.sonarr, body.sonarr),
        plex=_merge(saved.plex, body.plex),
        plex_refresh=body.plex_refresh,
        arr_rescan=body.arr_rescan,
        tidy_copies=body.tidy_copies,
        webhook_secret=saved.webhook_secret,
    )
    save_connections(session, settings)
    service.start_sync()  # titles and posters straight away
    return _out(settings, service)


class TestIn(BaseModel):
    service: Service
    url: str
    api_key: str | None = None  # empty: use the saved one


class TestOut(BaseModel):
    ok: bool
    message: str
    details: str | None = None


@router.post("/api/settings/connections/test", response_model=TestOut)
def test_connection(
    body: TestIn,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[Connections, Depends(get_connections_service)],
) -> TestOut:
    """Try the address and key without saving them."""
    saved: ServiceSettings = getattr(get_connections(session), body.service)
    settings = _merge(saved, ServiceIn(url=body.url, api_key=body.api_key))
    try:
        return TestOut(ok=True, message=service.test(body.service, settings))
    except ConnectionProblem as problem:
        return TestOut(ok=False, message=problem.message, details=problem.details or None)


@router.post("/api/settings/connections/new-secret", response_model=ConnectionsOut)
def new_webhook_secret(
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[Connections, Depends(get_connections_service)],
) -> ConnectionsOut:
    """Make a new webhook secret (the old webhook addresses stop working)."""
    settings = get_connections(session)
    settings.webhook_secret = secrets.token_urlsafe(24)
    save_connections(session, settings)
    return _out(settings, service)


@router.post("/api/connections/sync", response_model=SyncOut, status_code=202)
def start_sync(service: Annotated[Connections, Depends(get_connections_service)]) -> SyncOut:
    service.start_sync()
    status = service.status()
    return SyncOut(
        running=True,
        finished_at=time_of(status.finished_at),
        films=status.films,
        shows=status.shows,
        errors=status.errors,
    )


class MappingTestIn(BaseModel):
    path: str  # a path as Radarr/Sonarr/Plex report it


class MappingTestOut(BaseModel):
    path: str  # the same path as Tailarr sees it
    exists: bool
    inside_library: bool
    message: str


@router.post("/api/settings/path-mappings/test", response_model=MappingTestOut)
def test_mapping(
    body: MappingTestIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> MappingTestOut:
    library = get_library_settings(session, config)
    mapped = os.path.normpath(
        map_remote_path(body.path.strip(), [m.to_mapping() for m in library.path_mappings])
    )
    inside = any(is_inside(mapped, root) for root in (library.movies_dir, library.tv_dir))
    exists = os.path.exists(mapped)
    if exists and inside:
        message = "Found it. Tailarr can use this path."
    elif exists:
        message = "Tailarr can see this path, but it's outside your Films and TV folders."
    else:
        message = "Tailarr can't find this path. Add or fix a path mapping."
    return MappingTestOut(path=mapped, exists=exists, inside_library=inside, message=message)


# -- webhooks -------------------------------------------------------------------------------


def _secret_from(request: Request, header_secret: str | None, authorization: str | None) -> str:
    if header_secret:
        return header_secret
    query = request.query_params.get("secret")
    if query:
        return query
    if authorization and authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization[6:]).decode()
        except ValueError:
            return ""
        return decoded.partition(":")[2]  # the password field
    return ""


class WebhookOut(BaseModel):
    ok: bool
    message: str


@router.post("/api/webhooks/{service}", response_model=WebhookOut)
def webhook(
    service: Literal["radarr", "sonarr"],
    request: Request,
    payload: Annotated[dict, Body()],
    x_tailarr_secret: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> WebhookOut:
    """Radarr/Sonarr tell Tailarr about imports, upgrades, deletes and renames."""
    engine = request.app.state.engine
    config: AppConfig = request.app.state.config
    with Session(engine) as session:
        settings = get_connections(session)
        library = get_library_settings(session, config)
    given = _secret_from(request, x_tailarr_secret, authorization)
    if not hmac.compare_digest(given.encode(), settings.webhook_secret.encode()):
        raise HTTPException(
            status_code=401,
            detail="Wrong or missing secret. Copy the webhook address again from Tailarr's "
            "Settings page.",
        )
    result = webhooks.handle(
        engine,
        service,
        payload,
        mappings=[m.to_mapping() for m in library.path_mappings],
        roots=[library.movies_dir, library.tv_dir],
        tidy=settings.tidy_copies,
        folder_changed=request.app.state.folder_changed,
    )
    for hook in getattr(request.app.state, "on_webhook", []):
        hook(service, result)
    return WebhookOut(ok=True, message=result.message)


# -- activity -------------------------------------------------------------------------------


class ActivityOut(BaseModel):
    id: int
    at: datetime
    source: str
    kind: str
    message: str
    ok: bool
    details: str | None
    path: str | None
    job_id: int | None
    rule_id: int | None


@router.get("/api/activity", response_model=list[ActivityOut])
def activity(
    session: Annotated[Session, Depends(get_session)],
    limit: int = 100,
    source: str | None = None,
    rule_id: int | None = None,
) -> list[ActivityOut]:
    """The newest things Tailarr did by itself or was told, newest first."""
    query = select(ActivityEntry)
    if source:
        query = query.where(ActivityEntry.source == source)
    if rule_id is not None:
        query = query.where(ActivityEntry.rule_id == rule_id)
    rows = session.exec(
        query.order_by(col(ActivityEntry.at).desc(), col(ActivityEntry.id).desc()).limit(
            max(1, min(limit, 500))
        )
    ).all()
    return [
        ActivityOut(**{**r.model_dump(), "at": time_of(r.at)})  # type: ignore[arg-type]
        for r in rows
    ]
