"""Applying one action to many films or episodes at once ("change many").

TV seasons/shows and a selection of films share this: each item's own file (and, if asked,
the copies Tailarr made of it) is planned with `actions/plans.py`, the owner sees a summary
of every file, and confirming queues one job per file as a group.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..actions.plans import (
    Action,
    FilePlan,
    changes_originals,
    describe_action,
    plan_file,
    space_totals,
)
from ..core.config import AppConfig
from ..core.paths import is_inside
from ..jobs.engine import JobQueue
from ..jobs.hdr10_copy import usable_work_folder
from ..jobs.models import JobGroup
from ..library.media_reader import MediaReader, details_of
from .common import LibraryFile


class BatchIn(BaseModel):
    action: Action
    # Tick "I understand" for files that are also in the downloads folder (still seeding).
    allow_hardlinked: bool = False
    # Also change the copies Tailarr made of these items (updated where they are).
    include_copies: bool = False


class BatchFileOut(BaseModel):
    kind: str  # "film" or "episode"
    item_id: int
    label: str  # "S01E02 – The Second One", "Blade Runner (1982)"
    file: str
    will_run: bool
    lines: list[str]
    reason: str | None
    hardlinked: bool
    new_file: str | None
    is_copy: bool = False  # one of Tailarr's copies (only with "also change copies")
    warnings: list[str] = []  # worth a look, e.g. no subtitles would be left


class SpaceTotalOut(BaseModel):
    label: str
    needed: int
    free: int
    enough: bool


class BatchPreviewOut(BaseModel):
    title: str  # "Make a copy without Dolby Vision: Test Show, Season 1"
    action: str
    scope: str  # "Test Show, Season 1", "3 films"
    changes_originals: bool
    files: list[BatchFileOut]
    will_run: int
    skipped: int
    hardlinked_skipped: int  # seeding files left out because "I understand" isn't ticked
    flagged: int  # files worth a look (e.g. no subtitles or no audio would be left)
    copies: int  # Tailarr copies these items have (offered with "also change copies")
    space: list[SpaceTotalOut]
    enough_space: bool


class BatchStartedOut(BaseModel):
    group_id: str
    title: str
    jobs: int


@dataclass
class BatchTarget:
    """One film or episode: its own file first, then any copies Tailarr made of it."""

    kind: str  # "film" or "episode"
    id: int
    label: str  # shown in the summary
    subject: str  # shown in the queue
    main_file: str | None
    files: list[LibraryFile]
    root: str


@dataclass
class PlannedBatch:
    preview: BatchPreviewOut
    plans: list[tuple[BatchTarget, FilePlan]]


def plan_batch(
    session: Session,
    config: AppConfig,
    reader: MediaReader,
    targets: list[BatchTarget],
    body: BatchIn,
    scope: str,
) -> PlannedBatch:
    plans: list[tuple[BatchTarget, FilePlan]] = []
    copies = 0
    for target in targets:
        main = next((f for f in target.files if f.name == target.main_file), None)
        target_copies = [f for f in target.files if f.is_copy and f is not main]
        copies += len(target_copies)
        files = [main] if main is not None else []
        if body.include_copies:
            files += target_copies
        for file in files:
            if not is_inside(file.path, target.root):
                continue
            details, error = None, None
            try:
                record = reader.get(session, file.path)
                details = details_of(record)
                error = record.error
            except OSError:
                error = "This file can't be opened any more."
            plans.append(
                (
                    target,
                    plan_file(
                        body.action,
                        file.path,
                        details,
                        is_copy=file.is_copy,
                        update_copies=body.include_copies,
                        allow_hardlinked=body.allow_hardlinked,
                        read_error=error,
                    ),
                )
            )
    totals = space_totals([p for _, p in plans], usable_work_folder(config.work_dir))
    space = [
        SpaceTotalOut(label=t.label, needed=t.needed, free=t.free, enough=t.enough) for t in totals
    ]
    action = describe_action(body.action)
    files = [
        BatchFileOut(
            kind=target.kind,
            item_id=target.id,
            label=target.label + (" (Tailarr's copy)" if plan.is_copy else ""),
            file=plan.name,
            will_run=plan.will_run,
            lines=plan.lines,
            reason=plan.reason,
            hardlinked=plan.hardlinked,
            new_file=plan.new_file,
            is_copy=plan.is_copy,
            warnings=plan.warnings,
        )
        for target, plan in plans
    ]
    preview = BatchPreviewOut(
        title=f"{action}: {scope}",
        action=action,
        scope=scope,
        changes_originals=changes_originals(body.action),
        files=files,
        will_run=sum(1 for _, p in plans if p.will_run),
        skipped=sum(1 for _, p in plans if not p.will_run),
        hardlinked_skipped=sum(1 for _, p in plans if not p.will_run and p.hardlinked),
        flagged=sum(1 for _, p in plans if p.warnings),
        copies=copies,
        space=space,
        enough_space=all(s.enough for s in space),
    )
    return PlannedBatch(preview=preview, plans=plans)


def start_batch(
    session: Session, queue: JobQueue, batch: PlannedBatch, what: str
) -> BatchStartedOut:
    """Queue one job per file (shown as a group in the queue). `what`: "episodes", "films"."""
    preview = batch.preview
    if preview.will_run == 0:
        raise HTTPException(status_code=400, detail=f"There's nothing to do for these {what}.")
    if not preview.enough_space:
        raise HTTPException(
            status_code=507,
            detail="Not enough free space for all of these copies. Free up some space, or "
            "choose fewer at a time.",
        )
    group = JobGroup(id=uuid.uuid4().hex, title=preview.title, created_at=time.time())
    session.add(group)
    session.commit()
    count = 0
    for target, plan in batch.plans:
        if not plan.will_run or plan.job_kind is None:
            continue
        link = {"film_id": target.id} if target.kind == "film" else {"episode_id": target.id}
        queue.submit(
            plan.job_kind,
            title=plan.job_title or plan.job_kind,
            subject=target.subject,
            path=plan.path,
            params=plan.params,
            group_id=group.id,
            **link,
        )
        count += 1
    return BatchStartedOut(group_id=group.id, title=group.title, jobs=count)
