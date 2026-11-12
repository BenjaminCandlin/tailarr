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
from .api import actions, automation, connections, films, health, jobs, rules, settings, tv
from .connections.service import Connections
from .core.config import AppConfig
from .core.db import make_engine
from .core.paths import is_inside
from .core.settings_store import get_library_settings
from .jobs import hdr10_copy, remove_tracks, replace_original, track_settings
from .jobs.engine import JobQueue
from .jobs.recycle import RecycleCleaner
from .library.media_reader import MediaReader
from .library.models import EpisodeFile, FilmFile
from .library.scanner import FilmScanner, rescan_film_folder
from .library.tv_scanner import TvScanner, rescan_show_folder
from .rules.automation import AutoRunner

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Bring the film list up to date in the background as soon as Tailarr starts.
    # (After the scan, the media reader reads the details of new or changed files.)
    films_started = app.state.film_scanner.start_if_stale()
    tv_started = app.state.tv_scanner.start_if_stale()
    if not (films_started or tv_started):
        app.state.media_reader.start()
    app.state.job_queue.start()
    app.state.recycle_cleaner.start()
    app.state.connections.start()
    app.state.auto_runner.start()
    yield
    app.state.auto_runner.stop()
    app.state.connections.stop()
    app.state.recycle_cleaner.stop()
    app.state.job_queue.stop()
    app.state.media_reader.stop()


def create_app(config: AppConfig | None = None, *, transport: object | None = None) -> FastAPI:
    """The app. `transport` lets tests answer instead of real Radarr/Sonarr/Plex servers."""
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

    def tv_root() -> Path:
        with Session(engine) as session:
            return Path(get_library_settings(session, config).tv_dir)

    def library_roots() -> list[str]:
        with Session(engine) as session:
            library = get_library_settings(session, config)
            return [library.movies_dir, library.tv_dir]

    app.state.media_reader = MediaReader(engine, lambda: [Path(p) for p in library_roots()])
    app.state.connections = Connections(engine, config, transport=transport)  # type: ignore[arg-type]
    app.state.connections.settings()  # saves the first webhook secret now, before any thread runs

    def scanned() -> None:
        app.state.media_reader.start()
        app.state.connections.sync_if_stale()
        auto = getattr(app.state, "auto_runner", None)
        if auto is not None:
            auto.scanned()

    app.state.film_scanner = FilmScanner(engine, films_root, scanned)
    app.state.tv_scanner = TvScanner(engine, tv_root, scanned)

    def file_changed(path: str) -> None:
        try:
            app.state.media_reader.file_changed(path)
        except Exception:  # the job's own result matters more than refreshing the page
            log.exception("Couldn't re-read %s after changing it", path)

    def folder_changed(folder: str) -> None:
        """A job added, replaced or removed files in a folder: show it straight away."""
        try:
            with Session(engine) as session:
                if is_inside(folder, tv_root()):
                    show = rescan_show_folder(session, folder, tv_root())
                    if show is None:
                        return
                    files: list[FilmFile | EpisodeFile] = list(
                        session.exec(
                            select(EpisodeFile).where(
                                EpisodeFile.show_id == show.id,
                                EpisodeFile.path.startswith(folder),  # type: ignore[union-attr]
                            )
                        ).all()
                    )
                else:
                    film = rescan_film_folder(session, folder, films_root())
                    if film is None:
                        return
                    files = list(
                        session.exec(select(FilmFile).where(FilmFile.film_id == film.id)).all()
                    )
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
    app.state.job_queue.on_done.append(app.state.connections.after_job)
    app.state.folder_changed = folder_changed

    def start_scans() -> None:
        app.state.film_scanner.start()
        app.state.tv_scanner.start()

    app.state.auto_runner = AutoRunner(
        engine, config, app.state.media_reader, app.state.job_queue, folder_changed, start_scans
    )
    app.state.on_webhook = [app.state.auto_runner.webhook_hook]
    app.state.job_queue.on_done.append(app.state.auto_runner.after_job)
    app.state.recycle_cleaner = RecycleCleaner(engine, library_roots)

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(films.router)
    app.include_router(actions.make_router("/api/films", films.load_film))
    app.include_router(tv.router)
    app.include_router(tv.episodes_router)
    app.include_router(actions.make_router("/api/episodes", tv.load_episode))
    app.include_router(tv.languages_router)
    app.include_router(connections.router)
    app.include_router(rules.router)
    app.include_router(automation.router)
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
