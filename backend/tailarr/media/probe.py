"""Reading what's inside a video file: its tracks, chapters, attachments and HDR.

Two tools are used, each for what it does best:

* ``mkvmerge -J`` lists the tracks exactly the way MKVToolNix numbers them
  (the numbers later stages need to change or remove tracks), with names,
  languages and default/forced flags.
* ``mediainfo`` recognises HDR formats (Dolby Vision with its profile, HDR10,
  HDR10+, HLG) and commercial audio names such as Atmos and DTS:X.

Reading is split in two steps. :func:`read_file` runs the tools and keeps only
the parts of their output Tailarr needs (a few KB per file), which is stored in
the database. :func:`describe` turns that stored output into friendly
information, so improving the descriptions never requires re-reading the
(possibly huge) video files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .describe import (
    HdrInfo,
    audio_codec_name,
    channel_layout,
    detect_hdr,
    resolution_label,
    subtitle_codec_name,
    video_codec_name,
)
from .languages import language_name
from .tools import ToolError, run_tool

# Big tool fields that are never needed (encoder settings, codec set-up data).
_DROP_MKVMERGE = {"codec_private_data"}
_KEEP_MEDIAINFO_GENERAL = {"Format", "Duration", "FileSize", "Title", "Movie"}
_DROP_MEDIAINFO = {"Encoded_Library_Settings", "extra", "Encoded_Library", "Encoded_Date"}

# Reading a big file on a sleeping Unraid disk can take a while (the disk spins up first).
_TIMEOUT = 300


class ReadError(ToolError):
    """The file couldn't be read (message in plain English, details for experts)."""


def _trim_mkvmerge(data: dict[str, Any]) -> dict[str, Any]:
    for track in data.get("tracks", []):
        props = track.get("properties", {})
        for key in _DROP_MKVMERGE:
            props.pop(key, None)
    return {
        "container": data.get("container", {}),
        "tracks": data.get("tracks", []),
        "chapters": data.get("chapters", []),
        "attachments": [
            {k: a.get(k) for k in ("id", "file_name", "content_type", "size")}
            for a in data.get("attachments", [])
        ],
    }


