"""Rules: list, create, change, delete, preview and run now."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from ..actions.plans import changes_originals, describe_action
from ..core.config import AppConfig
from ..jobs.engine import JobQueue
from ..rules.engine import candidates, describe_rule, plan_rule, rule_space, submit
from ..rules.models import Rule, RuleIn
from .common import time_of
from .deps import get_config, get_session
from .jobs import get_queue

router = APIRouter(prefix="/api/rules")

PREVIEW_LIMIT = 500  # files listed in a preview (the counts cover everything)


class RuleOut(RuleIn):
    id: int
    sentence: str  # the whole rule in plain English
    action_text: str
    changes_originals: bool
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None


def _out(rule: Rule) -> RuleOut:
    data = rule.to_input()
    return RuleOut(
        **data.model_dump(),
        id=rule.id,  # type: ignore[arg-type]
        sentence=describe_rule(data),
        action_text=describe_action(data.action),
        changes_originals=changes_originals(data.action),
        created_at=time_of(rule.created_at),  # type: ignore[arg-type]
        updated_at=time_of(rule.updated_at),  # type: ignore[arg-type]
        last_run_at=time_of(rule.last_run_at),
    )


def _get(session: Session, rule_id: int) -> Rule:
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="This rule doesn't exist any more.")
    return rule


@router.get("", response_model=list[RuleOut])
def list_rules(session: Annotated[Session, Depends(get_session)]) -> list[RuleOut]:
    rules = session.exec(select(Rule).order_by(col(Rule.created_at))).all()
    return [_out(r) for r in rules]


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, session: Annotated[Session, Depends(get_session)]) -> RuleOut:
    now = time.time()
    rule = Rule(name="", action="{}", created_at=now, updated_at=now)
    rule.update_from(body)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _out(rule)


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(rule_id: int, session: Annotated[Session, Depends(get_session)]) -> RuleOut:
    return _out(_get(session, rule_id))


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int, body: RuleIn, session: Annotated[Session, Depends(get_session)]
) -> RuleOut:
    rule = _get(session, rule_id)
    rule.update_from(body)
    rule.updated_at = time.time()
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _out(rule)


class EnabledIn(BaseModel):
    enabled: bool


@router.post("/{rule_id}/enabled", response_model=RuleOut)
def set_enabled(
    rule_id: int, body: EnabledIn, session: Annotated[Session, Depends(get_session)]
) -> RuleOut:
    rule = _get(session, rule_id)
    rule.enabled = body.enabled
    rule.updated_at = time.time()
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _out(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Annotated[Session, Depends(get_session)]) -> None:
    session.delete(_get(session, rule_id))
    session.commit()


# -- preview and run --------------------------------------------------------------------------


class PreviewItemOut(BaseModel):
    kind: str  # "film" or "episode"
    id: int
    label: str
    file: str
    will_run: bool
    lines: list[str]
    reason: str | None
    hardlinked: bool
    new_file: str | None


class SpaceOut(BaseModel):
    label: str
    needed: int
    free: int
    enough: bool


class RulePreviewOut(BaseModel):
    sentence: str
    changes_originals: bool
    items: list[PreviewItemOut]  # files the rule matches (up to PREVIEW_LIMIT)
    will_run: int
    skipped: int  # matched, but nothing to do or not possible
    not_matching: int  # conditions not met
    not_read: int  # Tailarr hasn't read these files yet
    space: list[SpaceOut]
    enough_space: bool


def _preview(session: Session, config: AppConfig, rule: RuleIn) -> tuple[RulePreviewOut, object]:
    plan = plan_rule(rule, candidates(session, config, rule.scope))
    space = [
        SpaceOut(label=t.label, needed=t.needed, free=t.free, enough=t.enough)
        for t in rule_space(plan, config)
    ]
    # Files that will change first, then the skipped ones.
    ordered = sorted(plan.matches, key=lambda m: not m.plan.will_run)
    preview = RulePreviewOut(
        sentence=describe_rule(rule),
        changes_originals=changes_originals(rule.action),
        items=[
            PreviewItemOut(
                kind=m.candidate.kind,
                id=m.candidate.id,
                label=m.candidate.label,
                file=m.plan.name,
                will_run=m.plan.will_run,
                lines=m.plan.lines,
                reason=m.plan.reason,
                hardlinked=m.plan.hardlinked,
                new_file=m.plan.new_file,
            )
            for m in ordered[:PREVIEW_LIMIT]
        ],
        will_run=sum(1 for m in plan.matches if m.plan.will_run),
        skipped=sum(1 for m in plan.matches if not m.plan.will_run),
        not_matching=plan.not_matching,
        not_read=plan.not_read,
        space=space,
        enough_space=all(s.enough for s in space),
    )
    return preview, plan


@router.post("/preview", response_model=RulePreviewOut)
def preview_unsaved(
    body: RuleIn,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> RulePreviewOut:
    """What a rule (saved or not) would do to the whole library now. Changes nothing."""
    return _preview(session, config, body)[0]


@router.post("/{rule_id}/preview", response_model=RulePreviewOut)
def preview_rule(
    rule_id: int,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> RulePreviewOut:
    return _preview(session, config, _get(session, rule_id).to_input())[0]


class RunIn(BaseModel):
    confirmed: bool = False


class RunOut(BaseModel):
    group_id: str | None
    jobs: int


@router.post("/{rule_id}/run", response_model=RunOut, status_code=202)
def run_rule(
    rule_id: int,
    body: RunIn,
    request: Request,
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> RunOut:
    """Apply the rule to the whole library now (after the owner confirmed the preview)."""
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Please check the preview and confirm first.")
    rule = _get(session, rule_id)
    preview, plan = _preview(session, config, rule.to_input())
    if preview.will_run == 0:
        raise HTTPException(status_code=400, detail="This rule has nothing to do right now.")
    if not preview.enough_space:
        raise HTTPException(
            status_code=507,
            detail="Not enough free space for everything this rule would do. Free up some space "
            "first.",
        )
    group, count = submit(
        request.app.state.engine,
        queue,
        rule,
        plan.matches,
        reason="run by hand",  # type: ignore[attr-defined]
    )
    return RunOut(group_id=group, jobs=count)
