"""Job type: make a copy of a film without Dolby Vision (an HDR10 copy).

For TVs and players that show Dolby Vision with the wrong colours. The copy is
``<original name> - HDR10.mkv`` next to the original; the original is never
touched. Nothing is re-encoded:

1. ``mkvextract`` takes the video out (with every frame's exact timestamp);
2. ``dovi_tool remove`` strips the Dolby Vision information (and, for UHD
   Blu-ray style profile 7, the enhancement layer), leaving the HDR10 picture;
3. ``mkvmerge`` puts that video back together with every other track,
   chapters, attachments and tags from the original, using the original
   timestamps; ``mkvpropedit`` then sets the same frame rate header;
4. the copy is checked: no Dolby Vision left (MediaInfo), HDR10 (and HDR10+ if
   the original had it) still there, the same tracks and settings, length,
   chapters, attachments, frame rate and every frame's timestamp.

Profile 7 files where the enhancement layer is a separate video track only need
step 3 (that track is left out). Profile 5 is refused: it has no HDR10 picture
underneath, so the copy would show wrong colours (safety rule 8).

Working files go in the work folder (``/work``) when it's mounted, otherwise in
the film's folder; the finished copy is always written next to the original.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from ..core.disk import SAFETY_MARGIN, format_size, free_space
from ..core.permissions import apply_umask
from ..library.naming import is_tailarr_copy
from ..media.probe import MediaDetails, ReadError, Track, describe, read_file
from .engine import JobContext, JobFailed, JobType
from .models import CopyRecord
from .remove_tracks import place_new_file
from .track_settings import check_file, track_label

KIND = "hdr10_copy"
TITLE = "Make a copy without Dolby Vision"
COPY_SUFFIX = " - HDR10"

NO_DV = "This file has no Dolby Vision, so there's nothing to remove."
PROFILE_5 = (
    "This file uses Dolby Vision profile 5, which has no HDR10 picture underneath. "
    "Without Dolby Vision the colours would be wrong (usually green and purple), so "
    "Tailarr won't make a copy without it."
)
CANT_REMOVE = (
    "Tailarr can't safely remove Dolby Vision from this file: players without Dolby Vision "
    "wouldn't show its picture correctly."
)


def output_name(source_name: str) -> str:
    """'Film (2020).mkv' -> 'Film (2020) - HDR10.mkv'."""
    return f"{Path(source_name).stem}{COPY_SUFFIX}.mkv"


class Hdr10Refused(ValueError):
    """Removing Dolby Vision isn't possible or not needed (plain-English reason)."""


@dataclass
class Hdr10Plan:
    source: MediaDetails
    video: Track  # the main (base layer) video track
    remove_rpu: bool  # False: the Dolby Vision layer is a separate track, simply left out
    dropped: list[Track]  # other video tracks left out (Dolby Vision enhancement layers)
    kept_others: list[Track] = field(default_factory=list)  # every track except `video`
    expected_formats: list[str] = field(default_factory=list)  # e.g. ["HDR10+", "HDR10"]

    @property
    def kept(self) -> list[Track]:
        """Every track of the original that the copy has, in order."""
        return [t for t in self.source.tracks if t not in self.dropped]

    @property
    def profile(self) -> str:
        return self.source.hdr.dv_label or "?"


def plan_hdr10(details: MediaDetails) -> Hdr10Plan:
    hdr = details.hdr
    if hdr.dv_profile is None:
        raise Hdr10Refused(NO_DV)
    if hdr.dv_label == "5" or hdr.dv_profile == 5:
        raise Hdr10Refused(PROFILE_5)
    if not hdr.can_remove_dv:
        raise Hdr10Refused(CANT_REMOVE)
    videos = [t for t in details.of_type("video") if t.codec_id != "V_MJPEG"]
    main = max(videos, key=lambda t: ((t.width or 0) * (t.height or 0), -t.id))
    if not main.codec_id.startswith("V_MPEGH"):
        raise Hdr10Refused("Tailarr can only remove Dolby Vision from HEVC (H.265) video.")
    dropped = [t for t in details.of_type("video") if t is not main and t.hdr and t.hdr.dv_profile]
    remove_rpu = bool(main.hdr and main.hdr.dv_profile)
    if not remove_rpu and not dropped:
        raise Hdr10Refused(CANT_REMOVE)  # Dolby Vision found, but not where expected
    return Hdr10Plan(
        source=details,
        video=main,
        remove_rpu=remove_rpu,
        dropped=dropped,
        kept_others=[t for t in details.tracks if t is not main and t not in dropped],
        expected_formats=[f for f in hdr.formats if f != "Dolby Vision"],
    )


