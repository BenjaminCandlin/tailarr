"""The rules table and what a rule says, in a form the web page and the planner share."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator
from sqlmodel import Field as DbField
from sqlmodel import SQLModel

from ..actions.plans import Action, DefaultTracksAction
from ..media.languages import normalize_language

Scope = Literal["films", "tv", "both"]


class Condition(BaseModel):
    """One "if": all of a rule's conditions must be true for a file."""

    type: Literal[
        "has_dolby_vision",
        "has_hdr10plus",
        "is_4k",
        "has_audio_not_in",
        "has_subtitles_not_in",
    ]
    languages: list[str] = []

    @field_validator("languages")
    @classmethod
    def _codes(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_language(c) for c in value if c.strip()))

    @model_validator(mode="after")
    def _needs_languages(self) -> Condition:
        if self.type.endswith("_not_in") and not self.languages:
            raise ValueError("Choose at least one language for the condition.")
        return self


class RuleIn(BaseModel):
    """A rule as the owner writes it."""

    name: str = Field(min_length=1, max_length=120)
    enabled: bool = False
    scope: Scope = "films"
    conditions: list[Condition] = []
    action: Action
    # Rules never touch originals unless this is ticked (safety rule 2), off by default.
    allow_originals: bool = False
    # ...and never change a hardlinked (seeding) file in place unless this is ticked too.
    allow_hardlinked: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Give the rule a name.")
        return value

    @model_validator(mode="after")
    def _originals(self) -> RuleIn:
        if isinstance(self.action, DefaultTracksAction) and not self.allow_originals:
            raise ValueError(
                "Choosing default tracks changes the original files, so tick “Allowed to change "
                "original files” for this rule (or choose another action)."
            )
        if self.allow_hardlinked and not self.allow_originals:
            self.allow_hardlinked = False
        return self


_ACTION = TypeAdapter(Action)
_CONDITIONS = TypeAdapter(list[Condition])


class Rule(SQLModel, table=True):
    id: int | None = DbField(default=None, primary_key=True)
    name: str
    enabled: bool = False
    scope: str = "films"
    conditions: str = "[]"  # JSON list of Condition
    action: str  # JSON Action
    allow_originals: bool = False
    allow_hardlinked: bool = False
    created_at: float
    updated_at: float
    last_run_at: float | None = None

    def to_input(self) -> RuleIn:
        return RuleIn.model_validate(
            {
                "name": self.name,
                "enabled": self.enabled,
                "scope": self.scope,
                "conditions": json.loads(self.conditions),
                "action": json.loads(self.action),
                "allow_originals": self.allow_originals,
                "allow_hardlinked": self.allow_hardlinked,
            }
        )

    def update_from(self, rule: RuleIn) -> None:
        self.name = rule.name
        self.enabled = rule.enabled
        self.scope = rule.scope
        self.conditions = _CONDITIONS.dump_json(rule.conditions).decode()
        self.action = _ACTION.dump_json(rule.action).decode()
        self.allow_originals = rule.allow_originals
        self.allow_hardlinked = rule.allow_hardlinked


class RuleRun(SQLModel, table=True):
    """A rule has looked at one version of a file (path + size + date): never again.

    So each new or upgraded file is handled once per rule, and Tailarr's own changes to a
    file don't make rules run on it again.
    """

    id: int | None = DbField(default=None, primary_key=True)
    rule_id: int = DbField(index=True)
    path: str = DbField(index=True)
    size: int
    mtime: float
    at: float
    outcome: str  # "queued", "skipped", "no-match", "tailarr-change"
    job_id: int | None = None
