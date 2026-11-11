"""Job type: change default/forced flags and track names, in place, with mkvpropedit.

mkvpropedit only rewrites the small header at the start of the file, so this is
quick even for huge films and nothing is copied. Because it changes the
original file, it is only started after the owner confirms a summary, and it
refuses hardlinked files (still seeding) unless the owner said they understand.

Tracks are identified by their unique ID inside the file (``track:=UID``), not
by position, so a file that was replaced since the owner chose the settings
(e.g. Radarr upgraded it) is detected instead of the wrong track being changed.
"""

from __future__ import annotations

import json
import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, field_validator

from ..core.paths import PathNotAllowedError, ensure_inside
from ..media.probe import MediaDetails, Track, describe
from ..media.tools import ToolError, run_tool
from .engine import JobContext, JobFailed, JobType

KIND = "track_settings"
TITLE = "Change track settings"
MAX_NAME_LENGTH = 200
# mkvpropedit normally rewrites the header where it is; at worst it adds a little at the end.
SPACE_NEEDED = 0
SPACE_MARGIN = 50 * 1000**2

_KIND_NAMES = {"video": "Video", "audio": "Audio", "subtitles": "Subtitles"}


class TrackChange(BaseModel):
    """The settings wanted for one track. Fields left out stay as they are."""

    uid: str
    default: bool | None = None
    forced: bool | None = None
    name: str | None = None  # "" removes the name

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())  # no line breaks or tabs in a track name
        if any(unicodedata.category(c) == "Cc" for c in value):
            raise ValueError("Track names can't contain special control characters.")
        if len(value) > MAX_NAME_LENGTH:
            raise ValueError(f"Track names can be at most {MAX_NAME_LENGTH} characters long.")
        return value


@dataclass
class PlannedTrack:
    """The changes for one track, in plain English and as mkvpropedit options."""

    uid: str
    label: str  # "Audio 2: French"
    changes: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)


class TracksChangedError(ValueError):
    pass


def track_label(track: Track, details: MediaDetails) -> str:
    same_kind = details.of_type(track.type)
    number = next(i for i, t in enumerate(same_kind, 1) if t is track)
    label = f"{_KIND_NAMES[track.type]} {number}"
    if track.type != "video" or track.language != "und":
        label += f": {track.language_name}"
    return label


def plan(details: MediaDetails, changes: list[TrackChange]) -> list[PlannedTrack]:
    """Work out what actually needs changing. Settings a track already has are skipped."""
    by_uid = {t.uid: t for t in details.tracks if t.uid}
    planned: list[PlannedTrack] = []
    for change in changes:
        track = by_uid.get(change.uid)
        if track is None:
            raise TracksChangedError(
                "The tracks in this file have changed since you chose these settings "
                "(perhaps Radarr replaced the file). Open the film again and choose again."
            )
        item = PlannedTrack(uid=track.uid, label=track_label(track, details))
        if change.default is not None and change.default != track.default:
            item.changes.append(
                "Make it the default" if change.default else "Stop it being the default"
            )
            item.args += ["--set", f"flag-default={int(change.default)}"]
        if change.forced is not None and change.forced != track.forced:
            item.changes.append(
                "Mark it as forced (shown even when subtitles are off)"
                if change.forced
                else "Remove the forced mark"
            )
            item.args += ["--set", f"flag-forced={int(change.forced)}"]
        if change.name is not None and change.name != track.name:
            if not change.name:
                item.changes.append(f"Remove its name “{track.name}”")
                item.args += ["--delete", "name"]
            else:
                item.changes.append(
                    f"Rename it from “{track.name}” to “{change.name}”"
                    if track.name
                    else f"Name it “{change.name}”"
                )
                item.args += ["--set", f"name={change.name}"]
        if item.changes:
            planned.append(item)
    return planned


def mkvpropedit_args(path: str, planned: list[PlannedTrack]) -> list[str]:
    args = [path]
    for item in planned:
        args += ["--edit", f"track:={item.uid}", *item.args]
    return args


