"""Turning a rule-like choice into what would happen to one file.

Track numbers differ from file to file, so batch actions (a whole TV season or
show) and automatic rules don't pick tracks by number. They describe what's
wanted ("keep only English subtitles", "make Dolby Vision files into HDR10
copies"), and :func:`plan_file` works out, for each file, which tracks that means
and whether there's anything to do at all. Nothing is changed here: the result
says which job to queue, with its exact settings, or why the file is skipped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.disk import SAFETY_MARGIN
from ..jobs import hdr10_copy, remove_tracks, track_settings
from ..jobs.track_settings import TrackChange
from ..library.naming import is_tailarr_copy
from ..media.languages import language_name, normalize_language
from ..media.probe import MediaDetails, Track

# -- what the owner can choose ------------------------------------------------------------


class LanguageChoice(BaseModel):
    """Which tracks of one kind (audio or subtitles) to keep."""

    mode: Literal["all", "only", "none"] = "all"  # "none": remove them all (subtitles only)
    languages: list[str] = []  # language codes such as "eng", kept with mode "only"
    keep_unknown: bool = True  # keep tracks with no language set
    keep_original: bool = True  # keep tracks marked as the original language (audio)

    @field_validator("languages")
    @classmethod
    def _codes(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_language(code) for code in value if code.strip()))

    @model_validator(mode="after")
    def _some_language(self) -> LanguageChoice:
        if self.mode == "only" and not self.languages:
            raise ValueError("Choose at least one language to keep.")
        return self


class Hdr10CopyAction(BaseModel):
    """Make a copy without Dolby Vision of every file that has it (not profile 5)."""

    type: Literal["hdr10_copy"] = "hdr10_copy"
    overwrite: bool = False  # replace HDR10 copies Tailarr made before


class RemoveTracksAction(BaseModel):
    """Save a copy without the audio/subtitle tracks that don't match the choices."""

    type: Literal["remove_tracks"] = "remove_tracks"
    audio: LanguageChoice = LanguageChoice()
    subtitles: LanguageChoice = LanguageChoice()
    remove_commentary: bool = False
    overwrite: bool = False  # replace "- Tailarr" copies made before

    @model_validator(mode="after")
    def _sensible(self) -> RemoveTracksAction:
        if self.audio.mode == "none":
            raise ValueError(
                "Every file needs at least one audio track, so audio can't be removed."
            )
        if self.audio.mode == "all" and self.subtitles.mode == "all" and not self.remove_commentary:
            raise ValueError("Choose which audio or subtitle tracks to remove.")
        return self


class DefaultTracksAction(BaseModel):
    """Choose the default audio and subtitles (changes the original files in place)."""

    type: Literal["default_tracks"] = "default_tracks"
    audio_language: str | None = None  # make the first audio track in this language the default
    subtitles: Literal["keep", "off", "language"] = "keep"
    subtitle_language: str | None = None

    @field_validator("audio_language", "subtitle_language")
    @classmethod
    def _code(cls, value: str | None) -> str | None:
        return normalize_language(value) if value and value.strip() else None

    @model_validator(mode="after")
    def _sensible(self) -> DefaultTracksAction:
        if self.subtitles == "language" and not self.subtitle_language:
            raise ValueError("Choose the subtitle language to show by default.")
        if self.audio_language is None and self.subtitles == "keep":
            raise ValueError("Choose a default audio language or default subtitles.")
        return self


Action = Annotated[
    Hdr10CopyAction | RemoveTracksAction | DefaultTracksAction, Field(discriminator="type")
]


# -- describing choices in plain English ----------------------------------------------------


def _languages(codes: list[str]) -> str:
    names = [language_name(code) for code in codes]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def describe_action(action: Hdr10CopyAction | RemoveTracksAction | DefaultTracksAction) -> str:
    """One line, e.g. 'Save copies keeping only English subtitles'."""
    if isinstance(action, Hdr10CopyAction):
        return "Make a copy without Dolby Vision (HDR10 copy)"
    if isinstance(action, RemoveTracksAction):
        parts = []
        if action.audio.mode == "only":
            parts.append(f"only {_languages(action.audio.languages)} audio")
        if action.subtitles.mode == "only":
            parts.append(f"only {_languages(action.subtitles.languages)} subtitles")
        text = "Save a copy keeping " + " and ".join(parts) if parts else "Save a copy"
        extra = []
        if action.subtitles.mode == "none":
            extra.append("no subtitles")
        if action.remove_commentary:
            extra.append("no commentary tracks")
        if extra:
            text += " with " + " and ".join(extra)
        return text
    parts = []
    if action.audio_language:
        parts.append(f"{language_name(action.audio_language)} audio")
    if action.subtitles == "off":
        parts.append("no subtitles shown")
    elif action.subtitles == "language" and action.subtitle_language:
        parts.append(f"{language_name(action.subtitle_language)} subtitles")
    return "Make the default " + " and ".join(parts) if parts else "Change default tracks"


