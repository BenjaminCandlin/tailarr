"""The SQLite database that lives in the config folder."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine

from ..jobs.models import JOB_TABLE_VERSION, Job
from ..library.models import (
    CACHE_TABLES,
    LIBRARY_CACHE_VERSION,
    MEDIA_TABLE_VERSION,
    MediaRecord,
)
from .permissions import create_file

CACHE_VERSION_KEY = "library_cache_version"
MEDIA_VERSION_KEY = "media_table_version"
JOB_VERSION_KEY = "job_table_version"


class Setting(SQLModel, table=True):
    """One saved setting. Values are stored as JSON text."""

    key: str = Field(primary_key=True)
    value: str


def make_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLite would create the file as rw-r--r--; Unraid shares expect group write too.
    # SQLite gives its journal files the same permissions as the database file.
    create_file(database_path)
    engine = create_engine(
        f"sqlite:///{database_path}",
        # The library scan writes from a background thread; wait for it rather than fail.
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    SQLModel.metadata.create_all(engine)
    _reset_if_outdated(engine, CACHE_VERSION_KEY, LIBRARY_CACHE_VERSION, CACHE_TABLES)
    _reset_if_outdated(engine, MEDIA_VERSION_KEY, MEDIA_TABLE_VERSION, (MediaRecord,))
    _reset_if_outdated(engine, JOB_VERSION_KEY, JOB_TABLE_VERSION, (Job,))
    return engine


def _reset_if_outdated(engine: Engine, key: str, version: int, models: tuple) -> None:
    """These tables only cache what's on disk: rebuild them when their layout changes."""
    with Session(engine) as session:
        row = session.get(Setting, key)
        if row is not None and row.value == str(version):
            return
    tables = [model.__table__ for model in models]
    SQLModel.metadata.drop_all(engine, tables=tables)
    SQLModel.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        session.merge(Setting(key=key, value=str(version)))
        session.commit()


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