@dataclass
class SpaceNeed:
    folder: Path
    label: str  # "the disk with your films", "the work folder"
    needed: int
    free: int

    @property
    def enough(self) -> bool:
        return self.free >= self.needed


def space_needs(source_size: int, film_folder: Path, work: Path | None) -> list[SpaceNeed]:
    """Space for the working files and the copy (each about the size of the film).

    At most two film-sized files exist at once: the taken-out video and the video
    without Dolby Vision, then that and the new copy.
    """
    film_disk = film_folder.stat().st_dev
    if work is None or work.stat().st_dev == film_disk:
        size = 2 * source_size + SAFETY_MARGIN
        return [SpaceNeed(film_folder, "the disk with your films", size, free_space(film_folder))]
    return [
        SpaceNeed(work, "the work folder", 2 * source_size + SAFETY_MARGIN, free_space(work)),
        SpaceNeed(
            film_folder,
            "the disk with your films",
            source_size + SAFETY_MARGIN,
            free_space(film_folder),
        ),
    ]


def usable_work_folder(work_dir: Path) -> Path | None:
    """The work folder, if it's mounted and Tailarr may write there."""
    if work_dir.is_dir() and os.access(work_dir, os.W_OK | os.X_OK):
        return work_dir
    return None


def mkvmerge_args(plan: Hdr10Plan, source: str, video: str, timestamps: str, out: str) -> list[str]:
    """Put the HDR10 video back together with everything else from the original."""
    args = ["-o", out]
    if plan.source.title:
        args += ["--title", plan.source.title]
    if not plan.remove_rpu:
        # The Dolby Vision layer is its own track: copy everything except that track.
        keep_video = [t for t in plan.source.of_type("video") if t not in plan.dropped]
        args += ["--video-tracks", ",".join(str(t.id) for t in keep_video), source]
        return args
    v = plan.video
    args += ["--timestamps", f"0:{timestamps}", "--language", f"0:{v.language}"]
    if v.name:
        args += ["--track-name", f"0:{v.name}"]
    args += ["--default-track-flag", f"0:{int(v.default)}"]
    if v.forced:
        args += ["--forced-display-flag", "0:1"]
    display = v.display_dimensions
    if display:
        args += ["--display-dimensions", f"0:{display}"]
    args.append(video)
    other_video = [t for t in plan.kept_others if t.type == "video"]
    if other_video:
        args += ["--video-tracks", ",".join(str(t.id) for t in other_video)]
    else:
        args.append("--no-video")
    args.append(source)
    return args


def verify_hdr10(copy: MediaDetails, plan: Hdr10Plan) -> list[str]:
    """Everything that's wrong with the new copy (empty when it's right)."""
    problems: list[str] = []
    if copy.hdr.dv_profile is not None or "Dolby Vision" in copy.hdr.formats:
        problems.append("Dolby Vision is still in the copy")
    if not copy.hdr_checked:
        problems.append("MediaInfo couldn't read the copy")
    missing = [f for f in plan.expected_formats if f not in copy.hdr.formats]
    if missing:
        problems.append(f"HDR lost: {', '.join(missing)} (found {copy.hdr.formats or 'none'})")
    videos = [t for t in copy.of_type("video") if t.codec_id != "V_MJPEG"]
    if not videos:
        problems.append("The copy has no video")
        return problems
    new_video = max(videos, key=lambda t: (t.width or 0) * (t.height or 0))
    src = plan.video
    if (new_video.width, new_video.height) != (src.width, src.height):
        problems.append(
            f"Picture size {new_video.width}x{new_video.height}, expected {src.width}x{src.height}"
        )
    if (new_video.language, new_video.name, new_video.default) != (
        src.language,
        src.name,
        src.default,
    ):
        problems.append("The video track's language, name or default setting changed")
    if plan.remove_rpu:
        # The new video is a new track (new ID); every other track is the original's.
        got, want = copy.tracks[1:], plan.kept_others
    else:
        got, want = copy.tracks, plan.kept
    if [t.uid for t in got] != [t.uid for t in want]:
        problems.append(f"Tracks: expected {[t.uid for t in want]}, found {[t.uid for t in got]}")
    else:
        for track, expected in zip(got, want, strict=True):
            settings = (track.default, track.forced, track.name, track.language)
            wanted = (expected.default, expected.forced, expected.name, expected.language)
            if settings != wanted:
                problems.append(f"{track_label(expected, plan.source)}: settings changed")
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


