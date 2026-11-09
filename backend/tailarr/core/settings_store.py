"""Settings the owner can change in the web page, saved in the database."""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session

from .config import AppConfig
from .db import Setting
from .paths import PathMapping

LIBRARY_KEY = "library"

# Folders that must never be used as a Films or TV folder.
_FORBIDDEN = {"/", "/config", "/app", "/data", "/proc", "/sys", "/dev", "/etc", "/usr"}


def _clean_folder(value: str) -> str:
    value = value.strip()
    if not value.startswith("/"):
        raise ValueError("Please enter a full folder path that starts with '/'.")
    path = str(PurePosixPath(value))
    if ".." in PurePosixPath(path).parts:
        raise ValueError("Folder paths can't contain '..'.")
    if path in _FORBIDDEN:
        raise ValueError(f"'{path}' is too broad. Choose the folder that holds your media.")
    return path


class PathMappingModel(BaseModel):
    remote: str = Field(description="Path as Radarr/Sonarr report it")
    local: str = Field(description="The same path as Tailarr sees it")

    @field_validator("remote", "local")
    @classmethod
    def _absolute(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("Paths must start with '/'.")
        return str(PurePosixPath(value))

    def to_mapping(self) -> PathMapping:
        return PathMapping(remote=self.remote, local=self.local)


class LibrarySettings(BaseModel):
    movies_dir: str
    tv_dir: str
    path_mappings: list[PathMappingModel] = Field(default_factory=list)

    @field_validator("movies_dir", "tv_dir")
    @classmethod
    def _folder(cls, value: str) -> str:
        return _clean_folder(value)

    @model_validator(mode="after")
    def _separate(self) -> LibrarySettings:
        films, tv = PurePosixPath(self.movies_dir), PurePosixPath(self.tv_dir)
        if films == tv or films in tv.parents or tv in films.parents:
            raise ValueError("The Films folder and the TV folder must be separate folders.")
        return self


def get_library_settings(session: Session, config: AppConfig) -> LibrarySettings:
    row = session.get(Setting, LIBRARY_KEY)
    if row is None:
        return LibrarySettings(movies_dir=config.default_movies_dir, tv_dir=config.default_tv_dir)
    return LibrarySettings.model_validate(json.loads(row.value))


def save_library_settings(session: Session, settings: LibrarySettings) -> LibrarySettings:
    row = session.get(Setting, LIBRARY_KEY) or Setting(key=LIBRARY_KEY, value="")
    row.value = settings.model_dump_json()
    session.add(row)
    session.commit()
    return settings
