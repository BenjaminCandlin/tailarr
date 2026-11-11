"""System check: are the tools installed and the folders reachable?"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from .. import __version__
from ..core.config import AppConfig
from ..core.settings_store import get_library_settings
from ..core.system import check_folder, current_umask
from ..media.tools import TOOLS, find_tool, tool_version
from .deps import get_config, get_session

router = APIRouter(prefix="/api")


class ToolStatusOut(BaseModel):
    name: str
    label: str
    purpose: str
    found: bool
    version: str | None
    ok: bool


class FolderStatusOut(BaseModel):
    key: str
    label: str
    purpose: str
    path: str
    exists: bool
    writable: bool
    required: bool
    ok: bool


class RunningAsOut(BaseModel):
    uid: int
    gid: int
    umask: str


class HealthOut(BaseModel):
    ok: bool
    version: str
    tools: list[ToolStatusOut]
    folders: list[FolderStatusOut]
    running_as: RunningAsOut


@router.get("/health", response_model=HealthOut)
def health(
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> HealthOut:
    tools = []
    for tool in TOOLS:
        found = find_tool(tool.name) is not None
        version = tool_version(tool) if found else None
        ok = found and version is not None
        tools.append(
            ToolStatusOut(
                name=tool.name,
                label=tool.label,
                purpose=tool.purpose,
                found=found,
                version=version,
                ok=ok,
            )
        )

    library = get_library_settings(session, config)
    folder_checks = [
        check_folder(
            "movies", "Films folder", "Where your films are", Path(library.movies_dir), True
        ),
        check_folder("tv", "TV folder", "Where your TV shows are", Path(library.tv_dir), True),
        check_folder(
            "config", "Config folder", "Tailarr's settings and database", config.config_dir, True
        ),
        check_folder(
            "work",
            "Work folder (optional)",
            "Working space for making copies without Dolby Vision. Not needed: without it "
            "Tailarr uses the film's folder.",
            config.work_dir,
            False,
        ),
    ]
    folders = [FolderStatusOut(**f.__dict__, ok=f.ok) for f in folder_checks]

    running_as = RunningAsOut(uid=os.getuid(), gid=os.getgid(), umask=f"{current_umask():03o}")
    ok = all(t.ok for t in tools) and all(f.ok for f in folders)
    return HealthOut(
        ok=ok, version=__version__, tools=tools, folders=folders, running_as=running_as
    )