def read_full(path: str) -> MediaDetails:
    """Tracks (mkvmerge) and HDR (MediaInfo): both are needed to check Dolby Vision."""
    try:
        return describe(read_file(path))
    except ReadError as exc:
        raise JobFailed(exc.message, exc.details) from exc


def make_job_type(
    engine: Engine,
    allowed_roots: Callable[[], list[str]],
    work_dir: Callable[[], Path],
    folder_changed: Callable[[str], None],
) -> JobType:
    def run(ctx: JobContext) -> str:
        source = ctx.path
        overwrite = bool(ctx.params.get("overwrite", False))
        film_folder = Path(source).parent
        steps = 6

        ctx.step(1, steps, "Checking the file")
        before = check_file(source, allowed_roots())
        details = read_full(source)
        try:
            plan = plan_hdr10(details)
        except Hdr10Refused as exc:
            raise JobFailed(str(exc)) from exc
        final = film_folder / output_name(Path(source).name)
        if final.exists():
            if not is_tailarr_copy(final.name):
                raise JobFailed(
                    f"A file called “{final.name}” is already there and it isn't a "
                    "copy made by Tailarr, so Tailarr won't replace it."
                )
            if not overwrite:
                raise JobFailed(
                    f"A copy called “{final.name}” already exists. To replace it, "
                    "start again and tick “Replace the existing copy”."
                )
        work = usable_work_folder(work_dir())
        for need in space_needs(before.st_size, film_folder, work):
            if not need.enough:
                raise JobFailed(
                    f"Not enough free space on {need.label}: needs {format_size(need.needed)}, "
                    f"{format_size(need.free)} free. Free up some space and try again."
                )
        scratch = work or film_folder

        timestamps = ctx.temp_path(scratch, ".txt")
        video = ctx.temp_path(scratch, ".hevc")
        clean = ctx.temp_path(scratch, ".hevc")
        if plan.remove_rpu:
            ctx.step(2, steps, "Taking out the video")
            ctx.run_tool(
                "mkvextract",
                [
                    source,
                    "tracks",
                    f"{plan.video.id}:{video}",
                    "timestamps_v2",
                    f"{plan.video.id}:{timestamps}",
                ],
            )
            ctx.step(3, steps, "Removing Dolby Vision")
            ctx.run_tool("dovi_tool", ["remove", "-i", str(video), "-o", str(clean)])
            ctx.discard(video)  # no longer needed: frees a film's worth of space

        ctx.step(4, steps, "Making the HDR10 copy")
        out = ctx.temp_path(film_folder)
        ctx.run_tool("mkvmerge", mkvmerge_args(plan, source, str(clean), str(timestamps), str(out)))
        ctx.discard(clean)
        if plan.remove_rpu and plan.video.default_duration:
            ctx.run_tool(
                "mkvpropedit",
                [
                    str(out),
                    "--edit",
                    "track:v1",
                    "--set",
                    f"default-duration={plan.video.default_duration}",
                ],
            )

        ctx.step(5, steps, "Checking the copy")
        problems = verify_hdr10(read_full(str(out)), plan)
        if plan.remove_rpu and not problems:
            # Every frame must be shown at exactly the same moment as in the original.
            copied = ctx.temp_path(scratch, ".txt")
            ctx.run_tool("mkvextract", [str(out), "timestamps_v2", f"0:{copied}"])
            if Path(copied).read_bytes() != Path(timestamps).read_bytes():
                problems.append("Frame timing differs from the original")
        if problems:
            raise JobFailed(
                "The HDR10 copy didn't come out as expected, so it was thrown away. "
                "Your original wasn't changed.",
                "\n".join(problems),
            )
        after = os.stat(source)
        if (after.st_size, after.st_mtime) != (before.st_size, before.st_mtime):
            raise JobFailed(
                "The original file changed while the copy was being made (perhaps Radarr "
                "replaced it), so the copy was thrown away. Try again."
            )

        ctx.step(6, steps, "Saving the copy", cancellable=False)
        try:
            place_new_file(out, final, overwrite=overwrite)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise JobFailed("The disk filled up while saving the copy.", str(exc)) from exc
            raise
        apply_umask(final)
        with Session(engine) as session:
            existing = session.get(CopyRecord, str(final))
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
        folder_changed(str(film_folder))

        ctx.result = {"copy": final.name, "source": Path(source).name}
        shows = " and ".join(plan.expected_formats) or "HDR10"
        return (
            f"HDR10 copy saved as “{final.name}”. Players without Dolby Vision show it "
            f"as {shows}. Your original wasn't changed."
        )

    return JobType(kind=KIND, run=run)
