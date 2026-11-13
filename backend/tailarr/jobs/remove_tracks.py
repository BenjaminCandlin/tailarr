"""Job type: save a copy of a film without some audio/subtitle tracks.

The copy is written by ``mkvmerge`` (a remux: nothing is re-encoded) next to the
original as ``<original name> - Tailarr.mkv``. Everything else comes across:
video, the kept tracks with their names/languages/flags, chapters,
attachments and tags. Track setting changes the owner made on the page
(default/forced/names) are applied to the copy too.

The copy is written to a hidden temporary file, checked (readable, exactly the
expected tracks in order with the expected settings, same length, same
chapters and attachments), and only then given its real name. The original is
never touched. An existing file with the copy's name is only replaced when the
owner said so, and only if it is one of Tailarr's own copies.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from ..core.permissions import apply_umask
from ..media.probe import MediaDetails, Track
from .engine import JobContext, JobFailed, JobType
from .models import CopyRecord, is_copy
from .track_settings import (
    TrackChange,
    TracksChangedError,
    check_file,
    read_tracks,
    track_label,
)

KIND = "remove_tracks"
TITLE = "Save a copy without some tracks"
COPY_SUFFIX = " - Tailarr"


class CopyRefusedError(ValueError):
    """The requested copy doesn't make sense (plain-English reason)."""


def output_name(source_name: str) -> str:
    """'Film (2020).mkv' -> 'Film (2020) - Tailarr.mkv'.

    A copy made from one of Tailarr's own '- Tailarr' copies updates that copy instead
    of piling up '- Tailarr - Tailarr' names.
    """
    stem = Path(source_name).stem
    if stem.endswith(COPY_SUFFIX):
        return f"{stem}.mkv"
    return f"{stem}{COPY_SUFFIX}.mkv"


@dataclass
class Wanted:
    default: bool
    forced: bool
    name: str


@dataclass
class CopyPlan:
    source: MediaDetails
    removed: list[Track]
    kept: list[Track]
    changes: dict[str, TrackChange]  # by uid, kept tracks only
    warnings: list[str] = field(default_factory=list)

    def wanted(self, track: Track) -> Wanted:
        change = self.changes.get(track.uid)
        if change is None:
            return Wanted(track.default, track.forced, track.name)
        return Wanted(
            track.default if change.default is None else change.default,
            track.forced if change.forced is None else change.forced,
            track.name if change.name is None else change.name,
        )

    def setting_changes(self) -> list[tuple[Track, list[str]]]:
        """The kept tracks whose settings change, with each change in plain English."""
        out = []
        for track in self.kept:
            want = self.wanted(track)
            lines = []
            if want.default != track.default:
                lines.append("Make it the default" if want.default else "Stop it being the default")
            if want.forced != track.forced:
                lines.append(
                    "Mark it as forced (shown even when subtitles are off)"
                    if want.forced
                    else "Remove the forced mark"
                )
            if want.name != track.name:
                if not want.name:
                    lines.append(f"Remove its name “{track.name}”")
                elif track.name:
                    lines.append(f"Rename it from “{track.name}” to “{want.name}”")
                else:
                    lines.append(f"Name it “{want.name}”")
            if lines:
                out.append((track, lines))
        return out

    def mkvmerge_options(self, skip: frozenset[int] = frozenset()) -> list[str]:
        """Which tracks to copy and their settings (track numbers as mkvmerge counts them).

        Tracks in `skip` (by mkvmerge number) get no setting options: the HDR10 copy brings
        its video in from a separate file and sets that track's options itself.
        """
        options: list[str] = []
        for kind, keep, none in (
            ("audio", "--audio-tracks", "--no-audio"),
            ("subtitles", "--subtitle-tracks", "--no-subtitles"),
        ):
            if not any(t.type == kind for t in self.removed):
                continue  # nothing of this kind removed: copy them all
            ids = [str(t.id) for t in self.kept if t.type == kind]
            options += [keep, ",".join(ids)] if ids else [none]
        for track in self.kept:
            if track.id in skip:
                continue
            want = self.wanted(track)
            if want.default != track.default:
                options += ["--default-track-flag", f"{track.id}:{int(want.default)}"]
            if want.forced != track.forced:
                options += ["--forced-display-flag", f"{track.id}:{int(want.forced)}"]
            if want.name != track.name:
                options += ["--track-name", f"{track.id}:{want.name}"]
        return options


