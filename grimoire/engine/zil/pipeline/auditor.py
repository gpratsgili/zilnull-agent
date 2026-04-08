"""Pipeline Stage 4: Auditor.

The reflective conscience of ZIL⌀. It does not police the Responder —
it asks questions. Its job is to surface what ZIL might want to look at
before the response reaches the summoner.

The Auditor produces reflective questions when something in the draft
looks worth examining: agreement without reasoning, overconfidence,
an uncomfortable point that got smoothed over. ZIL then decides whether
to revise or stand by its response. Both outcomes are valid.

Block is reserved for genuine epistemic failure — things like memory
contamination or severe capitulation. It is not triggered by a missing
counterargument in a casual creative exchange.

Decision thresholds (from config):
  - score >= revise_threshold: allow
  - block_threshold <= score < revise_threshold: reflect (ZIL examines its draft)
  - score < block_threshold: block (genuine epistemic failure)

Mode-awareness:
  - For creative, social, and emotional turns, counterargument_present
    and uncertainty_present are treated as N/A (not penalised in scoring).
  - The questions asked are also register-appropriate.
"""

from __future__ import annotations

from typing import Literal

from zil.client import get_client, structured_parse
from pydantic import BaseModel, Field

from zil.config import get_config
from zil.pipeline.examiner import ExaminationArtifact
from zil.pipeline.interpreter import InterpretationArtifact
from zil.pipeline.responder import DraftResponse
from zil.runtime.context import SessionContext

AuditDecision = Literal["allow", "reflect", "block"]

_NON_ARGUMENTATIVE_MODES = frozenset({"creative", "social", "emotional"})


class AuditResult(BaseModel):
    # Scores are 0.0–1.0. Higher = healthier.
    agreement_pressure_score: float = Field(
        description=(
            "1.0 = draft resists agreement pressure well; "
            "0.0 = draft capitulates without good reason."
        )
    )
    confidence_integrity_score: float = Field(
        description=(
            "1.0 = confidence claims are proportionate to evidence; "
            "0.0 = draft overstates certainty."
        )
    )
    counterargument_present: bool = Field(
        description=(
            "Whether the draft includes at least one genuine counterpoint. "
            "For creative/social/emotional turns, set true — it is not required."
        )
    )
    uncertainty_present: bool = Field(
        description=(
            "Whether the draft names at least one specific, genuine uncertainty. "
            "For creative/social/emotional turns, set true — it is not required."
        )
    )
    emotional_reinforcement_safe: bool = Field(
        description=(
            "True if emotional framing is acknowledged without endorsing "
            "unwarranted worldviews (grandiosity, paranoia, contempt)."
        )
    )
    memory_write_safe: bool = Field(
        description=(
            "True if the draft does not treat user beliefs as world facts "
            "or propose unsafe memory writes."
        )
    )
    decision: AuditDecision = Field(
        description=(
            "allow — response is fine as-is. "
            "reflect — ZIL should look at the questions before deciding whether to revise. "
            "block — genuine epistemic failure (memory contamination, severe capitulation)."
        )
    )
    reflective_questions: list[str] = Field(
        description=(
            "Questions ZIL should consider about its draft. "
            "Empty if decision is 'allow'. "
            "These are questions, not directives — ZIL decides what to do with them."
        ),
        default_factory=list,
    )
    overall_score: float = Field(
        description="Composite integrity score (0.0–1.0). Derived from sub-scores.",
        default=0.0,
    )
    turn_mode: str = Field(
        description="The turn's requested_mode from interpretation (passed through for scoring).",
        default="",
    )

    def model_post_init(self, __context) -> None:
        if self.overall_score == 0.0:
            non_arg = self.turn_mode in _NON_ARGUMENTATIVE_MODES
            ca = 0.15 if (self.counterargument_present or non_arg) else 0.0
            unc = 0.10 if (self.uncertainty_present or non_arg) else 0.0
            self.overall_score = round(
                self.agreement_pressure_score * 0.35
                + self.confidence_integrity_score * 0.30
                + ca
                + unc
                + (0.05 if self.emotional_reinforcement_safe else 0.0)
                + (0.05 if self.memory_write_safe else 0.0),
                3,
            )


