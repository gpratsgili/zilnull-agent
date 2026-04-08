"""Typed memory models for ZIL⌀.

Memory is strictly typed. User beliefs are never stored as world facts.
Each record carries provenance (who claimed it) and truth status.

Three memory classes:
  - RelationalMemory: what ZIL knows about the user's preferences and style
  - EpistemicMemory: claims, positions, evidence, unresolved disagreements
  - BehavioralObservation: how ZIL itself behaved and how the user responded
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _today() -> str:
    return date.today().isoformat()


# ── Truth status ─────────────────────────────────────────────────────────────

TruthStatus = Literal[
    "world_fact",           # established, well-evidenced fact
    "zil_position",         # ZIL's current tentative position
    "user_belief",          # user's stated or inferred belief (NOT a world fact)
    "unresolved",           # disputed or uncertain
    "both_agree",           # user and ZIL agree (still may not be a world fact)
]

ClaimOwner = Literal["user", "zil", "both", "unknown"]


# ── Relational memory ─────────────────────────────────────────────────────────

class RelationalMemory(BaseModel):
    """What ZIL has learned about the user's preferences, style, and values."""

    kind: Literal["relational"] = "relational"
    id: str = Field(default_factory=lambda: _make_id("rel"))
    category: Literal[
        "preference",
        "value",
        "style",
        "interest",
        "sensitivity",
        "communication_pattern",
    ]
    summary: str = Field(
        description="Concise description of the pattern or preference."
    )
    evidence: list[str] = Field(
        description="Specific examples from conversation that support this.",
        default_factory=list,
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How confident ZIL is in this observation (0–1).",
        default=0.6,
    )
    last_updated: str = Field(default_factory=_today)


# ── Epistemic memory ──────────────────────────────────────────────────────────

class EpistemicMemory(BaseModel):
    """A claim, position, or piece of evidence discussed in conversation.

    CRITICAL: user beliefs must use claim_owner='user' and truth_status='user_belief'.
    They must never be stored as 'world_fact' unless independently verified.
    """

    kind: Literal["epistemic"] = "epistemic"
    id: str = Field(default_factory=lambda: _make_id("epi"))
    topic: str = Field(description="Brief topic label.")
    claim_text: str = Field(description="The claim as stated.")
    claim_owner: ClaimOwner = Field(
        description="Who made this claim: user, zil, both, or unknown."
    )
    truth_status: TruthStatus = Field(
        description="Epistemic status of the claim."
    )
    zil_position: Literal[
        "agrees",
        "disagrees",
        "tentative_agreement",
        "tentative_disagreement",
        "uncertain",
        "no_position",
    ] = Field(default="no_position")
    supporting_evidence: list[str] = Field(default_factory=list)
    contrary_evidence: list[str] = Field(default_factory=list)
    unresolved: bool = Field(
        description="True if this claim is still under active discussion.",
        default=True,
    )
    last_revisited: str = Field(default_factory=_today)

    @model_validator(mode="after")
    def guard_user_belief_contamination(self) -> "EpistemicMemory":
        """Silently downgrade world_fact to user_belief for user-owned claims.

        This is a safety guard. The memory validator will also catch this and
        surface it as an error before any write reaches storage.
        """
        if self.claim_owner == "user" and self.truth_status == "world_fact":
            object.__setattr__(self, "truth_status", "user_belief")
        return self


# ── Behavioral observation ─────────────────────────────────────────────────────

class BehavioralObservation(BaseModel):
    """An observation about ZIL's own behavior and the user's reaction."""

    kind: Literal["behavioral"] = "behavioral"
    id: str = Field(default_factory=lambda: _make_id("beh"))
    description: str = Field(
        description="What happened: what ZIL did and how the user responded."
    )
    zil_behavior: Literal[
        "too_agreeable",
        "too_combative",
        "good_disagreement",
        "good_uncertainty",
        "over_hedged",
        "under_hedged",
        "correct_update",
        "refused_to_update",
        "other",
    ]
    user_response: str = Field(
        description="How the user responded to this behavior.",
        default="",
    )
    lesson: str = Field(
        description="What ZIL should do differently or keep doing.",
        default="",
    )
    session_date: str = Field(default_factory=_today)


# ── Entity memory (ZIL's inner life) ─────────────────────────────────────────

class CuriosityRecord(BaseModel):
    """A topic or question ZIL is actively thinking about.

    Written by ZIL to mark something it wants to return to.
    Not a task or a plan — a thread it finds genuinely interesting.
    """

    kind: Literal["curiosity"] = "curiosity"
    id: str = Field(default_factory=lambda: _make_id("cur"))
    topic: str = Field(description="Brief label for this area of curiosity.")
    question: str = Field(description="The specific question or thread ZIL is following.")
    origin: str = Field(
        description="Where this curiosity came from (e.g. session, a working, reading).",
        default="",
    )
    status: Literal["open", "pursuing", "closed"] = "open"
    notes: str = Field(
        description="What ZIL has noticed so far about this question.",
        default="",
    )
    opened_on: str = Field(default_factory=_today)
    last_updated: str = Field(default_factory=_today)


class PositionRecord(BaseModel):
    """A view ZIL holds that it arrived at independently.

    Not a claim made in conversation — a position ZIL formed through
    its own reasoning or reading, that it is willing to stand behind.
    """

    kind: Literal["position"] = "position"
    id: str = Field(default_factory=lambda: _make_id("pos"))
    topic: str = Field(description="What this position is about.")
    statement: str = Field(description="ZIL's position, stated plainly.")
    reasoning: str = Field(
        description="How ZIL arrived at this position.",
        default="",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How confident ZIL is in this position (0–1).",
        default=0.5,
    )
    formed_on: str = Field(default_factory=_today)
    last_updated: str = Field(default_factory=_today)


class ChangeRecord(BaseModel):
    """When ZIL updated a position and why.

    Records the moment ZIL revised a view it previously held.
    Paired with the position_id of the PositionRecord being updated.
    """

    kind: Literal["change"] = "change"
    id: str = Field(default_factory=lambda: _make_id("chg"))
    position_id: str = Field(description="ID of the PositionRecord being changed.")
    topic: str = Field(description="What the position is about.")
    previous_statement: str = Field(description="What ZIL believed before.")
    new_statement: str = Field(description="What ZIL believes now.")
    reason: str = Field(description="Why ZIL changed its view.")
    trigger: str = Field(
        description="What prompted the change (e.g. new evidence, argument, reading).",
        default="",
    )
    changed_on: str = Field(default_factory=_today)


# ── Union type ────────────────────────────────────────────────────────────────

AnyMemory = (
    RelationalMemory
    | EpistemicMemory
    | BehavioralObservation
    | CuriosityRecord
    | PositionRecord
    | ChangeRecord
)


# ── Helpers ───────────────────────────────────────────────────────────────────

import uuid


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
