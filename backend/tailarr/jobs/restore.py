"""Job type: put a file back from the recycle folder.

Replaced originals (and stale copies tidied after a Radarr/Sonarr upgrade) wait in a
hidden ``.tailarr-recycle`` folder inside their own folder. Restoring renames the file
back to where it was: instant, on the same disk, nothing copied.

If a file with that name is there now (usually the copy that replaced it), Tailarr
refuses unless the owner chose to swap: then the current file moves to the recycle
folder first, the same way "Replace the original" does, so nothing is ever lost.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from ..connections.service import record_activity
from ..core.paths import is_inside
from ..core.settings_store import get_recycle_settings
from .engine import JobContext, JobFailed, JobType
from .models import RecycledFile
from .recycle import RECYCLE_FOLDER, move_to_recycle

KIND = "restore_recycled"
TITLE = "Put a file back from the recycle folder"

GONE = (
    "This file isn't in the recycle folder any more (perhaps it was moved or deleted by "
    "hand), so there's nothing to put back."
)
NOT_OURS = (
    "Tailarr can only put back files it moved into a recycle folder inside your Films or TV "
    "folder. Nothing was changed."
)
INTERRUPTED = (
    "Tailarr was stopped or restarted while it was putting the file back. Open the folder to "
    "check which files are there; the file is either back in its usual place or still in the "
    "hidden .tailarr-recycle folder."
)


def clash_message(name: str) -> str:
    return (
        f"There's already a file called “{name}” in that folder, so Tailarr didn't put the "
        "old one back. Choose “swap them” to move the current file to the recycle folder "
        "first."
    )


def check_restorable(record: RecycledFile | None, roots: list[str]) -> RecycledFile:
    """The record must be a file Tailarr recycled, still there, going back inside the library."""
    if record is None:
        raise JobFailed(GONE)
    recycled, original = Path(record.path), Path(record.original_path)
    if (
        recycled.parent.name != RECYCLE_FOLDER
        or recycled.parent.parent != original.parent
        or not any(is_inside(record.path, root) for root in roots)
        or not any(is_inside(record.original_path, root) for root in roots)
    ):
        raise JobFailed(NOT_OURS)
    if not recycled.is_file():
        raise JobFailed(GONE)
    return record


def make_job_type(
    engine: Engine,
    allowed_roots: Callable[[], list[str]],
    folder_changed: Callable[[str], None],
) -> JobType:
    def run(ctx: JobContext) -> str:
        record_id = int(ctx.params["recycled_id"])
        swap = bool(ctx.params.get("swap", False))
        roots = allowed_roots()

        ctx.step(1, 3, "Checking the files")
        with Session(engine) as session:
            record = check_restorable(session.get(RecycledFile, record_id), roots)
            recycled, original = record.path, record.original_path
        name = Path(original).name
        clash = os.path.lexists(original)
        if clash and not swap:
            raise JobFailed(clash_message(name))

        # From here on, the steps are instant renames that mustn't be interrupted.
        moved_aside: str | None = None  # where the file that was there went
        with Session(engine) as session:
            keep_days = get_recycle_settings(session).keep_days
            if clash:
                ctx.step(2, 3, "Moving the current file to the recycle folder", cancellable=False)
                try:
                    aside = move_to_recycle(session, original, ctx.job_id)
                    moved_aside = aside.path
                except OSError as exc:
                    raise JobFailed(
                        "Tailarr couldn't move the current file into the recycle folder, so "
                        "nothing was changed.",
                        str(exc),
                    ) from exc

            ctx.step(3, 3, "Putting the file back", cancellable=False)
            try:
                if os.path.lexists(original):  # appeared in the meantime: never overwrite
                    raise FileExistsError(original)
                os.rename(recycled, original)
            except OSError as exc:
                if moved_aside is not None:  # put the current file back too
                    os.rename(moved_aside, original)
                    session.delete(aside)
                    session.commit()
                raise JobFailed(
                    "Tailarr couldn't put the file back, so nothing was changed.", str(exc)
                ) from exc
            stored = session.get(RecycledFile, record_id)
            if stored is not None:
                session.delete(stored)
            session.commit()

        folder = Path(original).parent
        with contextlib.suppress(OSError):  # an empty recycle folder goes away
            Path(recycled).parent.rmdir()
        folder_changed(str(folder))
        message = f"Put {name} back from the recycle folder."
        if moved_aside is not None:
            message += (
                f" The file that was there moved to the recycle folder (kept {keep_days} days)."
            )
        record_activity(engine, "tailarr", "restored", message, path=original, job_id=ctx.job_id)
        ctx.result = {
            "file": name,
            "swapped": moved_aside is not None,
            "recycled": moved_aside,
        }
        return message

    return JobType(kind=KIND, run=run, in_place=True, interrupted_message=INTERRUPTED)
