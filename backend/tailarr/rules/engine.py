"""Working out what a rule would do (preview) and doing it (run).

A rule is checked against each film's or episode's own file (never against Tailarr's
copies). Its conditions decide whether the file matches; its action is then planned by
the same planner as TV batch actions (`actions/plans.py`), so every safety check is the
same. Previews only use what Tailarr has already read about each file, so they're quick
and never wake up sleeping disks; files not read yet are counted separately.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlmodel import Session, select

from ..actions.plans import (
    DefaultTracksAction,
    FilePlan,
    describe_action,
    plan_file,
    space_totals,
)
from ..connections.models import ExternalInfo
from ..connections.service import record_activity
from ..core.config import AppConfig
from ..core.paths import is_inside
from ..core.settings_store import get_library_settings
from ..jobs.engine import JobQueue
from ..jobs.hdr10_copy import usable_work_folder
from ..jobs.models import JobGroup
from ..library.media_reader import details_of, is_current
from ..library.models import Episode, EpisodeFile, Film, FilmFile, MediaRecord, Show
from ..library.tv_naming import episode_label
from ..media.languages import language_name, normalize_language
from ..media.probe import MediaDetails
from .models import Condition, Rule, RuleIn

_UNKNOWN = {"und", "zxx", "mul", "mis"}


@dataclass
class Candidate:
    kind: str  # "film" or "episode"
    id: int
    label: str  # "Blade Runner (1982)", "Test Show – S01E02 – Title"
    path: str
    is_copy: bool
    details: MediaDetails | None
    read: bool  # False: Tailarr hasn't read this file yet
    read_error: str | None = None


# -- describing ---------------------------------------------------------------------------


def _languages(codes: list[str]) -> str:
    names = [language_name(c) for c in codes]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def describe_condition(condition: Condition) -> str:
    if condition.type == "has_dolby_vision":
        return "it has Dolby Vision"
    if condition.type == "has_hdr10plus":
        return "it has HDR10+"
    if condition.type == "is_4k":
        return "it's 4K"
    if condition.type == "has_audio_not_in":
        return f"it has audio that isn't {_languages(condition.languages)}"
    return f"it has subtitles that aren't {_languages(condition.languages)}"


def describe_rule(rule: RuleIn) -> str:
    """'When a new film is added, if it has Dolby Vision, make a copy without Dolby Vision.'"""
    what = {"films": "film", "tv": "episode", "both": "film or episode"}[rule.scope]
    text = f"When a new {what} is added"
    if rule.conditions:
        text += ", if " + " and ".join(describe_condition(c) for c in rule.conditions)
    action = describe_action(rule.action)
    return f"{text}: {action[0].lower()}{action[1:]}."


# -- conditions ---------------------------------------------------------------------------


def _other_languages(tracks: list, languages: list[str]) -> bool:
    wanted = set(languages)
    return any(normalize_language(t.language) not in wanted | _UNKNOWN for t in tracks)


def condition_met(condition: Condition, details: MediaDetails) -> bool:
    if condition.type == "has_dolby_vision":
        return details.hdr.dv_profile is not None or "Dolby Vision" in details.hdr.formats
    if condition.type == "has_hdr10plus":
        return "HDR10+" in details.hdr.formats
    if condition.type == "is_4k":
        return details.resolution == "4K"
    if condition.type == "has_audio_not_in":
        return _other_languages(details.of_type("audio"), condition.languages)
    return _other_languages(details.of_type("subtitles"), condition.languages)


# -- the library ---------------------------------------------------------------------------


def _records(session: Session, paths: list[str]) -> dict[str, MediaRecord]:
    if not paths:
        return {}
    wanted = set(paths)
    return {r.path: r for r in session.exec(select(MediaRecord)).all() if r.path in wanted}


def candidates(session: Session, config: AppConfig, scope: str) -> list[Candidate]:
    """Every film's and/or episode's own file (no copies), with what Tailarr knows about it."""
    library = get_library_settings(session, config)
    infos = {e.folder: e for e in session.exec(select(ExternalInfo)).all()}
    rows: list[tuple[str, int, str, FilmFile | EpisodeFile]] = []
    if scope in ("films", "both"):
        films = {f.id: f for f in session.exec(select(Film)).all()}
        for file in session.exec(select(FilmFile)).all():
            film = films.get(file.film_id)
            if film is None or file.name != film.main_file:
                continue
            if not is_inside(film.folder, library.movies_dir):
                continue
            info = infos.get(film.folder)
            title = info.title if info and info.title else film.title
            year = info.year if info and info.year else film.year
            rows.append(("film", film.id, f"{title} ({year})" if year else title, file))  # type: ignore[arg-type]
    if scope in ("tv", "both"):
        shows = {s.id: s for s in session.exec(select(Show)).all()}
        episodes = {e.id: e for e in session.exec(select(Episode)).all()}
        for file in session.exec(select(EpisodeFile)).all():
            episode = episodes.get(file.episode_id)
            show = shows.get(file.show_id)
            if episode is None or show is None or file.name != episode.main_file:
                continue
            if not is_inside(episode.folder, library.tv_dir):
                continue
            info = infos.get(show.folder)
            parts = [
                info.title if info and info.title else show.title,
                episode_label(episode.season, episode.episode, episode.episode_end),
                episode.title,
            ]
            rows.append(("episode", episode.id, " – ".join(p for p in parts if p), file))  # type: ignore[arg-type]
    records = _records(session, [r[3].path for r in rows])
    out = []
    for kind, item_id, label, file in rows:
        record = records.get(file.path)
        current = record is not None and is_current(record, file.size, file.mtime)
        out.append(
            Candidate(
                kind=kind,
                id=item_id,
                label=label,
                path=file.path,
                is_copy=file.is_copy,
                details=details_of(record) if current and record else None,
                read=current,
                read_error=record.error if current and record else None,
            )
        )
    out.sort(key=lambda c: (c.kind, c.label.casefold()))
    return out


# -- planning and running -------------------------------------------------------------------


@dataclass
class RuleMatch:
    candidate: Candidate
    plan: FilePlan


@dataclass
class RulePlan:
    matches: list[RuleMatch]
    not_matching: int
    not_read: int


def plan_for(rule: RuleIn, candidate: Candidate) -> FilePlan | None:
    """What the rule does to one file, or None if its conditions don't match."""
    if candidate.is_copy:
        return None  # rules only look at original files
    details = candidate.details
    if details is not None and not all(condition_met(c, details) for c in rule.conditions):
        return None
    plan = plan_file(
        rule.action,
        candidate.path,
        details,
        is_copy=candidate.is_copy,
        allow_hardlinked=rule.allow_hardlinked,
        read_error=candidate.read_error,
    )
    if isinstance(rule.action, DefaultTracksAction) and not rule.allow_originals:
        plan.will_run = False
        plan.reason = "This rule isn't allowed to change original files."
    return plan