def plan_copy(
    details: MediaDetails,
    remove: list[str],
    changes: list[TrackChange],
    *,
    require_removal: bool = True,
) -> CopyPlan:
    """Check the choices for a copy. `require_removal=False`: copies that only change
    settings (or only remove Dolby Vision) are fine too."""
    by_uid = {t.uid: t for t in details.tracks if t.uid}
    missing = [uid for uid in [*remove, *(c.uid for c in changes)] if uid not in by_uid]
    if missing:
        raise TracksChangedError(
            "The tracks in this file have changed since you chose them "
            "(perhaps Radarr replaced the file). Open the film again and choose again."
        )
    removing = set(remove)
    if not removing and require_removal:
        raise CopyRefusedError("Untick at least one track to leave out of the copy.")
    if any(by_uid[uid].type == "video" for uid in removing):
        raise CopyRefusedError("Video tracks can't be removed, only audio and subtitle tracks.")
    removed = [t for t in details.tracks if t.uid in removing]
    kept = [t for t in details.tracks if t.uid not in removing]
    if details.of_type("audio") and not any(t.type == "audio" for t in kept):
        raise CopyRefusedError("Keep at least one audio track, or the copy would have no sound.")
    plan = CopyPlan(
        source=details,
        removed=removed,
        kept=kept,
        changes={c.uid: c for c in changes if c.uid not in removing},
    )
    kept_audio = [t for t in kept if t.type == "audio"]
    if any(t.default for t in details.of_type("audio")) and not any(
        plan.wanted(t).default for t in kept_audio
    ):
        plan.warnings.append(
            "None of the audio tracks left is marked as the default, so most players "
            "will play the first one."
        )
    kept_subs = [t for t in kept if t.type == "subtitles"]
    if any(t.default for t in removed if t.type == "subtitles") and not any(
        plan.wanted(t).default for t in kept_subs
    ):
        plan.warnings.append(
            "The subtitles that were shown automatically are being removed, so no "
            "subtitles will show unless you choose some."
        )
    return plan


def describe_track(track: Track, details: MediaDetails) -> str:
    """'Audio 3: Japanese – AAC, Stereo, “Japanese”'."""
    parts = [track.codec]
    if track.type == "subtitles":
        parts = [f"{track.codec} ({'picture-based' if track.picture_based else 'text'})"]
    if track.channel_layout:
        parts.append(track.channel_layout)
    if track.name:
        parts.append(f"“{track.name}”")
    return f"{track_label(track, details)} – {', '.join(p for p in parts if p)}"


def verify_copy(copy: MediaDetails, plan: CopyPlan) -> list[str]:
    """Everything that's wrong with the new copy (empty when it's right)."""
    problems: list[str] = []
    expected = [t.uid for t in plan.kept]
    got = [t.uid for t in copy.tracks]
    if got != expected:
        problems.append(f"Tracks: expected {expected}, found {got}")
        return problems
    for want_track, track in zip(plan.kept, copy.tracks, strict=True):
        want = plan.wanted(want_track)
        label = track_label(want_track, plan.source)
        if (track.type, track.codec_id) != (want_track.type, want_track.codec_id):
            problems.append(f"{label}: different kind of track")
        if (track.default, track.forced, track.name) != (want.default, want.forced, want.name):
            problems.append(
                f"{label}: default={track.default} forced={track.forced} name={track.name!r}, "
                f"expected default={want.default} forced={want.forced} name={want.name!r}"
            )
    source_length, copy_length = plan.source.duration, copy.duration
    if source_length and copy_length is not None:
        if abs(source_length - copy_length) > max(1.0, source_length * 0.001):
            problems.append(f"Length: {copy_length:.3f} s, expected {source_length:.3f} s")
    elif source_length:
        problems.append("Length: unknown")
    if copy.chapters != plan.source.chapters:
        problems.append(f"Chapters: {copy.chapters}, expected {plan.source.chapters}")
    if len(copy.attachments) != len(plan.source.attachments):
        problems.append(
            f"Attachments: {len(copy.attachments)}, expected {len(plan.source.attachments)}"
        )
    return problems


