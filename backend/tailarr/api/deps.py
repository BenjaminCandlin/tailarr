"""Shared pieces handed to each API endpoint."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlmodel import Session

from ..core.config import AppConfig


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