def changes_originals(action: Hdr10CopyAction | RemoveTracksAction | DefaultTracksAction) -> bool:
    return isinstance(action, DefaultTracksAction)


# -- what would happen to one file ----------------------------------------------------------


@dataclass
class FilePlan:
    path: str
    name: str
    will_run: bool
    lines: list[str] = field(default_factory=list)  # what happens, in plain English
    reason: str | None = None  # why it's skipped
    job_kind: str | None = None
    job_title: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    changes_original: bool = False
    hardlinked: bool = False
    new_file: str | None = None
    # Space this job needs while it runs: (folder, bytes) on the film's disk, and in the
    # work folder (HDR10 copies only), plus what's left behind (the copy itself).
    space_needed: int = 0
    work_needed: int = 0


def _skip(path: str, reason: str, **extra: Any) -> FilePlan:
    return FilePlan(path=path, name=Path(path).name, will_run=False, reason=reason, **extra)


def _is_commentary(track: Track) -> bool:
    return track.commentary or "commentary" in track.name.casefold()


def _keeps(choice: LanguageChoice, track: Track) -> bool:
    if choice.mode == "all":
        return True
    if choice.mode == "none":
        return False
    language = normalize_language(track.language)
    if language in choice.languages:
        return True
    if choice.keep_unknown and language in ("und", "zxx", "mul", "mis"):
        return True
    return bool(choice.keep_original and track.original)


def _existing_copy(final: Path, overwrite: bool) -> str | None:
    if not final.exists():
        return None
    if not is_tailarr_copy(final.name):
        return f"A file called “{final.name}” is already there and it isn't a Tailarr copy."
    if not overwrite:
        return f"A copy called “{final.name}” already exists."
    return None


def _plan_remove(
    action: RemoveTracksAction, path: str, details: MediaDetails, size: int
) -> FilePlan:
    choices = {"audio": action.audio, "subtitles": action.subtitles}
    remove = [
        track
        for track in details.tracks
        if track.type in choices
        and (
            not _keeps(choices[track.type], track)
            or (action.remove_commentary and _is_commentary(track))
        )
    ]
    if not remove:
        return _skip(path, "Nothing to remove: every track is one you want to keep.")
    try:
        plan = remove_tracks.plan_copy(details, [t.uid for t in remove], [])
    except remove_tracks.CopyRefusedError as error:
        return _skip(path, str(error))
    final = Path(path).with_name(remove_tracks.output_name(Path(path).name))
    problem = _existing_copy(final, action.overwrite)
    if problem:
        return _skip(path, problem)
    lines = [f"Leave out {remove_tracks.describe_track(t, details)}" for t in plan.removed]
    lines += plan.warnings
    return FilePlan(
        path=path,
        name=Path(path).name,
        will_run=True,
        lines=lines,
        job_kind=remove_tracks.KIND,
        job_title=remove_tracks.TITLE,
        params={
            "remove": [t.uid for t in plan.removed],
            "changes": [],
            "overwrite": action.overwrite,
        },
        new_file=final.name,
        space_needed=size,
    )


def _plan_hdr10(action: Hdr10CopyAction, path: str, details: MediaDetails, size: int) -> FilePlan:
    if not details.hdr_checked:
        return _skip(path, "MediaInfo couldn't read this file, so its HDR wasn't checked.")
    try:
        plan = hdr10_copy.plan_hdr10(details)
    except hdr10_copy.Hdr10Refused as error:
        return _skip(path, str(error))
    final = Path(path).with_name(hdr10_copy.output_name(Path(path).name))
    problem = _existing_copy(final, action.overwrite)
    if problem:
        return _skip(path, problem)
    shows = " and ".join(plan.expected_formats) or "HDR10"
    lines = [f"Copy without Dolby Vision profile {plan.profile}: players show it as {shows}"]
    return FilePlan(
        path=path,
        name=Path(path).name,
        will_run=True,
        lines=lines,
        job_kind=hdr10_copy.KIND,
        job_title=hdr10_copy.TITLE,
        params={"overwrite": action.overwrite},
        new_file=final.name,
        space_needed=size,
        work_needed=2 * size,
    )


def _first(tracks: list[Track], language: str) -> Track | None:
    matching = [t for t in tracks if normalize_language(t.language) == language]
    # Prefer ordinary tracks over commentary, audio description and hearing-impaired ones.
    matching.sort(key=lambda t: (_is_commentary(t), t.visual_impaired, t.hearing_impaired))
    return matching[0] if matching else None


