"""The Tailarr web app: the API plus the web pages."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from . import __version__
from .api import films, health, settings
from .core.config import AppConfig
from .core.db import make_engine
from .core.settings_store import get_library_settings
from .library.scanner import FilmScanner


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Bring the film list up to date in the background as soon as Tailarr starts.
    app.state.film_scanner.start_if_stale()
    yield


def create_app(config: AppConfig | None = None) -> FastAPI:
    config = config or AppConfig.from_env()
    app = FastAPI(
        title="Tailarr",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.config = config
    engine = app.state.engine = make_engine(config.database_path)

    def films_root() -> Path:
        with Session(engine) as session:
            return Path(get_library_settings(session, config).movies_dir)

    app.state.film_scanner = FilmScanner(engine, films_root)

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(films.router)

    _mount_frontend(app, config.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        # Unknown API addresses are real errors, not web pages.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        if index.is_file():
            # Every other address is a page of the app (e.g. /films, /settings).
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        raise HTTPException(status_code=503, detail="The web interface hasn't been built.")
