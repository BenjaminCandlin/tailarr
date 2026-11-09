"""The SQLite database that lives in the config folder."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine

from .permissions import create_file


class Setting(SQLModel, table=True):
    """One saved setting. Values are stored as JSON text."""

    key: str = Field(primary_key=True)
    value: str


def make_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLite would create the file as rw-r--r--; Unraid shares expect group write too.
    # SQLite gives its journal files the same permissions as the database file.
    create_file(database_path)
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
