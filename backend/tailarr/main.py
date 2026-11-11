"""The Tailarr web app: the API plus the web pages."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from . import __version__
from .api import copies, films, health, jobs, settings
from .core.config import AppConfig
from .core.db import make_engine
from .core.settings_store import get_library_settings
from .jobs import hdr10_copy, remove_tracks, replace_original, track_settings
from .jobs.engine import JobQueue
from .jobs.recycle import RecycleCleaner
from .library.media_reader import MediaReader
from .library.models import FilmFile
from .library.scanner import FilmScanner, rescan_film_folder

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Bring the film list up to date in the background as soon as Tailarr starts.
    # (After the scan, the media reader reads the details of new or changed files.)
    if not app.state.film_scanner.start_if_stale():
        app.state.media_reader.start()
    app.state.job_queue.start()
    app.state.recycle_cleaner.start()
    yield
    app.state.recycle_cleaner.stop()
    app.state.job_queue.stop()
    app.state.media_reader.stop()


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

    app.state.media_reader = MediaReader(engine, films_root)
    app.state.film_scanner = FilmScanner(engine, films_root, app.state.media_reader.start)

    def library_roots() -> list[str]:
        with Session(engine) as session:
            library = get_library_settings(session, config)
            return [library.movies_dir, library.tv_dir]

    def file_changed(path: str) -> None:
        try:
            app.state.media_reader.file_changed(path)
        except Exception:  # the job's own result matters more than refreshing the page
            log.exception("Couldn't re-read %s after changing it", path)

    def folder_changed(folder: str) -> None:
        """A job added, replaced or removed files in a film's folder: show it straight away."""
        try:
            with Session(engine) as session:
                film = rescan_film_folder(session, folder, films_root())
                if film is None:
                    return
                files = session.exec(select(FilmFile).where(FilmFile.film_id == film.id)).all()
                for file in files:
                    app.state.media_reader.get(session, file.path)  # reads new/changed files
        except Exception:  # the job's own result matters more than refreshing the page
            log.exception("Couldn't refresh %s after changing it", folder)

    app.state.job_queue = JobQueue(
        engine,
        [
            track_settings.make_job_type(library_roots, file_changed),
            remove_tracks.make_job_type(engine, library_roots, folder_changed),
            replace_original.make_job_type(engine, library_roots, folder_changed),
            hdr10_copy.make_job_type(
                engine, library_roots, lambda: config.work_dir, folder_changed
            ),
        ],
    )
    app.state.recycle_cleaner = RecycleCleaner(engine, library_roots)

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(films.router)
    app.include_router(copies.router)
    app.include_router(jobs.router)

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
