"""Start-up configuration, read from environment variables.

These are the values the container starts with. Settings the owner can change
in the web page (such as the Films and TV folders) are stored in the database;
the environment variables only provide their first, default values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MOVIES_DIR = "/data/media/movies"
DEFAULT_TV_DIR = "/data/media/tv"


def _default_static_dir() -> Path:
    installed = Path("/app/static")
    if installed.is_dir():
        return installed
    # Running from a source checkout: use the built frontend.
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


@dataclass(frozen=True)
class AppConfig:
    config_dir: Path
    work_dir: Path
    default_movies_dir: str
    default_tv_dir: str
    static_dir: Path

    @property
    def database_path(self) -> Path:
        return self.config_dir / "tailarr.db"

    @classmethod
    def from_env(cls) -> AppConfig:
        env = os.environ
        return cls(
            config_dir=Path(env.get("TAILARR_CONFIG_DIR", "/config")),
            work_dir=Path(env.get("TAILARR_WORK_DIR", "/work")),
            default_movies_dir=env.get("TAILARR_MOVIES_DIR", DEFAULT_MOVIES_DIR),
            default_tv_dir=env.get("TAILARR_TV_DIR", DEFAULT_TV_DIR),
            static_dir=Path(env.get("TAILARR_STATIC_DIR", str(_default_static_dir()))),
        )