def plan_rule(rule: RuleIn, items: list[Candidate]) -> RulePlan:
    matches: list[RuleMatch] = []
    not_matching = not_read = 0
    for candidate in items:
        if candidate.is_copy:
            continue
        if not candidate.read:
            not_read += 1
            continue
        plan = plan_for(rule, candidate)
        if plan is None:
            not_matching += 1
            continue
        matches.append(RuleMatch(candidate, plan))
    return RulePlan(matches=matches, not_matching=not_matching, not_read=not_read)


def rule_space(plan: RulePlan, config: AppConfig) -> list:
    return space_totals([m.plan for m in plan.matches], usable_work_folder(config.work_dir))


def submit(
    engine: Engine,
    queue: JobQueue,
    rule: Rule,
    matches: list[RuleMatch],
    *,
    reason: str,
) -> tuple[str | None, int]:
    """Queue one job per file that the rule changes, as one group. Returns (group, count)."""
    runnable = [m for m in matches if m.plan.will_run and m.plan.job_kind]
    if not runnable:
        return None, 0
    title = f"Rule “{rule.name}”: {reason}"
    group_id = uuid.uuid4().hex
    with Session(engine) as session:
        session.add(JobGroup(id=group_id, title=title, created_at=time.time()))
        stored = session.get(Rule, rule.id)
        if stored is not None:
            stored.last_run_at = time.time()
            session.add(stored)
        session.commit()
    for match in runnable:
        link = (
            {"film_id": match.candidate.id}
            if match.candidate.kind == "film"
            else {"episode_id": match.candidate.id}
        )
        job = queue.submit(
            match.plan.job_kind,  # type: ignore[arg-type]
            title=match.plan.job_title or match.plan.job_kind,  # type: ignore[arg-type]
            subject=match.candidate.label,
            path=match.plan.path,
            params=match.plan.params,
            group_id=group_id,
            **link,
        )
        record_activity(
            engine,
            "rule",
            "job-queued",
            f"Rule “{rule.name}”: {job.title.lower()} for {match.candidate.label}.",
            path=match.plan.path,
            job_id=job.id,
            rule_id=rule.id,
        )
    return group_id, len(runnable)
