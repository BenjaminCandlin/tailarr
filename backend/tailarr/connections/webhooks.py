"""Messages from Radarr and Sonarr ("webhooks"): keeping Tailarr's copies in step.

Radarr and Sonarr track one file per film/episode. When they **upgrade** or **delete**
that file, any copies Tailarr made from it are now from an old release; when they
**rename** it, the copies keep their old names. With the "Tidy up copies" setting on
(the default), Tailarr:

* moves copies of an upgraded/deleted original into the hidden recycle folder (kept for
  the recycle period, like replaced originals; never deleted straight away), and
* renames copies to match a renamed original (``New name - HDR10.mkv``).

Only files Tailarr recorded making are touched, only inside the library, only if they
still have a Tailarr copy name, and never a copy that is hardlinked elsewhere. New
imports just make Tailarr look at the folder straight away (rules come in Stage 10).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from ..core.paths import PathMapping, is_inside, map_remote_path
from ..jobs import hdr10_copy, remove_tracks
from ..jobs.models import CopyRecord
from ..jobs.recycle import move_to_recycle
from ..library.naming import is_tailarr_copy
from .service import record_activity

log = logging.getLogger(__name__)

_COPY_NAMES = {
    hdr10_copy.KIND: hdr10_copy.output_name,
    remove_tracks.KIND: remove_tracks.output_name,
}


@dataclass
class WebhookResult:
    event: str
    message: str
    imported: list[str] = field(default_factory=list)  # new files, for rules (Stage 10)
    upgraded: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)  # folders to look at again


def _paths(items: Any) -> list[str]:
    out = []
    for item in items or []:
        path = item.get("path") if isinstance(item, dict) else None
        if path:
            out.append(path)
    return out


def _file_paths(payload: dict[str, Any], service: str) -> list[str]:
    key = "movieFile" if service == "radarr" else "episodeFile"
    single = payload.get(key)
    paths = _paths([single]) if isinstance(single, dict) else []
    paths += _paths(payload.get("episodeFiles"))
    return paths


def _stale_copies(engine: Engine, original: str) -> list[CopyRecord]:
    with Session(engine) as session:
        return list(session.exec(select(CopyRecord).where(CopyRecord.source_path == original)))


def tidy_copies_of(
    engine: Engine, original: str, roots: list[str], reason: str, service: str
) -> list[str]:
    """Move Tailarr's copies of an original that's gone into the recycle folder."""
    moved: list[str] = []
    if os.path.exists(original):
        return moved  # the original is still there: its copies aren't stale
    for record in _stale_copies(engine, original):
        copy = record.path
        problem = None
        if not any(is_inside(copy, root) for root in roots):
            problem = "it isn't inside your Films or TV folder"
        elif not is_tailarr_copy(Path(copy).name):
            problem = "it doesn't have a Tailarr copy name any more"
        elif not os.path.exists(copy):
            problem = None  # already gone: just forget it
        elif os.stat(copy).st_nlink > 1:
            problem = "it's hardlinked to another file"
        if problem:
            record_activity(
                engine,
                service,
                "copy-kept",
                f"Kept {Path(copy).name}: {problem}.",
                ok=False,
                path=copy,
            )
            continue
        with Session(engine) as session:
            if os.path.exists(copy):
                move_to_recycle(session, copy)
                moved.append(copy)
                record_activity(
                    engine,
                    service,
                    "copy-tidied",
                    f"Moved {Path(copy).name} to the recycle folder: its original was {reason}.",
                    path=copy,
                )
            stored = session.get(CopyRecord, copy)
            if stored is not None:
                session.delete(stored)
            session.commit()
        # Copies made from this copy are now stale too.
        moved += tidy_copies_of(engine, copy, roots, reason, service)
    return moved


def rename_copies_of(
    engine: Engine, previous: str, new: str, roots: list[str], service: str
) -> list[str]:
    """Give Tailarr's copies of a renamed original matching names."""
    renamed: list[str] = []
    for record in _stale_copies(engine, previous):
        old_copy = Path(record.path)
        if not old_copy.exists():
            # Radarr may have moved the whole folder, copies included.
            moved = Path(new).parent / old_copy.name
            if moved.exists():
                old_copy = moved
            else:
                continue
        name_for = _COPY_NAMES.get(record.kind)
        if name_for is None:
            continue
        target = Path(new).parent / name_for(Path(new).name)
        ok = (
            any(is_inside(str(target), root) for root in roots)
            and is_tailarr_copy(old_copy.name)
            and not target.exists()
        )
        with Session(engine) as session:
            stored = session.get(CopyRecord, record.path)
            if stored is None:
                continue
            if ok and old_copy != target:
                os.rename(old_copy, target)
                renamed.append(str(target))
                record_activity(
                    engine,
                    service,
                    "copy-renamed",
                    f"Renamed {old_copy.name} to {target.name} to match its original.",
                    path=str(target),
                )
            final = target if ok else old_copy
            session.delete(stored)
            session.flush()
            session.add(
                CopyRecord(
                    path=str(final),
                    source_path=new,
                    source_size=stored.source_size,
                    source_mtime=stored.source_mtime,
                    kind=stored.kind,
                    created_at=stored.created_at,
                    job_id=stored.job_id,
                )
            )
            session.commit()
        renamed += rename_copies_of(engine, record.path, str(final), roots, service)
    return renamed


