"""Job type: replace an original file with a copy Tailarr made from it.

Two instant renames on the same disk, nothing copied:

1. the original moves into the hidden recycle folder in the film's folder
   (deleted after the keep period, 30 days by default);
2. the copy takes the original's exact name, so Radarr and Plex still find
   "their" file.

Only allowed for a copy Tailarr has a record of making *from this original*,
and only if the original hasn't changed since (e.g. Radarr upgraded it). If the
second rename fails, the original is put straight back.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from ..core.settings_store import get_recycle_settings
from .engine import JobContext, JobFailed, JobType
from .models import CopyRecord, RecycledFile
from .recycle import move_to_recycle
from .track_settings import check_file, read_tracks

KIND = "replace_original"
TITLE = "Replace the original with a copy"

NO_RECORD = (
    "Tailarr has no record of making this copy from this file, so it won't use it to "
    "replace the original."
)
# Only copies without some tracks can replace their original. An HDR10 copy has no Dolby
# Vision, so replacing a Dolby Vision original with it would lose that for good.
REPLACEABLE_KIND = "remove_tracks"
NOT_REPLACEABLE = (
    "Only copies made with \u201cSave a copy without the unticked tracks\u201d can replace "
    "their original. An HDR10 copy is meant to sit next to the original, so Dolby Vision "
    "TVs can still play the original."
)
ORIGINAL_CHANGED = (
    "The original file has changed since this copy was made (perhaps Radarr upgraded it), "
    "so the copy may be out of date. Nothing was changed. Make a new copy from the current "
    "file if you still want one."
)
INTERRUPTED = (
    "Tailarr was stopped or restarted while it was swapping the files. Open the film to "
    "check which files are there; the original is either in its usual place or in the "
    "hidden .tailarr-recycle folder inside the film's folder."
)


def check_copy_record(engine: Engine, original: str, copy: str) -> CopyRecord:
    """The copy must be one Tailarr made from this original, unchanged since."""
    with Session(engine) as session:
        record = session.get(CopyRecord, copy)
    if record is None or record.source_path != original:
        raise JobFailed(NO_RECORD)
    if record.kind != REPLACEABLE_KIND:
        raise JobFailed(NOT_REPLACEABLE)
    stat = os.stat(original)
    if (stat.st_size, stat.st_mtime) != (record.source_size, record.source_mtime):
        raise JobFailed(ORIGINAL_CHANGED)
    return record


def make_job_type(
    engine: Engine,
    allowed_roots: Callable[[], list[str]],
    folder_changed: Callable[[str], None],
) -> JobType:
    def run(ctx: JobContext) -> str:
        original = ctx.path
        copy = str(ctx.params["copy"])
        roots = allowed_roots()

        ctx.step(1, 3, "Checking the files")
        check_file(original, roots)
        check_file(copy, roots)
        if Path(copy).parent != Path(original).parent:
            raise JobFailed("The copy and the original must be in the same folder.")
        check_copy_record(engine, original, copy)
        read_tracks(copy)  # the copy must still be a readable MKV file

        # From here on, both steps are instant renames that mustn't be interrupted.
        ctx.step(2, 3, "Moving the original to the recycle folder", cancellable=False)
        with Session(engine) as session:
            try:
                recycled = move_to_recycle(session, original, ctx.job_id)
            except OSError as exc:
                raise JobFailed(
                    "Tailarr couldn't move the original into the recycle folder, so nothing "
                    "was changed.",
                    str(exc),
                ) from exc
            recycled_path = recycled.path
            keep_days = get_recycle_settings(session).keep_days

            ctx.step(3, 3, "Putting the copy in its place", cancellable=False)
            try:
                os.rename(copy, original)
            except OSError as exc:
                os.rename(recycled_path, original)  # put the original back
                session.delete(session.get(RecycledFile, recycled.id))
                session.commit()
                raise JobFailed(
                    "Tailarr couldn't give the copy the original's name, so the original was "
                    "put back. Nothing was changed.",
                    str(exc),
                ) from exc
            record = session.get(CopyRecord, copy)
            if record is not None:
                session.delete(record)
            session.commit()

        folder_changed(str(Path(original).parent))
        ctx.result = {"file": Path(original).name, "recycled": recycled_path}
        return (
            f"The original was replaced with the copy. The old file is kept in the recycle "
            f"folder for {keep_days} days, then deleted."
        )

    return JobType(kind=KIND, run=run, in_place=True, interrupted_message=INTERRUPTED)
