"""Making a copy without Dolby Vision, with the real tools, on the sample films."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tailarr.core.config import AppConfig
from tailarr.jobs import hdr10_copy
from tailarr.jobs.engine import JobQueue
from tailarr.jobs.models import CopyRecord
from tailarr.main import create_app
from tailarr.media.probe import describe, read_file
from tests.conftest import page_client

COLOUR = "Colour Test (2023)"
COLOUR_FILE = "Colour Test (2023) WEBDL-2160p DV HDR10.mkv"
COLOUR_COPY = "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv"
BLURAY = "Blu-ray Night (2018) {imdb-tt0000001}"
BLURAY_FILE = "Blu-ray Night (2018) Remux-2160p.mkv"
ENV = {**os.environ, "LC_ALL": "C.UTF-8"}


@pytest.fixture
def library(samples_dir: Path, config: AppConfig) -> Path:
    movies = Path(config.default_movies_dir)
    shutil.rmtree(movies)
    shutil.copytree(samples_dir / "data" / "media" / "movies", movies, symlinks=True)
    return movies


def _start(client: TestClient):
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    queue: JobQueue = client.app.state.job_queue  # type: ignore[attr-defined]
    queue.start()
    return queue


@pytest.fixture
def app_client(client: TestClient, library: Path):
    queue = _start(client)
    yield client
    queue.stop()


def _film_id(client: TestClient, title: str) -> int:
    films = client.get("/api/films").json()["films"]
    return next(f["id"] for f in films if f["title"] == title)


def _wait(client: TestClient, job_id: int, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def _copy(client: TestClient, film_id: int, file: str, **extra) -> dict:
    response = client.post(
        f"/api/films/{film_id}/hdr10-copy", json={"file": file, "confirmed": True, **extra}
    )
    assert response.status_code == 202, response.text
    return _wait(client, response.json()["id"])


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mkvmerge(path: Path) -> dict:
    out = subprocess.run(["mkvmerge", "-J", str(path)], capture_output=True, env=ENV, check=True)
    return json.loads(out.stdout)


def _timestamps(path: Path, tmp: Path, track: int = 0) -> str:
    out = tmp / f"ts-{path.stem}-{time.monotonic_ns()}.txt"
    subprocess.run(
        ["mkvextract", str(path), "timestamps_v2", f"{track}:{out}"],
        capture_output=True,
        env=ENV,
        check=True,
    )
    return out.read_text()


def _leftovers(*folders: Path) -> list[str]:
    return [
        p.name
        for f in folders
        if f.exists()
        for p in f.iterdir()
        if p.name.startswith(".tailarr-tmp-")
    ]


# -- planning -----------------------------------------------------------------------------


def test_copy_name() -> None:
    assert hdr10_copy.output_name("Film (2020).mkv") == "Film (2020) - HDR10.mkv"


@pytest.mark.parametrize(
    ("sample", "message"),
    [
        ("dv_p5", "profile 5, which has no HDR10 picture underneath"),
        ("sdr_multi", "has no Dolby Vision"),
        ("hdr10plus", "has no Dolby Vision"),
    ],
)
def test_refusals(samples_dir: Path, sample: str, message: str) -> None:
    details = describe(read_file(samples_dir / "files" / f"{sample}.mkv"))
    with pytest.raises(hdr10_copy.Hdr10Refused) as err:
        hdr10_copy.plan_hdr10(details)
    assert message in str(err.value)


def test_plans(samples_dir: Path) -> None:
    p8 = hdr10_copy.plan_hdr10(describe(read_file(samples_dir / "files" / "dv_p8.mkv")))
    assert p8.remove_rpu and p8.dropped == [] and p8.expected_formats == ["HDR10"]
    assert p8.profile == "8.1"
    p7 = hdr10_copy.plan_hdr10(describe(read_file(samples_dir / "files" / "dv_p7_dual.mkv")))
    assert p7.remove_rpu and p7.source.hdr.dv_dual_layer and p7.profile == "7"


# -- the API and the job ------------------------------------------------------------------


def test_preview(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client, "Colour Test")
    response = app_client.post(
        f"/api/films/{film_id}/hdr10-copy/preview", json={"file": COLOUR_FILE}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["new_file"] == COLOUR_COPY
    assert data["exists"] is True  # the sample library already has one
    assert data["dv_profile"] == "8.1"
    assert data["blu_ray_layers"] is False
    assert data["result"] == ["HDR10"]
    assert data["kept"][0].startswith("Audio 1: English")
    assert len(data["kept"]) == 4
    assert (data["chapters"], data["attachments"]) == (2, 1)
    assert data["uses_work_folder"] is False
    source_size = (library / COLOUR / COLOUR_FILE).stat().st_size
    assert [s["label"] for s in data["space"]] == ["the disk with your films"]
    assert data["space"][0]["needed"] > 2 * source_size
    assert data["enough_space"] is True


def test_preview_refusals(app_client: TestClient) -> None:
    streaming = _film_id(app_client, "Streaming Only")
    response = app_client.post(
        f"/api/films/{streaming}/hdr10-copy/preview",
        json={"file": "Streaming Only (2024) WEBDL-2160p DV.mkv"},
    )
    assert response.status_code == 400
    assert "profile 5" in response.json()["detail"]
    weekend = _film_id(app_client, "The Long Weekend")
    detail = app_client.get(f"/api/films/{weekend}").json()
    response = app_client.post(
        f"/api/films/{weekend}/hdr10-copy/preview", json={"file": detail["main_file"]}
    )
    assert response.status_code == 400
    assert "no Dolby Vision" in response.json()["detail"]


def test_needs_confirmation_and_asks_before_replacing_a_copy(app_client: TestClient) -> None:
    film_id = _film_id(app_client, "Colour Test")
    response = app_client.post(f"/api/films/{film_id}/hdr10-copy", json={"file": COLOUR_FILE})
    assert response.status_code == 400
    response = app_client.post(
        f"/api/films/{film_id}/hdr10-copy", json={"file": COLOUR_FILE, "confirmed": True}
    )
    assert response.status_code == 409
    assert "Replace the existing copy" in response.json()["detail"]


def test_profile_8_copy(app_client: TestClient, library: Path, tmp_path: Path) -> None:
    film_id = _film_id(app_client, "Colour Test")
    original = library / COLOUR / COLOUR_FILE
    before = (_hash(original), original.stat().st_mtime)
    job = _copy(app_client, film_id, COLOUR_FILE, overwrite=True)
    assert job["status"] == "done", job
    assert job["title"] == "Make a copy without Dolby Vision"
    assert job["step_count"] == 6
    assert job["message"].startswith(f"HDR10 copy saved as “{COLOUR_COPY}”")
    assert job["result"] == {"copy": COLOUR_COPY, "source": COLOUR_FILE}
    assert (_hash(original), original.stat().st_mtime) == before  # never touched

    copy = library / COLOUR / COLOUR_COPY
    details = describe(read_file(copy))
    assert details.hdr.formats == ["HDR10"]
    assert details.hdr.dv_profile is None

    src, out = _mkvmerge(original), _mkvmerge(copy)
    # Every other track is the original's, with its settings; chapters and attachments too.
    assert [t["properties"]["uid"] for t in out["tracks"][1:]] == [
        t["properties"]["uid"] for t in src["tracks"][1:]
    ]
    for a, b in zip(src["tracks"][1:], out["tracks"][1:], strict=True):
        for key in ("language", "track_name", "default_track", "forced_track"):
            assert a["properties"].get(key) == b["properties"].get(key)
    assert out["chapters"] == src["chapters"]
    assert len(out["attachments"]) == len(src["attachments"]) == 1
    # The exact frame rate and every frame's timing.
    assert out["tracks"][0]["properties"]["default_duration"] == 41708333
    assert _timestamps(copy, tmp_path) == _timestamps(original, tmp_path)
    assert out["container"]["properties"]["duration"] == src["container"]["properties"]["duration"]
    # No Dolby Vision settings block in the track header either.
    info = subprocess.run(["mkvinfo", str(copy)], capture_output=True, text=True, env=ENV)
    assert "Dolby Vision" not in info.stdout

    umask = os.umask(0)
    os.umask(umask)
    assert copy.stat().st_mode & 0o777 == 0o666 & ~umask
    assert _leftovers(library / COLOUR) == []
    with Session(app_client.app.state.engine) as session:  # type: ignore[attr-defined]
        record = session.get(CopyRecord, str(copy))
        assert record is not None and record.kind == "hdr10_copy"

    files = app_client.get(f"/api/films/{film_id}").json()["files"]
    hdr10 = next(f for f in files if f["name"] == COLOUR_COPY)
    assert hdr10["copy_of"] == COLOUR_FILE
    assert hdr10["media"]["hdr"] == ["HDR10"]
    # It can replace the original, but only if the owner chooses to: the summary says
    # plainly that Dolby Vision would be gone.
    assert hdr10["can_replace_original"] is True
    response = app_client.post(
        f"/api/films/{film_id}/replace-original/preview", json={"copy_file": COLOUR_COPY}
    )
    assert response.status_code == 200, response.text
    assert response.json()["loses_dolby_vision"] is True


def test_replace_the_original_with_an_hdr10_copy(app_client: TestClient, library: Path) -> None:
    film_id = _film_id(app_client, "Blu-ray Night")
    assert _copy(app_client, film_id, BLURAY_FILE)["status"] == "done"
    copy = hdr10_copy.output_name(BLURAY_FILE)
    response = app_client.post(
        f"/api/films/{film_id}/replace-original",
        json={"copy_file": copy, "confirmed": True, "understood": True},
    )
    assert response.status_code == 202, response.text
    job = _wait(app_client, response.json()["id"])
    assert job["status"] == "done", job
    original = library / BLURAY / BLURAY_FILE
    assert describe(read_file(original)).hdr.dv_profile is None  # the copy took its place
    recycled = library / BLURAY / ".tailarr-recycle" / BLURAY_FILE
    assert describe(read_file(recycled)).hdr.dv_profile == 7  # the original waits there
    detail = app_client.get(f"/api/films/{film_id}").json()
    assert [f["name"] for f in detail["files"]] == [BLURAY_FILE]
    assert detail["media"]["hdr"] == ["HDR10"]


def test_profile_7_blu_ray_copy(app_client: TestClient, library: Path, tmp_path: Path) -> None:
    """UHD Blu-ray style: the enhancement layer is left out along with the Dolby Vision info."""
    film_id = _film_id(app_client, "Blu-ray Night")
    original = library / BLURAY / BLURAY_FILE
    preview = app_client.post(
        f"/api/films/{film_id}/hdr10-copy/preview", json={"file": BLURAY_FILE}
    ).json()
    assert preview["dv_profile"] == "7" and preview["blu_ray_layers"] is True
    assert preview["exists"] is False
    job = _copy(app_client, film_id, BLURAY_FILE)
    assert job["status"] == "done", job
    copy = library / BLURAY / hdr10_copy.output_name(BLURAY_FILE)
    details = describe(read_file(copy))
    assert details.hdr.formats == ["HDR10"] and details.hdr.dv_profile is None
    assert copy.stat().st_size < original.stat().st_size  # the enhancement layer is gone
    assert _timestamps(copy, tmp_path) == _timestamps(original, tmp_path)
    assert len(details.of_type("video")) == 1
    assert [t.language for t in details.of_type("audio")] == ["eng", "fre"]


def test_variable_frame_rate(
    app_client: TestClient, library: Path, samples_dir: Path, tmp_path: Path
) -> None:
    folder = library / "Odd Timing (2010)"
    folder.mkdir()
    original = folder / "Odd Timing (2010).mkv"
    shutil.copy(samples_dir / "files" / "dv_p8_vfr.mkv", original)
    app_client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    film_id = _film_id(app_client, "Odd Timing")
    job = _copy(app_client, film_id, original.name)
    assert job["status"] == "done", job
    copy = folder / "Odd Timing (2010) - HDR10.mkv"
    stamps = _timestamps(copy, tmp_path)
    assert stamps == _timestamps(original, tmp_path)
    assert "\n84\n125\n175\n" in stamps  # really uneven


def test_profile_7_with_a_separate_enhancement_track(
    app_client: TestClient, library: Path, samples_dir: Path, tmp_path: Path
) -> None:
    """Older dual-track files: the enhancement layer is its own track, simply left out."""
    work = tmp_path / "build"
    work.mkdir()
    dual = samples_dir / "files" / "dv_p7_dual.mkv"
    subprocess.run(
        ["mkvextract", str(dual), "tracks", f"0:{work / 'v.hevc'}"],
        capture_output=True, env=ENV, check=True,
    )  # fmt: skip
    subprocess.run(
        ["dovi_tool", "demux", "-i", str(work / "v.hevc"),
         "--bl-out", str(work / "bl.hevc"), "--el-out", str(work / "el.hevc")],
        capture_output=True, check=True,
    )  # fmt: skip
    folder = library / "Two Tracks (2015)"
    folder.mkdir()
    original = folder / "Two Tracks (2015).mkv"
    subprocess.run(
        ["mkvmerge", "-q", "-o", str(original),
         "--default-duration", "0:24000/1001p", str(work / "bl.hevc"),
         "--default-duration", "0:24000/1001p", str(work / "el.hevc"),
         "--no-video", str(samples_dir / "files" / "dv_p8.mkv")],
        capture_output=True, env=ENV, check=True,
    )  # fmt: skip
    details = describe(read_file(original))
    assert details.hdr.dv_profile is not None and details.hdr.dv_dual_layer
    plan = hdr10_copy.plan_hdr10(details)
    assert plan.remove_rpu is False and len(plan.dropped) == 1

    app_client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    job = _copy(app_client, _film_id(app_client, "Two Tracks"), original.name)
    assert job["status"] == "done", job
    copy = describe(read_file(folder / "Two Tracks (2015) - HDR10.mkv"))
    assert copy.hdr.dv_profile is None and copy.hdr.formats == ["HDR10"]
    assert len(copy.of_type("video")) == 1
    assert [t.uid for t in copy.tracks] == [t.uid for t in details.tracks if t not in plan.dropped]


def test_work_folder_is_used_when_mounted(library: Path, config: AppConfig, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    client = page_client(create_app(dataclasses.replace(config, work_dir=work)))
    queue = _start(client)
    try:
        film_id = _film_id(client, "Blu-ray Night")
        preview = client.post(
            f"/api/films/{film_id}/hdr10-copy/preview", json={"file": BLURAY_FILE}
        ).json()
        assert preview["uses_work_folder"] is True
        seen: list[str] = []
        real = hdr10_copy.mkvmerge_args

        def spy(plan, source, video, timestamps, out):
            seen.extend([video, timestamps, out])
            return real(plan, source, video, timestamps, out)

        hdr10_copy.mkvmerge_args = spy  # type: ignore[assignment]
        try:
            assert _copy(client, film_id, BLURAY_FILE)["status"] == "done"
        finally:
            hdr10_copy.mkvmerge_args = real  # type: ignore[assignment]
        video, timestamps, out = (Path(p) for p in seen)
        assert video.parent == work and timestamps.parent == work  # working files in /work
        assert out.parent == library / BLURAY  # the copy is written next to the original
        assert _leftovers(work, library / BLURAY) == []
    finally:
        queue.stop()


def test_failed_check_leaves_nothing_behind(
    app_client: TestClient, library: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        hdr10_copy, "verify_hdr10", lambda copy, plan: ["Dolby Vision is still in the copy"]
    )
    film_id = _film_id(app_client, "Blu-ray Night")
    job = _copy(app_client, film_id, BLURAY_FILE)
    assert job["status"] == "failed"
    assert "thrown away" in job["error"]
    assert job["error_details"] == "Dolby Vision is still in the copy"
    assert sorted(p.name for p in (library / BLURAY).iterdir()) == [BLURAY_FILE]


def test_profile_5_refused_when_the_job_runs(app_client: TestClient, library: Path) -> None:
    queue: JobQueue = app_client.app.state.job_queue  # type: ignore[attr-defined]
    folder = library / "Streaming Only (2024)"
    path = folder / "Streaming Only (2024) WEBDL-2160p DV.mkv"
    job = queue.submit("hdr10_copy", title="T", subject="S", path=str(path), params={})
    finished = _wait(app_client, job.id)  # type: ignore[arg-type]
    assert finished["status"] == "failed"
    assert "profile 5" in finished["error"]
    assert [p.name for p in folder.iterdir()] == [path.name]


def test_not_enough_space(app_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(hdr10_copy, "free_space", lambda path: 1000)
    film_id = _film_id(app_client, "Blu-ray Night")
    preview = app_client.post(
        f"/api/films/{film_id}/hdr10-copy/preview", json={"file": BLURAY_FILE}
    ).json()
    assert preview["enough_space"] is False
    response = app_client.post(
        f"/api/films/{film_id}/hdr10-copy", json={"file": BLURAY_FILE, "confirmed": True}
    )
    assert response.status_code == 507