def _copies(count: int) -> str:
    return f"{count} Tailarr cop{'y' if count == 1 else 'ies'}"


def handle(
    engine: Engine,
    service: str,
    payload: dict[str, Any],
    *,
    mappings: list[PathMapping],
    roots: list[str],
    tidy: bool,
    folder_changed: Callable[[str], None],
) -> WebhookResult:
    """Act on one message from Radarr or Sonarr."""
    event = str(payload.get("eventType") or "")
    name = "Radarr" if service == "radarr" else "Sonarr"

    def local(path: str) -> str:
        return os.path.normpath(map_remote_path(path, mappings))

    def inside(path: str) -> bool:
        return any(is_inside(path, root) for root in roots)

    result = WebhookResult(event=event, message=f"{name} sent “{event}”.")
    if event == "Test":
        result.message = f"{name} sent a test message. The connection works."
    elif event == "Download":
        files = [local(p) for p in _file_paths(payload, service)]
        files = [f for f in files if inside(f)]
        result.imported = files
        old = [local(p) for p in _paths(payload.get("deletedFiles"))]
        upgrade = bool(payload.get("isUpgrade")) or bool(old)
        if upgrade:
            result.upgraded = files
        moved: list[str] = []
        if tidy:
            for path in old:
                if inside(path):
                    moved += tidy_copies_of(engine, path, roots, "upgraded", service)
        what = "an upgrade" if upgrade else "a new file"
        result.message = f"{name} imported {what}: " + (
            ", ".join(Path(f).name for f in files) or "no file inside your library"
        )
        if moved:
            result.message += f". {_copies(len(moved))} of the old file moved to the recycle folder"
        result.folders = sorted({str(Path(f).parent) for f in files + old if inside(f)})
    elif event in ("MovieFileDelete", "EpisodeFileDelete"):
        files = [local(p) for p in _file_paths(payload, service)]
        reason = str(payload.get("deleteReason") or "deleted").lower()
        why = "upgraded" if reason == "upgrade" else "deleted"
        moved = []
        if tidy:
            for path in files:
                if inside(path):
                    moved += tidy_copies_of(engine, path, roots, why, service)
        result.message = f"{name} {why} " + (", ".join(Path(f).name for f in files) or "a file")
        if moved:
            result.message += f"; {_copies(len(moved))} moved to the recycle folder"
        result.folders = sorted({str(Path(f).parent) for f in files if inside(f)})
    elif event == "Rename":
        key = "renamedMovieFiles" if service == "radarr" else "renamedEpisodeFiles"
        renamed: list[str] = []
        folders: set[str] = set()
        for item in payload.get(key) or []:
            previous, new = item.get("previousPath"), item.get("path")
            if not previous or not new:
                continue
            previous, new = local(previous), local(new)
            if not inside(new):
                continue
            folders |= {str(Path(previous).parent), str(Path(new).parent)}
            if tidy:
                renamed += rename_copies_of(engine, previous, new, roots, service)
        result.message = f"{name} renamed files" + (
            f"; {_copies(len(renamed))} renamed to match" if renamed else ""
        )
        result.folders = sorted(f for f in folders if inside(f))
    elif event in ("MovieDelete", "SeriesDelete"):
        result.message = f"{name} removed {'a film' if service == 'radarr' else 'a show'}."
        item = payload.get("movie") or payload.get("series") or {}
        folder = item.get("folderPath") or item.get("path")
        if folder and inside(local(folder)):
            result.folders = [local(folder)]
    record_activity(engine, service, "webhook", result.message, path=None)
    for folder in result.folders:
        try:
            folder_changed(folder)
        except Exception:
            log.exception("Couldn't refresh %s after a webhook", folder)
    return result