def _trim_mediainfo(data: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = (data.get("media") or {}).get("track") or []
    kept = []
    for track in tracks:
        kind = track.get("@type")
        if kind == "General":
            keep = _KEEP_MEDIAINFO_GENERAL | {"@type"}
            kept.append({k: v for k, v in track.items() if k in keep})
        elif kind in ("Video", "Audio", "Text"):
            kept.append({k: v for k, v in track.items() if k not in _DROP_MEDIAINFO})
    return kept


def read_file(path: str | Path) -> dict[str, Any]:
    """Run mkvmerge and MediaInfo on a file. Returns the trimmed raw output.

    Raises ReadError if mkvmerge can't read the file. MediaInfo problems are
    not fatal: tracks are still shown, just without HDR details.
    """
    path = str(path)
    try:
        result = run_tool("mkvmerge", ["-J", path], timeout=_TIMEOUT)
        identified = json.loads(result.stdout)
    except ToolError as error:
        raise ReadError(
            "Tailarr couldn't read the tracks in this file. It may be damaged, still being "
            "copied, or on a disk that isn't available right now.",
            error.details or error.message,
        ) from error
    except json.JSONDecodeError as error:
        raise ReadError(
            "MKVToolNix gave an answer Tailarr couldn't understand.", str(error)
        ) from error
    if not identified.get("container", {}).get("recognized", False):
        raise ReadError(
            "MKVToolNix doesn't recognise this file as a video file it can read.",
            "\n".join(identified.get("errors", []) or [result.stdout[:2000]]),
        )

    raw: dict[str, Any] = {"mkvmerge": _trim_mkvmerge(identified), "mediainfo": None}
    try:
        info = run_tool("mediainfo", ["--Output=JSON", path], timeout=_TIMEOUT)
        raw["mediainfo"] = _trim_mediainfo(json.loads(info.stdout))
    except (ToolError, json.JSONDecodeError) as error:
        raw["mediainfo_error"] = getattr(error, "details", "") or str(error)
    return raw


# --------------------------------------------------------------------------- describing


@dataclass
class Track:
    id: int  # mkvmerge's track number (0, 1, 2, ...)
    uid: str  # the track's unique ID inside the file (text: too big for JavaScript numbers)
    type: str  # "video", "audio" or "subtitles"
    codec: str  # friendly, e.g. "Dolby TrueHD Atmos"
    codec_id: str
    language: str  # code, e.g. "eng"
    language_name: str  # e.g. "English"
    name: str  # the track's title, may be empty
    default: bool
    forced: bool
    enabled: bool = True
    hearing_impaired: bool = False
    visual_impaired: bool = False
    commentary: bool = False
    original: bool = False
    # Video
    width: int | None = None
    height: int | None = None
    resolution: str | None = None
    frame_rate: str | None = None
    bit_depth: int | None = None
    hdr: HdrInfo | None = None
    default_duration: int | None = None  # nanoseconds per frame, as stored in the file
    display_dimensions: str | None = None  # e.g. "3840x1606"
    # Audio
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    # Subtitles
    picture_based: bool | None = None


@dataclass
class Attachment:
    name: str
    mime_type: str
    size: int


@dataclass
class MediaDetails:
    container: str
    title: str
    duration: float | None  # seconds
    tracks: list[Track] = field(default_factory=list)
    chapters: int = 0
    attachments: list[Attachment] = field(default_factory=list)
    hdr: HdrInfo = field(default_factory=HdrInfo)
    resolution: str | None = None
    hdr_checked: bool = True  # False when MediaInfo couldn't read the file

    def of_type(self, kind: str) -> list[Track]:
        return [t for t in self.tracks if t.type == kind]


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _frame_rate(props: dict[str, Any], info: dict[str, Any]) -> str | None:
    rate = info.get("FrameRate")
    if rate:
        try:
            value = float(rate)
        except ValueError:
            return None
        mode = " (variable)" if info.get("FrameRate_Mode") == "VFR" else ""
        return f"{value:.3f}".rstrip("0").rstrip(".") + mode
    duration = props.get("default_duration")
    if duration:
        return f"{1e9 / duration:.3f}".rstrip("0").rstrip(".")
    return None


def _match_mediainfo(
    track: dict[str, Any], index_of_type: int, mediainfo: list[dict[str, Any]]
) -> dict[str, Any]:
    """Find MediaInfo's entry for an mkvmerge track: by unique id, else by position."""
    kind = {"video": "Video", "audio": "Audio", "subtitles": "Text"}[track["type"]]
    uid = track.get("properties", {}).get("uid")
    same_kind = [t for t in mediainfo if t.get("@type") == kind]
    if uid is not None:
        for entry in same_kind:
            if entry.get("UniqueID") == str(uid):
                return entry
    for entry in same_kind:
        if entry.get("StreamOrder") == str(track.get("id")):
            return entry
    return same_kind[index_of_type] if index_of_type < len(same_kind) else {}


def describe(raw: dict[str, Any]) -> MediaDetails:
    """Turn stored tool output (from read_file) into friendly details."""
    mkv = raw.get("mkvmerge") or {}
    mediainfo: list[dict[str, Any]] = raw.get("mediainfo") or []
    container = mkv.get("container", {})
    cprops = container.get("properties", {})
    duration_ns = cprops.get("duration")
    general = next((t for t in mediainfo if t.get("@type") == "General"), {})
    duration = duration_ns / 1e9 if duration_ns else None
    if duration is None and general.get("Duration"):
        try:
            duration = float(general["Duration"])
        except ValueError:
            duration = None

    details = MediaDetails(
        container=container.get("type") or "Unknown",
        title=cprops.get("title") or "",
        duration=duration,
        hdr_checked=raw.get("mediainfo") is not None,
    )
    seen: dict[str, int] = {}
    for track in mkv.get("tracks", []):
        kind = track.get("type")
        if kind not in ("video", "audio", "subtitles"):
            continue
        index = seen.get(kind, 0)
        seen[kind] = index + 1
        props = track.get("properties", {})
        info = _match_mediainfo(track, index, mediainfo)
        codec_id = props.get("codec_id") or ""
        codec = track.get("codec") or ""
        language = props.get("language") or "und"
        item = Track(
            id=int(track.get("id", 0)),
            uid=str(props.get("uid") or ""),
            type=kind,
            codec=codec,
            codec_id=codec_id,
            language=language,
            language_name=language_name(language, props.get("language_ietf")),
            name=props.get("track_name") or "",
            default=bool(props.get("default_track", False)),
            forced=bool(props.get("forced_track", False)),
            enabled=bool(props.get("enabled_track", True)),
            hearing_impaired=bool(props.get("flag_hearing_impaired", False)),
            visual_impaired=bool(props.get("flag_visual_impaired", False)),
            commentary=bool(props.get("flag_commentary", False)),
            original=bool(props.get("flag_original", False)),
        )
        if kind == "video":
            item.codec = video_codec_name(codec_id, codec)
            width, height = _dimensions(props, info)
            item.width, item.height = width, height
            item.resolution = resolution_label(width, height)
            item.frame_rate = _frame_rate(props, info)
            item.bit_depth = _int(info.get("BitDepth"))
            item.default_duration = _int(props.get("default_duration"))
            item.display_dimensions = props.get("display_dimensions") or None
            item.hdr = detect_hdr(info)
        elif kind == "audio":
            item.codec = audio_codec_name(
                codec_id,
                codec,
                info.get("Format_Commercial_IfAny", ""),
                info.get("Format_AdditionalFeatures", ""),
                info.get("Format", ""),
            )
            item.channels = _int(props.get("audio_channels")) or _int(info.get("Channels"))
            item.channel_layout = channel_layout(item.channels, info.get("ChannelLayout", ""))
            item.sample_rate = _int(props.get("audio_sampling_frequency"))
        else:
            item.codec, item.picture_based = subtitle_codec_name(codec_id, codec)
        details.tracks.append(item)

    for chapter_list in mkv.get("chapters", []):
        details.chapters += int(chapter_list.get("num_entries", 0))
    details.attachments = [
        Attachment(a.get("file_name") or "", a.get("content_type") or "", int(a.get("size") or 0))
        for a in mkv.get("attachments", [])
    ]
    main_video = _main_video(details)
    if main_video is not None:
        details.hdr = main_video.hdr or HdrInfo()
        details.resolution = main_video.resolution
        # Profile 7 discs: the second video track is the Dolby Vision enhancement layer.
        extra = [t for t in details.of_type("video") if t is not main_video and t.hdr]
        if any(t.hdr and t.hdr.dv_profile for t in extra) and not details.hdr.dv_profile:
            layer = next(t.hdr for t in extra if t.hdr and t.hdr.dv_profile)
            details.hdr = HdrInfo(
                formats=["Dolby Vision", *details.hdr.formats],
                dv_profile=layer.dv_profile,
                dv_compatibility=layer.dv_compatibility,
                dv_dual_layer=True,
            )
    return details


def _dimensions(props: dict[str, Any], info: dict[str, Any]) -> tuple[int | None, int | None]:
    width, height = _int(info.get("Width")), _int(info.get("Height"))
    if width and height:
        return width, height
    pixels = props.get("pixel_dimensions") or ""
    if "x" in pixels:
        w, _, h = pixels.partition("x")
        return _int(w), _int(h)
    return None, None


def _main_video(details: MediaDetails) -> Track | None:
    videos = [t for t in details.of_type("video") if t.codec_id != "V_MJPEG"]
    if not videos:
        return None
    return max(videos, key=lambda t: ((t.width or 0) * (t.height or 0), -t.id))
