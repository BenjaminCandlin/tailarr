"""Tidying Tailarr's own records and caches, so nothing grows forever.

* Finished jobs older than 30 days leave the Queue's history (running and waiting jobs,
  and the activity log, are kept).
* Small poster copies not used for 90 days are deleted (they're remade when needed).
* Radarr/Sonarr pictures that no film or show uses any more are deleted.
* Rule memory (`RuleRun`) for files that no longer exist is forgotten.

Only Tailarr's own database rows and files in /config/cache are touched.
"""

from __future__ import annotations

import logging
import os
import time

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from ..connections.models import ExternalInfo
from ..jobs.models import ACTIVE, Job, JobGroup
from ..rules.models import RuleRun
from .config import AppConfig

log = logging.getLogger(__name__)

JOB_HISTORY_DAYS = 30
THUMBNAIL_DAYS = 90


def clean_job_history(engine: Engine, now: float | None = None) -> int:
    cutoff = (now or time.time()) - JOB_HISTORY_DAYS * 86400
    with Session(engine) as session:
        old = session.exec(
            select(Job).where(col(Job.status).not_in(list(ACTIVE)), col(Job.finished_at) < cutoff)
        ).all()
        for job in old:
            session.delete(job)
        session.flush()
        used = set(session.exec(select(Job.group_id).where(col(Job.group_id).is_not(None))).all())
        for group in session.exec(select(JobGroup)).all():
            if group.id not in used:
                session.delete(group)
        session.commit()
    return len(old)


def clean_caches(engine: Engine, config: AppConfig, now: float | None = None) -> int:
    now = now or time.time()
    removed = 0
    posters = config.config_dir / "cache" / "posters"
    if posters.is_dir():
        for path in posters.rglob("*.jpg"):
            try:
                used = max(path.stat().st_atime, path.stat().st_mtime)
                if now - used > THUMBNAIL_DAYS * 86400:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    arr = config.config_dir / "cache" / "arr"
    if arr.is_dir():
        with Session(engine) as session:
            keep = {
                p
                for info in session.exec(select(ExternalInfo)).all()
                for p in (info.poster_file, info.backdrop_file)
                if p
            }
        for path in arr.glob("*.jpg"):
            if str(path) not in keep:
                path.unlink(missing_ok=True)
                removed += 1
    return removed


def clean_rule_memory(engine: Engine) -> int:
    with Session(engine) as session:
        rows = session.exec(select(RuleRun)).all()
        gone = [r for r in rows if not os.path.exists(r.path)]
        for row in gone:
            session.delete(row)
        session.commit()
    return len(gone)


def tidy(engine: Engine, config: AppConfig) -> None:
    for name, step in (
        ("job history", lambda: clean_job_history(engine)),
        ("caches", lambda: clean_caches(engine, config)),
        ("rule memory", lambda: clean_rule_memory(engine)),
    ):
        try:
            count = step()
            if count:
                log.info("Tidied %s: %s removed", name, count)
        except Exception:  # never let tidying crash the app
            log.exception("Tidying %s failed", name)
