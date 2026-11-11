#!/usr/bin/env python3
"""Make tiny sample MKV files for Tailarr's tests.

Usage:  python tests/samples/make_samples.py OUTPUT_FOLDER

Needs ffmpeg (with libx264 and libx265) and mkvmerge. Each sample is 2-3
seconds of a low-resolution test pattern with sine-wave audio, so the whole
set is only a few megabytes and takes a few seconds to make.

Dolby Vision and HDR10+ samples are made by adding real metadata frames
(copied from dovi_tool's test files, see fixtures/README.md) into the HEVC
video. This avoids needing special builds of x265.

The generated files are NOT committed to git.

Besides the individual samples in OUTPUT/files, a TRaSH Guides style tree is
made in OUTPUT/data:

    data/media/movies/<Film (Year)>/<Film (Year)>.mkv
    data/media/tv/<Show>/Season 01/<Show> - S01E01 - <Title>.mkv
    data/torrents/movies/<release>.mkv   (hardlink to one of the films)

The film folders also include poster artwork, TRaSH-style "{tmdb-...}" folder
names, a Tailarr "- HDR10" copy, a non-MKV film, an empty folder and a
leftover temporary file, so the library scanner meets real-world variety.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Bump when the samples change, so cached copies get rebuilt.
SAMPLES_VERSION = "2"

HDR10_X265 = (
    "repeat-headers=1:hdr10=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:"
    "master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):"
    "max-cll=1000,400"
)


@dataclass(frozen=True)
class Audio:
    language: str
    name: str
    codec: str  # ffmpeg encoder: aac, ac3
    channels: int = 2
    default: bool = False


@dataclass(frozen=True)
class Subtitle:
    language: str
    name: str
    default: bool = False
    forced: bool = False


@dataclass(frozen=True)
class Sample:
    name: str
    description: str
    video: str  # "h264", "hevc-sdr", "hdr10", "hdr10plus", "dv8", "dv5", "dv7", "dv7dual"
    fps: str  # as a fraction, e.g. "24000/1001"
    seconds: float = 2.0
    audio: tuple[Audio, ...] = ()
    subtitles: tuple[Subtitle, ...] = ()
    chapters: int = 0
    attachment: bool = False
    title: str = ""
    # What MediaInfo should report, used by tests.
    expect_hdr: tuple[str, ...] = field(default_factory=tuple)
    # Frame durations in milliseconds, repeated, for a variable frame rate; empty = constant.
    vfr_pattern: tuple[int, ...] = ()


ENG = Audio("eng", "English", "aac", 2, default=True)
FRE_51 = Audio("fre", "Français 5.1", "ac3", 6)
JPN = Audio("jpn", "Japanese", "aac", 2)

SAMPLES: tuple[Sample, ...] = (
    Sample(
        "sdr_multi",
        "H.264 SDR, 23.976 fps, three audio languages, forced and normal subtitles",
        "h264",
        "24000/1001",
        seconds=3,
        audio=(ENG, FRE_51, JPN),
        subtitles=(
            Subtitle("eng", "English", default=True),
            Subtitle("eng", "English (Forced)", forced=True),
            Subtitle("fre", "Français"),
            Subtitle("spa", "Español"),
        ),
        chapters=3,
        attachment=True,
        title="Sample Multi-Language Film",
    ),
    Sample("sdr_2997", "H.264 SDR at 29.97 fps", "h264", "30000/1001", audio=(ENG,)),
    Sample(
        "hdr10",
        "HEVC HDR10 at 25 fps",
        "hdr10",
        "25",
        audio=(ENG, FRE_51),
        subtitles=(Subtitle("eng", "English"),),
        chapters=2,
        expect_hdr=("HDR10",),
    ),
    Sample(
        "hdr10plus",
        "HEVC HDR10+ at 23.976 fps",
        "hdr10plus",
        "24000/1001",
        audio=(ENG,),
        expect_hdr=("HDR10+",),
    ),
    Sample(
        "dv_p8",
        "Dolby Vision profile 8.1 (HDR10 compatible) at 23.976 fps",
        "dv8",
        "24000/1001",
        audio=(ENG, FRE_51),
        subtitles=(Subtitle("eng", "English"), Subtitle("eng", "English (Forced)", forced=True)),
        chapters=2,
        attachment=True,
        expect_hdr=("Dolby Vision", "HDR10"),
    ),
    Sample(
        "dv_p5",
        "Dolby Vision profile 5 (no HDR10 fallback, must not be converted)",
        "dv5",
        "24000/1001",
        audio=(ENG,),
        expect_hdr=("Dolby Vision",),
    ),
    Sample(
        "dv_p7",
        "Dolby Vision profile 7 metadata (Blu-ray style), single video track",
        "dv7",
        "24000/1001",
        audio=(ENG,),
        expect_hdr=("Dolby Vision", "HDR10"),
    ),
    Sample(
        "dv_p7_dual",
        "Dolby Vision profile 7 with a real enhancement layer (BL+EL+RPU in one track, "
        "as MakeMKV makes from UHD Blu-rays)",
        "dv7dual",
        "24000/1001",
        audio=(ENG, FRE_51),
        subtitles=(Subtitle("eng", "English", default=True),),
        chapters=2,
        expect_hdr=("Dolby Vision", "HDR10"),
    ),
    Sample(
        "dv_p8_vfr",
        "Dolby Vision profile 8.1 with a variable frame rate",
        "dv8",
        "24000/1001",
        audio=(ENG,),
        expect_hdr=("Dolby Vision", "HDR10"),
        vfr_pattern=(42, 42, 41, 50, 33),
    ),
)

# The fake TRaSH-style library: (sample name, relative path inside data/).
LIBRARY: tuple[tuple[str, str], ...] = (
    ("sdr_multi", "media/movies/Sample Multi-Language Film (2021)/Sample Multi-Language Film (2021).mkv"),
    ("hdr10", "media/movies/Bright Lights (2019)/Bright Lights (2019) Bluray-2160p.mkv"),
    ("dv_p8", "media/movies/Colour Test (2023)/Colour Test (2023) WEBDL-2160p DV HDR10.mkv"),
    ("dv_p5", "media/movies/Streaming Only (2024)/Streaming Only (2024) WEBDL-2160p DV.mkv"),
    ("sdr_2997", "media/movies/The Long Weekend (1999) {tmdb-10001}/The Long Weekend (1999) {tmdb-10001} Bluray-1080p.mkv"),
    ("dv_p7_dual", "media/movies/Blu-ray Night (2018) {imdb-tt0000001}/Blu-ray Night (2018) Remux-2160p.mkv"),
    ("hdr10plus", "media/movies/Ärger im Paradies (2020)/Ärger im Paradies (2020) WEBDL-2160p.mkv"),
    # A folder named like a download (not renamed by Radarr).
    ("sdr_2997", "media/movies/The.Quiet.Hours.2017.1080p.BluRay.x264-GRP/the.quiet.hours.2017.1080p.bluray.x264-grp.mkv"),
    # A copy Tailarr made earlier, next to its original.
    ("hdr10", "media/movies/Colour Test (2023)/Colour Test (2023) WEBDL-2160p DV HDR10 - HDR10.mkv"),
    ("sdr_2997", "media/tv/Test Show/Season 01/Test Show - S01E01 - Pilot.mkv"),
    ("sdr_2997", "media/tv/Test Show/Season 01/Test Show - S01E02 - The Second One.mkv"),
    ("hdr10plus", "media/tv/Test Show/Season 02/Test Show - S02E01 - Brighter.mkv"),
    ("dv_p8", "media/tv/Another Show (2022)/Season 01/Another Show (2022) - S01E01 - Start.mkv"),
)
# Poster / backdrop artwork: (relative path, top colour, bottom colour).
ARTWORK: tuple[tuple[str, str, str], ...] = (
    ("media/movies/Colour Test (2023)/poster.jpg", "0x0f766e", "0x111827"),
    ("media/movies/Colour Test (2023)/fanart.jpg", "0x134e4a", "0x0b1220"),
    ("media/movies/Bright Lights (2019)/folder.jpg", "0xb45309", "0x1f2937"),
    ("media/movies/The Long Weekend (1999) {tmdb-10001}/poster.png", "0x1d4ed8", "0x0f172a"),
)
# Other things found in real film folders: (relative path, kind).
EXTRAS: tuple[tuple[str, str], ...] = (
    ("media/movies/Old Home Video (1995)/Old Home Video (1995).mp4", "mp4"),
    ("media/movies/Not Downloaded Yet (2025)/", "folder"),
    ("media/movies/Bright Lights (2019)/.tailarr-tmp-0123abcd.mkv", "junk"),
    ("media/movies/Bright Lights (2019)/Bright Lights (2019) Bluray-2160p.en.srt", "srt"),
)
# A film that is also "seeding" in the download client (same file, two names).
HARDLINKED = (
    "media/movies/Colour Test (2023)/Colour Test (2023) WEBDL-2160p DV HDR10.mkv",
    "torrents/movies/Colour.Test.2023.2160p.WEB-DL.DV.HDR10.mkv",
)


# --------------------------------------------------------------------------- helpers


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    # mkvmerge exit code 1 means "warnings", which is fine.
    if proc.returncode not in (0, 1) or (proc.returncode == 1 and args[0] != "mkvmerge"):
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{proc.stdout}\n{proc.stderr}")


def _split_nals(data: bytes) -> list[bytes]:
    starts = [m.start() for m in re.finditer(b"\x00\x00\x01", data)]
    nals = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(data)
        nal = data[start + 3 : end]
        if i + 1 < len(starts):
            nal = nal.rstrip(b"\x00")  # leading zero of the next 4-byte start code
        nals.append(nal)
    return nals


def _is_vcl(nal: bytes) -> bool:
    return ((nal[0] >> 1) & 0x3F) < 32


def add_dolby_vision(hevc: Path, rpu_file: Path, out: Path) -> int:
    """Add one Dolby Vision metadata frame (RPU) after every picture."""
    rpu = rpu_file.read_bytes()
    assert rpu.startswith(b"\x00\x00\x00\x01")
    rpu_nal = b"\x00\x00\x00\x01\x7c\x01" + rpu[4:]  # NAL type 62 (UNSPEC62)
    output = bytearray()
    frames = 0
    for nal in _split_nals(hevc.read_bytes()):
        output += b"\x00\x00\x00\x01" + nal
        if _is_vcl(nal):  # the test encodes use one slice per picture
            output += rpu_nal
            frames += 1
    out.write_bytes(bytes(output))
    return frames


class _BitWriter:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, value: int, width: int) -> None:
        self.bits += [(value >> (width - 1 - i)) & 1 for i in range(width)]

    def to_bytes(self) -> bytes:
        bits = self.bits + [0] * ((-len(self.bits)) % 8)
        return bytes(int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits), 8))


def _emulation_prevention(payload: bytes) -> bytes:
    out = bytearray()
    zeros = 0
    for byte in payload:
        if zeros >= 2 and byte <= 3:
            out.append(3)
            zeros = 0
        out.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(out)


def _hdr10plus_sei() -> bytes:
    """A minimal SMPTE ST 2094-40 (HDR10+) dynamic metadata SEI message."""
    w = _BitWriter()
    w.put(0xB5, 8)  # country code: USA
    w.put(0x003C, 16)  # terminal provider: Samsung
    w.put(0x0001, 16)  # provider oriented code
    w.put(4, 8)  # application identifier
    w.put(1, 8)  # application version
    w.put(1, 2)  # one processing window
    w.put(400, 27)  # targeted system display maximum luminance
    w.put(0, 1)  # no targeted display actual peak luminance
    for value in (1000, 900, 800):  # maxscl
        w.put(value, 17)
    w.put(300, 17)  # average maxrgb
    percentages = (1, 5, 10, 25, 50, 75, 90, 95, 99)
    w.put(len(percentages), 4)
    for i, pct in enumerate(percentages):
        w.put(pct, 7)
        w.put(10 * (i + 1), 17)
    w.put(0, 10)  # fraction bright pixels
    w.put(0, 1)  # no mastering display actual peak luminance
    w.put(0, 1)  # no tone mapping
    w.put(0, 1)  # no colour saturation mapping
    payload = w.to_bytes()
    sei = bytes([4, len(payload)]) + payload + b"\x80"  # payload type 4 = T.35
    return b"\x00\x00\x00\x01\x4e\x01" + _emulation_prevention(sei)  # prefix SEI


def add_hdr10plus(hevc: Path, out: Path) -> None:
    sei = _hdr10plus_sei()
    output = bytearray()
    for nal in _split_nals(hevc.read_bytes()):
        if _is_vcl(nal):
            output += sei
        output += b"\x00\x00\x00\x01" + nal
    out.write_bytes(bytes(output))


# --------------------------------------------------------------------------- building


def _video(sample: Sample, tmp: Path) -> tuple[Path, bool]:
    """Make the video stream. Returns (file, is_raw_hevc)."""
    src = ["-f", "lavfi", "-i", f"testsrc2=s=320x180:r={sample.fps}:d={sample.seconds}"]
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *src]
    if sample.video == "h264":
        out = tmp / "video.mkv"
        _run([*base, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(out)])
        return out, False

    hevc = tmp / "video.hevc"
    params = "log-level=error"
    if sample.video != "hevc-sdr":
        params += ":" + HDR10_X265
    _run(
        [
            *base,
            "-pix_fmt",
            "yuv420p10le",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            params,
            str(hevc),
        ]
    )
    final = tmp / "video-final.hevc"
    if sample.video in ("hdr10", "hevc-sdr"):
        return hevc, True
    if sample.video == "dv7dual":
        # A small enhancement layer carrying the profile 7 metadata, woven into the
        # base layer by dovi_tool, like a UHD Blu-ray remux.
        el = tmp / "el.hevc"
        _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                f"testsrc2=s=160x90:r={sample.fps}:d={sample.seconds}",
                "-pix_fmt", "yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast",
                "-x265-params", "log-level=error:repeat-headers=1", str(el),
            ]
        )  # fmt: skip
        el_rpu = tmp / "el-rpu.hevc"
        add_dolby_vision(el, FIXTURES / "fel_orig.bin", el_rpu)
        _run(["dovi_tool", "mux", "--bl", str(hevc), "--el", str(el_rpu), "-o", str(final)])
        return final, True
    if sample.video == "hdr10plus":
        add_hdr10plus(hevc, final)
    else:
        rpu = {"dv8": "profile8.bin", "dv5": "profile5.bin", "dv7": "fel_orig.bin"}[sample.video]
        add_dolby_vision(hevc, FIXTURES / rpu, final)
    return final, True


def _audio(track: Audio, seconds: float, tmp: Path, index: int) -> Path:
    out = tmp / f"audio{index}.mka"
    layout = "5.1" if track.channels == 6 else "stereo"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={440 + 110 * index}:duration={seconds}",
            "-af",
            f"aformat=channel_layouts={layout}",
            "-c:a",
            track.codec,
            "-b:a",
            "64k",
            str(out),
        ]
    )
    return out


def _srt(track: Subtitle, seconds: float, tmp: Path, index: int) -> Path:
    out = tmp / f"subs{index}.srt"
    end = int(seconds * 1000) - 100
    out.write_text(
        f"1\n00:00:00,100 --> 00:00:{end // 1000:02d},{end % 1000:03d}\n"
        f"{track.name} subtitle line\n",
        encoding="utf-8",
    )
    return out


def _chapters(count: int, seconds: float, tmp: Path) -> Path:
    out = tmp / "chapters.txt"
    lines = []
    for i in range(count):
        ms = int(seconds * 1000 * i / count)
        stamp = f"00:00:{ms // 1000:02d}.{ms % 1000:03d}"
        lines += [f"CHAPTER{i + 1:02d}={stamp}", f"CHAPTER{i + 1:02d}NAME=Chapter {i + 1}"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _cover(tmp: Path) -> Path:
    out = tmp / "cover.png"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=teal:s=60x90:d=1",
            "-frames:v",
            "1",
            str(out),
        ]
    )
    return out


def _artwork(out: Path, top: str, bottom: str) -> None:
    """A plain gradient picture standing in for a real poster."""
    w, h = (1280, 720) if "fanart" in out.name else (600, 900)
    gradient = f"gradients=s={w}x{h}:c0={top}:c1={bottom}:x0=0:y0=0:x1=0:y1={h}:d=1"
    _run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", gradient]
        + ["-frames:v", "1", str(out)]
    )


def _flag(value: bool) -> str:
    return "yes" if value else "no"


def build_sample(sample: Sample, out: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="tailarr-sample-") as tmp_name:
        tmp = Path(tmp_name)
        video, raw = _video(sample, tmp)
        args = ["mkvmerge", "--quiet", "-o", str(out)]
        if sample.title:
            args += ["--title", sample.title]
        if raw and sample.vfr_pattern:
            stamps = tmp / "timestamps.txt"
            frames = round(sample.seconds * eval(sample.fps))  # noqa: S307 (our own constant)
            times, now = [], 0
            for i in range(frames):
                times.append(str(now))
                now += sample.vfr_pattern[i % len(sample.vfr_pattern)]
            stamps.write_text("# timestamp format v2\n" + "\n".join(times) + "\n")
            args += ["--timestamps", f"0:{stamps}"]
        elif raw:
            args += ["--default-duration", f"0:{sample.fps}fps"]
        args += ["--language", "0:und", str(video)]
        for i, track in enumerate(sample.audio):
            args += [
                "--language",
                f"0:{track.language}",
                "--track-name",
                f"0:{track.name}",
                "--default-track-flag",
                f"0:{_flag(track.default)}",
                str(_audio(track, sample.seconds, tmp, i)),
            ]
        for i, track in enumerate(sample.subtitles):
            args += [
                "--sub-charset",
                "0:UTF-8",
                "--language",
                f"0:{track.language}",
                "--track-name",
                f"0:{track.name}",
                "--default-track-flag",
                f"0:{_flag(track.default)}",
                "--forced-display-flag",
                f"0:{_flag(track.forced)}",
                str(_srt(track, sample.seconds, tmp, i)),
            ]
        if sample.chapters:
            args += ["--chapters", str(_chapters(sample.chapters, sample.seconds, tmp))]
        if sample.attachment:
            args += [
                "--attachment-mime-type",
                "image/png",
                "--attachment-name",
                "cover.png",
                "--attach-file",
                str(_cover(tmp)),
            ]
        _run(args)
    return out


def build_all(output: Path) -> dict[str, Path]:
    """Build every sample (if not already built) and the fake library tree."""
    output.mkdir(parents=True, exist_ok=True)
    files = output / "files"
    files.mkdir(exist_ok=True)
    stamp = output / "samples-version.json"
    current = stamp.exists() and json.loads(stamp.read_text()).get("version") == SAMPLES_VERSION

    built: dict[str, Path] = {}
    for sample in SAMPLES:
        path = files / f"{sample.name}.mkv"
        if not (current and path.exists()):
            build_sample(sample, path)
        built[sample.name] = path

    data = output / "data"
    if data.exists():
        shutil.rmtree(data)
    for sample_name, relative in LIBRARY:
        target = data / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built[sample_name], target)
    seeding = data / HARDLINKED[1]
    seeding.parent.mkdir(parents=True, exist_ok=True)
    os.link(data / HARDLINKED[0], seeding)

    art = output / "artwork"
    art.mkdir(exist_ok=True)
    for relative, top, bottom in ARTWORK:
        cached = art / f"{top}-{bottom}-{Path(relative).name}"
        if not cached.exists():
            _artwork(cached, top, bottom)
        shutil.copyfile(cached, data / relative)
    for relative, kind in EXTRAS:
        target = data / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "folder":
            continue
        if kind == "mp4":
            _run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i"]
                + [str(built["sdr_2997"]), "-map", "0:v", "-c", "copy", str(target)]
            )
        elif kind == "srt":
            target.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        else:
            target.write_bytes(b"half-written")

    stamp.write_text(json.dumps({"version": SAMPLES_VERSION}))
    return built


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    for tool in ("ffmpeg", "mkvmerge", "dovi_tool"):
        if shutil.which(tool) is None:
            print(f"Missing required program: {tool}")
            return 1
    built = build_all(Path(sys.argv[1]))
    for name, path in built.items():
        print(f"{name:12} {path.stat().st_size / 1024:7.0f} KB  {path}")
    print(f"Library tree: {Path(sys.argv[1]) / 'data'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
