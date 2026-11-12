from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tailarr.core.config import AppConfig
from tailarr.main import create_app

REPO = Path(__file__).resolve().parents[2]

# In CI every tool must be present: missing tools fail tests instead of being skipped.
REQUIRE_ALL_TOOLS = os.environ.get("TAILARR_REQUIRE_ALL_TOOLS") == "1"


def _load_make_samples():
    path = REPO / "tests" / "samples" / "make_samples.py"
    spec = importlib.util.spec_from_file_location("make_samples", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_samples"] = module
    spec.loader.exec_module(module)
    return module


make_samples = _load_make_samples()


@pytest.fixture(scope="session")
def samples_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    for tool in ("ffmpeg", "mkvmerge", "dovi_tool"):
        if shutil.which(tool) is None:
            pytest.fail(f"{tool} is needed to make the sample files")
    out = tmp_path_factory.mktemp("samples")
    make_samples.build_all(out)
    return out


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    data = tmp_path / "data"
    movies = data / "media" / "movies"
    tv = data / "media" / "tv"
    movies.mkdir(parents=True)
    tv.mkdir(parents=True)
    return AppConfig(
        config_dir=tmp_path / "config",
        work_dir=tmp_path / "work-not-mounted",
        default_movies_dir=str(movies),
        default_tv_dir=str(tv),
        static_dir=tmp_path / "static",
    )


# Tailarr's own page sends this with every change (cross-site protection).
PAGE_HEADERS = {"X-Requested-With": "tailarr"}


def page_client(app) -> TestClient:  # noqa: ANN001
    """A test client that talks to Tailarr the way its own web page does."""
    return TestClient(app, headers=PAGE_HEADERS)


@pytest.fixture
def client(config: AppConfig) -> TestClient:
    return page_client(create_app(config))
