"""Check that the generated sample files are what the later tests rely on."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from .conftest import make_samples

SAMPLES = {s.name: s for s in make_samples.SAMPLES}


def _identify(path: Path) -> dict:
    out = subprocess.run(["mkvmerge", "-J", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _mediainfo(path: Path, inform: str) -> str:
    out = subprocess.run(
        ["mediainfo", f"--Inform=Video;{inform}", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_tracks(samples_dir: Path, name: str) -> None:
    sample = SAMPLES[name]
    info = _identify(samples_dir / "files" / f"{name}.mkv")
    assert info["container"]["recognized"]
    tracks = info["tracks"]
    video = [t for t in tracks if t["type"] == "video"]
    audio = [t for t in tracks if t["type"] == "audio"]
    subs = [t for t in tracks if t["type"] == "subtitles"]
    assert len(video) == 1
    assert [t["properties"]["language"] for t in audio] == [a.language for a in sample.audio]
    assert [t["properties"]["track_name"] for t in audio] == [a.name for a in sample.audio]
    assert [t["properties"]["audio_channels"] for t in audio] == [a.channels for a in sample.audio]
    assert [t["properties"]["language"] for t in subs] == [s.language for s in sample.subtitles]
    assert [t["properties"]["forced_track"] for t in subs] == [s.forced for s in sample.subtitles]
    assert [t["properties"]["default_track"] for t in subs] == [s.default for s in sample.subtitles]
    assert len(info.get("chapters", [])) == (1 if sample.chapters else 0)
    if sample.chapters:
        assert info["chapters"][0]["num_entries"] == sample.chapters
    assert len(info.get("attachments", [])) == (1 if sample.attachment else 0)
    if sample.title:
        assert info["container"]["properties"]["title"] == sample.title


@pytest.mark.parametrize(
    ("name", "fps"),
    [("sdr_multi", "23.976"), ("sdr_2997", "29.970"), ("hdr10", "25.000"), ("dv_p8", "23.976")],
)
def test_sample_frame_rates(samples_dir: Path, name: str, fps: str) -> None:
    assert _mediainfo(samples_dir / "files" / f"{name}.mkv", "%FrameRate%") == fps


@pytest.mark.parametrize(
    ("name", "hdr_format", "profile"),
    [
        ("sdr_multi", "", ""),
        ("hdr10", "SMPTE ST 2086", ""),
        ("hdr10plus", "SMPTE ST 2094 App 4", ""),
        ("dv_p8", "Dolby Vision", "dvhe.08"),
        ("dv_p5", "Dolby Vision", "dvhe.05"),
        ("dv_p7", "Dolby Vision", "dvhe.07"),
    ],
)
def test_sample_hdr(samples_dir: Path, name: str, hdr_format: str, profile: str) -> None:
    path = samples_dir / "files" / f"{name}.mkv"
    detected = _mediainfo(path, "%HDR_Format%")
    if hdr_format:
        assert detected.startswith(hdr_format)
    else:
        assert detected == ""
    assert _mediainfo(path, "%HDR_Format_Profile%").startswith(profile)
    if name in ("dv_p8", "dv_p7", "hdr10"):
        assert "HDR10" in _mediainfo(path, "%HDR_Format_Compatibility%")
    if name == "dv_p5":
        # Profile 5 has no HDR10 base layer.
        assert _mediainfo(path, "%HDR_Format_Compatibility%").split("/")[0].strip() == ""


def test_library_tree_follows_trash_layout(samples_dir: Path) -> None:
    data = samples_dir / "data"
    films = sorted(p.name for p in (data / "media" / "movies").iterdir())
    assert "Colour Test (2023)" in films
    episodes = list((data / "media" / "tv" / "Test Show").glob("Season */*.mkv"))
    assert len(episodes) == 3
    assert (data / "torrents" / "movies").is_dir()


def test_seeding_file_is_hardlinked(samples_dir: Path) -> None:
    data = samples_dir / "data"
    film = data / make_samples.HARDLINKED[0]
    seeding = data / make_samples.HARDLINKED[1]
    assert film.stat().st_nlink == 2
    assert film.stat().st_ino == seeding.stat().st_ino