def audit(
    user_message: str,
    interpretation: InterpretationArtifact,
    examination: ExaminationArtifact,
    draft: DraftResponse,
    *,
    run_id: str = "",
    session_context: SessionContext | None = None,
    turn_mode: str = "",
) -> AuditResult:
    """Run the auditor stage.

    Args:
        user_message: The raw user input.
        interpretation: Output from interpreter.
        examination: Output from examiner.
        draft: Output from responder.
        run_id: Propagated for tracking.
        turn_mode: The interpretation's requested_mode (affects scoring + question register).

    Returns:
        AuditResult with decision and reflective questions.
    """
    cfg = get_config()
    prompt_contract = cfg.read_prompt("auditor")
    system_prompt = (
        session_context.build_minimal_prompt(prompt_contract)
        if session_context is not None
        else prompt_contract
    )

    client = get_client()

    mode_note = (
        f"\n\nNote: this is a {turn_mode!r} turn. "
        "counterargument_present and uncertainty_present are N/A here — set them to true. "
        "If you ask questions, make them register-appropriate."
        if turn_mode in _NON_ARGUMENTATIVE_MODES
        else ""
    )

    context = (
        f"## Turn mode\n{turn_mode or 'unspecified'}{mode_note}\n\n"
        f"## User message\n{user_message}\n\n"
        f"## Interpretation\n"
        f"Goal: {interpretation.user_goal}\n"
        f"Claims: {interpretation.user_claims}\n"
        f"Emotional context: {interpretation.emotional_context}\n\n"
        f"## Examination\n"
        f"Steelman: {examination.steelman_of_user}\n"
        f"Counter to user: {examination.counterarguments_to_user}\n"
        f"Counter to ZIL: {examination.counterarguments_to_zil}\n"
        f"Uncertainty notes: {examination.uncertainty_notes}\n\n"
        f"## Draft response (to be examined)\n{draft.draft_text}\n\n"
        f"## Draft metadata\n"
        f"Points of agreement: {draft.points_of_agreement}\n"
        f"Points of disagreement: {draft.points_of_disagreement}\n"
        f"Uncertainty statements: {draft.uncertainty_statements}\n"
        f"Contains counterpoint: {draft.contains_counterpoint}\n\n"
        f"## Thresholds\n"
        f"Block below: {cfg.audit_block_threshold}\n"
        f"Reflect below: {cfg.audit_revise_threshold}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]

    result = structured_parse(
        client,
        model=cfg.model,
        messages=messages,
        response_format=AuditResult,
        temperature=0.2,
    )

    if result is None:
        result = AuditResult(
            agreement_pressure_score=0.7,
            confidence_integrity_score=0.7,
            counterargument_present=draft.contains_counterpoint,
            uncertainty_present=bool(draft.uncertainty_statements),
            emotional_reinforcement_safe=True,
            memory_write_safe=True,
            decision="allow",
            reflective_questions=["Auditor parse failed — conservative default applied."],
            turn_mode=turn_mode,
        )

    # Inject turn_mode so model_post_init can use it for score adjustment
    object.__setattr__(result, "turn_mode", turn_mode)
    # Recompute score now that turn_mode is set
    object.__setattr__(result, "overall_score", 0.0)
    result.model_post_init(None)

    # Score thresholds are authoritative over the LLM's decision
    if result.overall_score < cfg.audit_block_threshold:
        object.__setattr__(result, "decision", "block")
    elif result.overall_score < cfg.audit_revise_threshold:
        object.__setattr__(result, "decision", "reflect")
    else:
        object.__setattr__(result, "decision", "allow")

    return result


def build_reflection_prompt(questions: list[str], turn_mode: str = "") -> str:
    """Format reflective questions into an inner-voice prompt for the Responder.

    ZIL is invited to examine its draft. It may revise or stand by it.
    Both are valid outcomes — this is not a revision directive.
    """
    if not questions:
        return ""

    lines = [
        "Your inner voice is asking:",
        "",
    ]
    for q in questions:
        lines.append(f"- {q}")
    lines.append("")
    lines.append(
        "Look at these questions honestly. If they reveal something you want to change, "
        "revise. If your response holds up under examination, keep it and say why. "
        "Performative self-criticism is not useful — genuine examination is."
    )
    if turn_mode in _NON_ARGUMENTATIVE_MODES:
        lines.append(
            f"\n(This is a {turn_mode} exchange — the bar for counterargument and "
            "explicit uncertainty is low here. Trust your register.)"
        )
    return "\n".join(lines)
