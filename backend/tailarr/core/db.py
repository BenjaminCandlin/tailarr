"""The SQLite database that lives in the config folder."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine

from ..library.models import CACHE_TABLES, LIBRARY_CACHE_VERSION
from .permissions import create_file

CACHE_VERSION_KEY = "library_cache_version"


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
    _reset_cache_if_outdated(engine)
    return engine


def _reset_cache_if_outdated(engine: Engine) -> None:
    """The library tables only cache what's on disk: rebuild them when their layout changes."""
    with Session(engine) as session:
        row = session.get(Setting, CACHE_VERSION_KEY)
        if row is not None and row.value == str(LIBRARY_CACHE_VERSION):
            return
    tables = [model.__table__ for model in CACHE_TABLES]  # type: ignore[attr-defined]
    SQLModel.metadata.drop_all(engine, tables=tables)
    SQLModel.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        session.merge(Setting(key=CACHE_VERSION_KEY, value=str(LIBRARY_CACHE_VERSION)))
        session.commit()


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