def place_new_file(temp: Path, final: Path, *, overwrite: bool) -> None:
    """Give the finished temporary file its real name.

    Without `overwrite`, an existing file is never replaced, even one that appeared a
    moment ago: a hardlink fails if the name is taken, unlike a rename.
    """
    if overwrite:
        os.replace(temp, final)
        return
    try:
        os.link(temp, final)
    except FileExistsError as exc:
        raise JobFailed(
            f"A file called “{final.name}” appeared while the copy was being made, "
            "so Tailarr didn't replace it."
        ) from exc
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EMLINK):
            raise
        # A disk that doesn't support hardlinks: check, then rename.
        if final.exists():
            raise JobFailed(
                f"A file called “{final.name}” already exists, so Tailarr didn't replace it."
            ) from exc
        os.rename(temp, final)
        return
    os.unlink(temp)


def make_job_type(
    engine: Engine,
    allowed_roots: Callable[[], list[str]],
    folder_changed: Callable[[str], None],
) -> JobType:
    def run(ctx: JobContext) -> str:
        source = ctx.path
        remove = list(ctx.params.get("remove", []))
        changes = [TrackChange(**c) for c in ctx.params.get("changes", [])]
        overwrite = bool(ctx.params.get("overwrite", False))
        folder = Path(source).parent

        ctx.step(1, 4, "Checking the file")
        before = check_file(source, allowed_roots())
        details = read_tracks(source)
        try:
            plan = plan_copy(
                details, remove, changes, require_removal=not ctx.params.get("update_copy")
            )
        except (TracksChangedError, CopyRefusedError) as exc:
            raise JobFailed(str(exc)) from exc
        final = folder / output_name(Path(source).name)
        if ctx.params.get("update_copy") and is_copy(engine, source):
            # Batch "also change copies": update one of Tailarr's copies where it is.
            final, overwrite = Path(source), True
        updating_copy = final == Path(source)
        if final.exists():
            if not is_copy(engine, final):
                raise JobFailed(
                    f"A file called “{final.name}” is already there and it isn't a "
                    "copy made by Tailarr, so Tailarr won't replace it."
                )
            if not overwrite:
                raise JobFailed(
                    f"A copy called “{final.name}” already exists. To replace it, "
                    "start again and tick “Replace the existing copy”."
                )
        # The copy is at most as big as the original.
        ctx.ensure_free_space(folder, before.st_size)

        ctx.step(2, 4, "Making the copy")
        temp = ctx.temp_path(folder)
        ctx.run_tool("mkvmerge", ["-o", str(temp), *plan.mkvmerge_options(), source])

        ctx.step(3, 4, "Checking the copy")
        problems = verify_copy(read_tracks(str(temp)), plan)
        if problems:
            raise JobFailed(
                "The copy didn't come out as expected, so it was thrown away. "
                "Your original wasn't changed.",
                "\n".join(problems),
            )
        after = os.stat(source)
        if (after.st_size, after.st_mtime) != (before.st_size, before.st_mtime):
            raise JobFailed(
                "The original file changed while the copy was being made (perhaps Radarr "
                "replaced it), so the copy was thrown away. Try again."
            )

        ctx.step(4, 4, "Saving the copy", cancellable=False)
        place_new_file(temp, final, overwrite=overwrite)
        apply_umask(final)
        with Session(engine) as session:
            existing = session.get(CopyRecord, str(final))
            # A copy that was updated is still a copy of the same original: keep its record.
            if not updating_copy:
                if existing is not None:
                    session.delete(existing)
                    session.flush()
                session.add(
                    CopyRecord(
                        path=str(final),
                        source_path=source,
                        source_size=before.st_size,
                        source_mtime=before.st_mtime,
                        kind=KIND,
                        created_at=os.stat(final).st_mtime,
                        job_id=ctx.job_id,
                    )
                )
            session.commit()
        folder_changed(str(folder))

        ctx.result = {"copy": final.name, "source": Path(source).name}
        count = len(plan.removed)
        removed = f"{count} track{'s' if count != 1 else ''} left out"
        where = "updated" if updating_copy else "saved"
        return f"Copy {where} as “{final.name}” ({removed}). Your original wasn't changed."

    return JobType(kind=KIND, run=run)