def default_track_changes(
    action: DefaultTracksAction, details: MediaDetails
) -> tuple[list[TrackChange], list[str]]:
    """The track changes the action means for this file, and notes about parts not possible."""
    wanted: dict[str, bool] = {}
    notes: list[str] = []
    if action.audio_language:
        audio = details.of_type("audio")
        target = _first(audio, action.audio_language)
        if target is None:
            notes.append(f"No {language_name(action.audio_language)} audio track.")
        else:
            for track in audio:
                wanted[track.uid] = track is target
    subs = details.of_type("subtitles")
    if action.subtitles == "off":
        for track in subs:
            wanted[track.uid] = False
    elif action.subtitles == "language" and action.subtitle_language:
        target = _first([t for t in subs if not t.forced], action.subtitle_language)
        if target is None:
            notes.append(f"No {language_name(action.subtitle_language)} subtitles.")
        else:
            for track in subs:
                wanted[track.uid] = track is target
    changes = [
        TrackChange(uid=t.uid, default=wanted[t.uid])
        for t in details.tracks
        if t.uid in wanted and wanted[t.uid] != t.default
    ]
    return changes, notes


def _plan_defaults(
    action: DefaultTracksAction,
    path: str,
    details: MediaDetails,
    links: int,
    allow_hardlinked: bool,
) -> FilePlan:
    changes, notes = default_track_changes(action, details)
    planned = track_settings.plan(details, changes)
    if not planned:
        reason = " ".join(notes) or "Already set up like this."
        return _skip(path, reason)
    if links > 1 and not allow_hardlinked:
        return _skip(
            path,
            "Also in your downloads (still seeding), so it's only changed if you tick "
            "“I understand” for seeding files.",
            hardlinked=True,
            changes_original=True,
        )
    lines = [f"{p.label}: {', '.join(p.changes)}" for p in planned] + notes
    return FilePlan(
        path=path,
        name=Path(path).name,
        will_run=True,
        lines=lines,
        job_kind=track_settings.KIND,
        job_title=track_settings.TITLE,
        params={
            "changes": [c.model_dump(exclude_none=True) for c in changes],
            "allow_hardlinked": allow_hardlinked,
        },
        changes_original=True,
        hardlinked=links > 1,
    )


def plan_file(
    action: Hdr10CopyAction | RemoveTracksAction | DefaultTracksAction,
    path: str,
    details: MediaDetails | None,
    *,
    is_copy: bool = False,
    allow_hardlinked: bool = False,
    read_error: str | None = None,
) -> FilePlan:
    """What `action` would do to the file at `path`. Changes nothing."""
    if is_copy:
        return _skip(path, "This is a copy Tailarr made; actions apply to original files.")
    if not path.lower().endswith(".mkv"):
        return _skip(path, "Not an MKV file, so Tailarr can't change it.")
    if details is None:
        return _skip(path, read_error or "Tailarr couldn't read this file.")
    try:
        stat = os.stat(path)
    except OSError:
        return _skip(path, "This file can't be opened any more.")
    if isinstance(action, Hdr10CopyAction):
        return _plan_hdr10(action, path, details, stat.st_size)
    if isinstance(action, RemoveTracksAction):
        return _plan_remove(action, path, details, stat.st_size)
    return _plan_defaults(action, path, details, stat.st_nlink, allow_hardlinked)


# -- disk space for many jobs ---------------------------------------------------------------


@dataclass
class SpaceTotal:
    label: str
    folder: str
    needed: int
    free: int

    @property
    def enough(self) -> bool:
        return self.free >= self.needed


def space_totals(plans: list[FilePlan], work: Path | None) -> list[SpaceTotal]:
    """Space all the jobs need together, per disk.

    Copies stay, so their sizes add up; working files (HDR10 copies) are removed after
    each job, and jobs run one at a time, so only the biggest one counts. Each job also
    checks again just before it starts.
    """
    from ..core.disk import free_space

    by_disk: dict[int, SpaceTotal] = {}
    working: dict[int, int] = {}

    def add(folder: Path, label: str, copies: int, work_bytes: int) -> None:
        try:
            device = folder.stat().st_dev
        except OSError:
            return
        total = by_disk.get(device)
        if total is None:
            total = by_disk[device] = SpaceTotal(label, str(folder), 0, free_space(folder))
        total.needed += copies
        working[device] = max(working.get(device, 0), work_bytes)

    for plan in plans:
        if not plan.will_run or not (plan.space_needed or plan.work_needed):
            continue
        folder = Path(plan.path).parent
        if plan.work_needed and work is not None:
            add(folder, "the disk with your files", plan.space_needed, 0)
            add(work, "the work folder", 0, plan.work_needed)
        else:
            add(folder, "the disk with your files", plan.space_needed, plan.work_needed)
    for device, total in by_disk.items():
        total.needed += working.get(device, 0) + SAFETY_MARGIN
    return list(by_disk.values())
