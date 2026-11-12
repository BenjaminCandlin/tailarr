"""Reading tracks and HDR details, with the real tools on the generated sample files."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tailarr.core.config import AppConfig
from tailarr.library.models import MediaRecord
from tailarr.main import create_app
from tailarr.media.describe import (
    audio_codec_name,
    channel_layout,
    detect_hdr,
    resolution_label,
    subtitle_codec_name,
    video_codec_name,
)
from tailarr.media.languages import language_name
from tailarr.media.probe import ReadError, describe, read_file
from tests.conftest import page_client

from .conftest import make_samples

SAMPLES = {s.name: s for s in make_samples.SAMPLES}


def _details(samples_dir: Path, name: str):
    return describe(read_file(samples_dir / "files" / f"{name}.mkv"))


# --------------------------------------------------------------------------- HDR on real files


@pytest.mark.parametrize(
    ("name", "formats", "profile", "fallback", "can_remove"),
    [
        ("sdr_multi", [], None, None, False),
        ("sdr_2997", [], None, None, False),
        ("hdr10", ["HDR10"], None, None, False),
        ("hdr10plus", ["HDR10+", "HDR10"], None, None, False),
        ("dv_p8", ["Dolby Vision", "HDR10"], "8.1", "HDR10", True),
        ("dv_p7", ["Dolby Vision", "HDR10"], "7", "HDR10", True),
        # Profile 5 has no HDR10 picture underneath: never offer to remove Dolby Vision.
        ("dv_p5", ["Dolby Vision"], "5", None, False),
    ],
)
def test_hdr_detection(samples_dir, name, formats, profile, fallback, can_remove) -> None:
    hdr = _details(samples_dir, name).hdr
    assert hdr.formats == formats
    assert hdr.dv_label == profile
    assert hdr.dv_fallback == fallback
    assert hdr.can_remove_dv is can_remove


@pytest.mark.parametrize("name", list(SAMPLES))
def test_tracks_match_the_samples(samples_dir: Path, name: str) -> None:
    sample = SAMPLES[name]
    details = _details(samples_dir, name)
    assert details.container == "Matroska"
    assert details.duration == pytest.approx(sample.seconds, abs=0.2)
    assert len(details.of_type("video")) == 1
    audio = details.of_type("audio")
    subs = details.of_type("subtitles")
    assert [t.name for t in audio] == [a.name for a in sample.audio]
    assert [t.language for t in audio] == [a.language for a in sample.audio]
    assert [t.default for t in audio] == [a.default for a in sample.audio]
    assert [t.forced for t in subs] == [s.forced for s in sample.subtitles]
    assert [t.default for t in subs] == [s.default for s in sample.subtitles]
    assert details.chapters == sample.chapters
    assert len(details.attachments) == (1 if sample.attachment else 0)
    # Track numbers are mkvmerge's (later stages use them to change tracks).
    assert [t.id for t in details.tracks] == list(range(len(details.tracks)))


def test_friendly_track_details(samples_dir: Path) -> None:
    details = _details(samples_dir, "sdr_multi")
    assert details.title == "Sample Multi-Language Film"
    video = details.of_type("video")[0]
    assert video.codec == "H.264 (AVC)"
    assert (video.width, video.height) == (320, 180)
    assert video.frame_rate == "23.976"
    assert video.bit_depth == 8

    english, french, japanese = details.of_type("audio")
    assert (english.codec, english.channel_layout, english.language_name) == (
        "AAC",
        "Stereo",
        "English",
    )
    assert (french.codec, french.channel_layout) == ("Dolby Digital", "5.1")
    assert french.name == "Français 5.1"  # accents survive
    assert japanese.language_name == "Japanese"

    subs = details.of_type("subtitles")
    assert [s.language_name for s in subs] == ["English", "English", "French", "Spanish"]
    assert subs[0].codec == "SRT" and subs[0].picture_based is False
    assert subs[1].forced and subs[1].name == "English (Forced)"
    assert details.attachments[0].name == "cover.png"
    assert details.attachments[0].mime_type == "image/png"


def test_frame_rates(samples_dir: Path) -> None:
    assert _details(samples_dir, "sdr_2997").of_type("video")[0].frame_rate == "29.97"
    assert _details(samples_dir, "hdr10").of_type("video")[0].frame_rate == "25"
    assert _details(samples_dir, "dv_p8").of_type("video")[0].bit_depth == 10


def test_names_survive_a_plain_c_locale(samples_dir: Path, monkeypatch) -> None:
    # The container starts with no language settings; accents must still come through.
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANG", "C")
    raw = read_file(samples_dir / "files" / "sdr_multi.mkv")
    names = [t.name for t in describe(raw).of_type("subtitles")]
    assert "Français" in names and "Español" in names


def test_stored_output_is_small(samples_dir: Path) -> None:
    raw = read_file(samples_dir / "files" / "dv_p8.mkv")
    import json

    text = json.dumps(raw)
    assert len(text) < 12_000
    assert "Encoded_Library_Settings" not in text
    assert "codec_private_data" not in text


def test_unreadable_file_gives_friendly_error(tmp_path: Path) -> None:
    broken = tmp_path / "Broken (2020).mkv"
    broken.write_bytes(b"this is not a video" * 100)
    with pytest.raises(ReadError) as error:
        read_file(broken)
    assert "couldn't read" in error.value.message or "doesn't recognise" in error.value.message
    assert error.value.details


def test_mp4_files_can_be_read(samples_dir: Path) -> None:
    mp4 = (
        samples_dir
        / "data"
        / "media"
        / "movies"
        / "Old Home Video (1995)"
        / "Old Home Video (1995).mp4"
    )
    details = describe(read_file(mp4))
    assert details.container != "Matroska"
    assert details.of_type("video")[0].codec == "H.264 (AVC)"


# --------------------------------------------------------------------------- naming rules


def test_language_names() -> None:
    assert language_name("eng") == "English"
    assert language_name("fre") == "French"
    assert language_name("fra") == "French"  # the other ISO code for French
    assert language_name("ger") == "German"
    assert language_name("gre") == "Greek"
    assert language_name("chi", "zh-Hant") == "Chinese (Traditional)"
    assert language_name("por", "pt-BR") == "Portuguese (Brazil)"
    assert language_name("spa", "es-419") == "Spanish (Latin America)"
    assert language_name("und") == "Unknown language"
    assert language_name("", None) == "Unknown language"
    assert language_name("en") == "English"
    assert language_name("xyz") == "xyz"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ("A_TRUEHD", "TrueHD Atmos", "Dolby TrueHD with Dolby Atmos", "", "MLP FBA"),
            "Dolby TrueHD Atmos",
        ),
        (("A_TRUEHD", "TrueHD", "", "", "MLP FBA"), "Dolby TrueHD"),
        (
            ("A_EAC3", "E-AC-3", "Dolby Digital Plus with Dolby Atmos", "JOC", "E-AC-3"),
            "Dolby Digital Plus Atmos",
        ),
        (("A_EAC3", "E-AC-3", "Dolby Digital Plus", "", "E-AC-3"), "Dolby Digital Plus"),
        (("A_AC3", "AC-3", "Dolby Digital", "", "AC-3"), "Dolby Digital"),
        (
            ("A_DTS", "DTS-HD Master Audio", "DTS-HD Master Audio", "XLL", "DTS"),
            "DTS-HD Master Audio",
        ),
        (("A_DTS", "DTS-HD Master Audio", "DTS-HD Master Audio + DTS:X", "XLL X", "DTS"), "DTS:X"),
        (("A_DTS", "DTS-HD High Resolution Audio", "", "XBR", "DTS"), "DTS-HD High Resolution"),
        (("A_DTS", "DTS", "", "", "DTS"), "DTS"),
        (("A_AAC-2", "AAC", "", "LC", "AAC"), "AAC"),
        (("A_OPUS", "Opus", "", "", "Opus"), "Opus"),
        (("A_FLAC", "FLAC", "", "", "FLAC"), "FLAC"),
        (("A_PCM/INT/LIT", "PCM", "", "", "PCM"), "PCM (uncompressed)"),
        (("", "AAC", "", "", ""), "AAC"),  # MP4 files have no MKV codec id
    ],
)
def test_audio_codec_names(args, expected) -> None:
    assert audio_codec_name(*args) == expected


def test_other_codec_names() -> None:
    assert video_codec_name("V_MPEGH/ISO/HEVC", "HEVC/H.265/MPEG-H") == "HEVC (H.265)"
    assert video_codec_name("V_AV1", "AV1") == "AV1"
    assert video_codec_name("", "MPEG-4p10/AVC/H.264") == "H.264 (AVC)"
    assert subtitle_codec_name("S_HDMV/PGS", "HDMV PGS") == ("PGS", True)
    assert subtitle_codec_name("S_VOBSUB", "VobSub") == ("VobSub", True)
    assert subtitle_codec_name("S_TEXT/ASS", "SubStationAlpha") == ("ASS (styled text)", False)


def test_channel_layouts() -> None:
    assert channel_layout(1) == "Mono"
    assert channel_layout(2, "L R") == "Stereo"
    assert channel_layout(6, "L R C LFE Ls Rs") == "5.1"
    assert channel_layout(8, "L R C LFE Ls Rs Lb Rb") == "7.1"
    assert channel_layout(6) == "5.1"
    assert channel_layout(8) == "7.1"
    assert channel_layout(6, "L R C Ls Rs Cs") == "6.0"
    assert channel_layout(None) == ""


def test_resolution_labels() -> None:
    assert resolution_label(3840, 2160) == "4K"
    assert resolution_label(3840, 1600) == "4K"  # wide film, cropped
    assert resolution_label(1920, 800) == "1080p"
    assert resolution_label(1280, 720) == "720p"
    assert resolution_label(720, 576) == "576p"
    assert resolution_label(720, 480) == "480p"
    assert resolution_label(320, 180) == "SD"
    assert resolution_label(None, None) is None


@pytest.mark.parametrize(
    ("fields", "formats", "label", "fallback"),
    [
        # Real MediaInfo answers for common release types.
        (
            {
                "HDR_Format": "Dolby Vision / SMPTE ST 2094 App 4 / SMPTE ST 2086",
                "HDR_Format_Profile": "dvhe.08 / ",
                "HDR_Format_Compatibility": "HDR10 / HDR10+ Profile B / HDR10",
                "transfer_characteristics": "PQ",
            },
            ["Dolby Vision", "HDR10+", "HDR10"],
            "8.1",
            "HDR10",
        ),
        (
            {
                "HDR_Format": "Dolby Vision / SMPTE ST 2086",
                "HDR_Format_Profile": "dvhe.07 / ",
                "HDR_Format_Settings": "BL+EL+RPU / ",
                "HDR_Format_Compatibility": "Blu-ray / HDR10",
                "transfer_characteristics": "PQ",
            },
            ["Dolby Vision", "HDR10"],
            "7",
            "HDR10",
        ),
        (
            {
                "HDR_Format": "Dolby Vision",
                "HDR_Format_Profile": "dvhe.05",
                "transfer_characteristics": "PQ",
            },
            ["Dolby Vision"],
            "5",
            None,
        ),
        (
            {
                "HDR_Format": "Dolby Vision",
                "HDR_Format_Profile": "dvhe.08",
                "HDR_Format_Compatibility": "HLG",
                "transfer_characteristics": "HLG",
            },
            ["Dolby Vision", "HLG"],
            "8.4",
            "HLG",
        ),
        ({"transfer_characteristics": "HLG"}, ["HLG"], None, None),
        ({"transfer_characteristics": "PQ"}, ["HDR10"], None, None),
        ({"transfer_characteristics": "BT.709"}, [], None, None),
        ({}, [], None, None),
    ],
)
def test_hdr_rules(fields, formats, label, fallback) -> None:
    hdr = detect_hdr(fields)
    assert hdr.formats == formats
    assert hdr.dv_label == label
    assert hdr.dv_fallback == fallback


def test_profile_7_dual_layer() -> None:
    hdr = detect_hdr(
        {
            "HDR_Format": "Dolby Vision / SMPTE ST 2086",
            "HDR_Format_Profile": "dvhe.07 / ",
            "HDR_Format_Settings": "BL+EL+RPU / ",
            "HDR_Format_Compatibility": "Blu-ray / HDR10",
        }
    )
    assert hdr.dv_dual_layer is True
    assert hdr.can_remove_dv is True


# --------------------------------------------------------------------------- the API


@pytest.fixture
def library(samples_dir: Path, config: AppConfig) -> Path:
    movies = Path(config.default_movies_dir)
    shutil.rmtree(movies)
    shutil.copytree(samples_dir / "data" / "media" / "movies", movies, symlinks=True)
    return movies


@pytest.fixture
def scanned(client: TestClient, library: Path) -> TestClient:
    client.app.state.film_scanner.run()  # type: ignore[attr-defined]
    return client


@pytest.fixture
def read(scanned: TestClient) -> TestClient:
    scanned.app.state.media_reader.run()  # type: ignore[attr-defined]
    return scanned


def _films(client: TestClient) -> dict[str, dict]:
    return {film["title"]: film for film in client.get("/api/films").json()["films"]}


def test_scan_starts_reading_details(scanned: TestClient) -> None:
    reader = scanned.app.state.media_reader  # type: ignore[attr-defined]
    reader.wait(60)
    films = _films(scanned)
    assert all(f["media"]["read"] for f in films.values())


def test_film_list_has_hdr_badges(read: TestClient) -> None:
    body = read.get("/api/films").json()
    assert body["reading"]["running"] is False
    films = {f["title"]: f for f in body["films"]}
    colour = films["Colour Test"]["media"]
    assert colour == {
        "read": True,
        "error": False,
        "hdr": ["Dolby Vision", "HDR10"],
        "dv_profile": "8.1",
        "resolution": "SD",
    }
    assert films["Streaming Only"]["media"]["dv_profile"] == "5"
    assert films["Blu-ray Night"]["media"]["dv_profile"] == "7"
    assert films["Ärger im Paradies"]["media"]["hdr"] == ["HDR10+", "HDR10"]
    assert films["Bright Lights"]["media"]["hdr"] == ["HDR10"]
    assert films["The Long Weekend"]["media"]["hdr"] == []
    assert films["Old Home Video"]["media"]["read"] is True  # MP4 is read too


def test_film_detail_files_have_summaries(read: TestClient) -> None:
    film_id = _films(read)["Colour Test"]["id"]
    detail = read.get(f"/api/films/{film_id}").json()
    assert detail["media"]["dv_profile"] == "8.1"
    main, copy = detail["files"]
    assert main["media"]["hdr"] == ["Dolby Vision", "HDR10"]
    assert copy["media"]["hdr"] == ["HDR10"]  # the copy made without Dolby Vision


def test_media_endpoint(scanned: TestClient) -> None:
    film_id = _films(scanned)["Sample Multi-Language Film"]["id"]
    media = scanned.get(f"/api/films/{film_id}/media").json()
    assert media["file"] == "Sample Multi-Language Film (2021).mkv"
    assert media["error"] is None
    assert media["title"] == "Sample Multi-Language Film"
    assert media["chapters"] == 3
    assert media["attachments"] == [{"name": "cover.png", "mime_type": "image/png", "size": 219}]
    assert media["hdr"]["formats"] == []
    kinds = [t["type"] for t in media["tracks"]]
    assert kinds == ["video"] + ["audio"] * 3 + ["subtitles"] * 4
    french = media["tracks"][2]
    assert french["language_name"] == "French"
    assert french["codec"] == "Dolby Digital"
    assert french["channel_layout"] == "5.1"
    forced = media["tracks"][5]
    assert forced["forced"] is True and forced["default"] is False


def test_media_of_a_copy_and_dv_details(scanned: TestClient) -> None:
    film_id = _films(scanned)["Colour Test"]["id"]
    main = scanned.get(f"/api/films/{film_id}/media").json()
    assert main["hdr"] == {
        "formats": ["Dolby Vision", "HDR10"],
        "dv_profile": "8.1",
        "dv_fallback": "HDR10",
        "dv_dual_layer": False,
        "can_remove_dv": True,
    }
    name = "Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv"
    copy = scanned.get(f"/api/films/{film_id}/media", params={"file": name}).json()
    assert copy["file"] == name
    assert copy["hdr"]["formats"] == ["HDR10"]

    p5 = _films(scanned)["Streaming Only"]["id"]
    hdr = scanned.get(f"/api/films/{p5}/media").json()["hdr"]
    assert hdr["dv_profile"] == "5" and hdr["can_remove_dv"] is False


def test_media_reads_once_then_remembers(scanned: TestClient, config: AppConfig) -> None:
    film_id = _films(scanned)["Bright Lights"]["id"]
    first = scanned.get(f"/api/films/{film_id}/media").json()
    second = scanned.get(f"/api/films/{film_id}/media").json()
    assert first["read_at"] == second["read_at"]
    again = scanned.get(f"/api/films/{film_id}/media", params={"refresh": True}).json()
    assert again["read_at"] >= first["read_at"]
    # Remembered across restarts.
    restarted = page_client(create_app(config))
    assert restarted.get(f"/api/films/{film_id}/media").json()["read_at"] == again["read_at"]


def test_changed_file_is_read_again(read: TestClient, library: Path) -> None:
    film_id = _films(read)["Bright Lights"]["id"]
    before = read.get(f"/api/films/{film_id}/media").json()
    target = library / "Bright Lights (2019)" / "Bright Lights (2019) Bluray-2160p.mkv"
    # A new release replaces the file (Radarr upgrade): now it has Dolby Vision.
    tmp = target.with_name("upgrade.tmp")
    shutil.copyfile(
        library / "Colour Test (2023)" / "Colour Test (2023) WEBDL-2160p DV HDR10.mkv", tmp
    )
    os.replace(tmp, target)
    future = time.time() + 10
    os.utime(target, (future, future))
    after = read.get(f"/api/films/{film_id}/media").json()
    assert after["read_at"] != before["read_at"]
    assert after["hdr"]["dv_profile"] == "8.1"
    # The list catches up after the next scan + background read.
    read.app.state.film_scanner.run()  # type: ignore[attr-defined]
    read.app.state.media_reader.run()  # type: ignore[attr-defined]
    assert _films(read)["Bright Lights"]["media"]["dv_profile"] == "8.1"


def test_unreadable_file_is_explained(scanned: TestClient, library: Path) -> None:
    folder = library / "Damaged Film (2010)"
    folder.mkdir()
    (folder / "Damaged Film (2010).mkv").write_bytes(b"\x00garbage" * 500)
    scanned.app.state.film_scanner.run()  # type: ignore[attr-defined]
    scanned.app.state.media_reader.run()  # type: ignore[attr-defined]
    film = _films(scanned)["Damaged Film"]
    assert film["media"]["read"] is True and film["media"]["error"] is True
    media = scanned.get(f"/api/films/{film['id']}/media").json()
    assert media["tracks"] == []
    assert "Tailarr couldn't read" in media["error"] or "doesn't recognise" in media["error"]
    assert media["error_details"]


def test_unknown_file_is_refused(scanned: TestClient, library: Path) -> None:
    film_id = _films(scanned)["Colour Test"]["id"]
    for name in ("nope.mkv", "../Bright Lights (2019)/Bright Lights (2019) Bluray-2160p.mkv"):
        response = scanned.get(f"/api/films/{film_id}/media", params={"file": name})
        assert response.status_code == 404


def test_file_gone_since_scan(scanned: TestClient, library: Path) -> None:
    film_id = _films(scanned)["Bright Lights"]["id"]
    (library / "Bright Lights (2019)" / "Bright Lights (2019) Bluray-2160p.mkv").unlink()
    response = scanned.get(f"/api/films/{film_id}/media")
    assert response.status_code == 404
    assert "Check for new films" in response.json()["detail"]


def test_removed_films_are_forgotten(read: TestClient, library: Path, config: AppConfig) -> None:
    shutil.rmtree(library / "Bright Lights (2019)")
    read.app.state.film_scanner.run()  # type: ignore[attr-defined]
    read.app.state.media_reader.run()  # type: ignore[attr-defined]
    with Session(read.app.state.engine) as session:  # type: ignore[attr-defined]
        paths = session.exec(select(MediaRecord.path)).all()
    assert paths
    assert not any("Bright Lights" in p for p in paths)


def test_records_kept_when_films_folder_is_missing(read: TestClient, library: Path) -> None:
    hidden = library.with_name("movies-away")
    library.rename(hidden)
    read.app.state.film_scanner.run()  # type: ignore[attr-defined]
    read.app.state.media_reader.run()  # type: ignore[attr-defined]
    hidden.rename(library)
    assert all(f["media"]["read"] for f in _films(read).values())


def test_reader_starts_when_tailarr_starts(config: AppConfig, library: Path) -> None:
    app = create_app(config)
    with page_client(app) as client:
        app.state.film_scanner.wait(30)
        app.state.media_reader.wait(60)
        assert all(f["media"]["read"] for f in _films(client).values())