def read_tracks(path: str) -> MediaDetails:
    """Read just the track list (mkvmerge only: quick, and all this job needs)."""
    try:
        result = run_tool("mkvmerge", ["-J", path], timeout=300)
        identified = json.loads(result.stdout)
    except (ToolError, json.JSONDecodeError) as exc:
        raise JobFailed(
            "Tailarr couldn't read the tracks in this file. It may be damaged, still being "
            "copied, or on a disk that isn't available right now.",
            getattr(exc, "details", "") or str(exc),
        ) from exc
    if not identified.get("container", {}).get("recognized", False):
        raise JobFailed("MKVToolNix doesn't recognise this file as an MKV file it can change.")
    return describe({"mkvmerge": identified, "mediainfo": None})


def check_file(path: str, roots: list[str]) -> os.stat_result:
    """The file must be an MKV file inside the library, and still be there."""
    try:
        ensure_inside(path, roots)
    except PathNotAllowedError as exc:
        raise JobFailed(
            "This file isn't inside your Films or TV folder, so Tailarr won't change it.",
            str(exc),
        ) from exc
    if Path(path).suffix.lower() != ".mkv":
        raise JobFailed("Tailarr can only change track settings in MKV files.")
    try:
        return os.stat(path)
    except FileNotFoundError as exc:
        raise JobFailed(
            "This file isn't there any more. It may have been moved, renamed or replaced "
            "(for example by Radarr)."
        ) from exc
    except OSError as exc:
        raise JobFailed(
            "Tailarr couldn't open this file. Check that the disk holding it is available.",
            str(exc),
        ) from exc


HARDLINK_REFUSAL = (
    "This file is also in your downloads folder (it's hardlinked, usually because it's still "
    "seeding). Changing it would also change the seeding copy, so Tailarr didn't touch it. "
    "To go ahead anyway, tick “I understand” before saving."
)


def make_job_type(
    allowed_roots: Callable[[], list[str]], file_changed: Callable[[str], None]
) -> JobType:
    def run(ctx: JobContext) -> str:
        path = ctx.path
        changes = [TrackChange(**c) for c in ctx.params.get("changes", [])]

        ctx.step(1, 3, "Checking the file")
        stat = check_file(path, allowed_roots())
        if stat.st_nlink > 1 and not ctx.params.get("allow_hardlinked", False):
            raise JobFailed(HARDLINK_REFUSAL)
        try:
            planned = plan(read_tracks(path), changes)
        except TracksChangedError as exc:
            raise JobFailed(str(exc)) from exc
        if not planned:
            return "Nothing needed changing: the tracks already had these settings."
        ctx.ensure_free_space(Path(path).parent, SPACE_NEEDED, margin=SPACE_MARGIN)

        # Once mkvpropedit starts it must finish: stopping it halfway could damage the file.
        ctx.step(2, 3, "Saving the changes", cancellable=False)
        try:
            ctx.run_tool("mkvpropedit", mkvpropedit_args(path, planned), cancellable=False)
        except ToolError as exc:
            raise JobFailed(
                "MKVToolNix couldn't save the changes. The file should be as it was before; "
                "open the film to check its tracks.",
                exc.details or exc.message,
            ) from exc

        ctx.step(3, 3, "Checking the result", cancellable=False)
        try:
            leftover = plan(read_tracks(path), changes)
        except TracksChangedError as exc:
            raise JobFailed(
                "After saving, the file's tracks don't look as expected. "
                "Open the film to check its tracks.",
                str(exc),
            ) from exc
        finally:
            file_changed(path)  # show the file as it now is, whatever happened
        if leftover:
            raise JobFailed(
                "The changes were saved, but some settings didn't stick. "
                "Open the film to check its tracks.",
                "\n".join(f"{p.label}: {', '.join(p.changes)}" for p in leftover),
            )
        count = len(planned)
        tracks = f"{count} track{'s' if count != 1 else ''}"
        return f"{tracks} changed. Plex may need a library refresh to notice."

    return JobType(kind=KIND, run=run, in_place=True)
