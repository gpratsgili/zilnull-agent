"""Pipeline Stage 2: Examiner.

Tests both the user's view and ZIL's initial lean against counterarguments,
alternative framings, and required evidence. This stage is adversarial toward
certainty — including ZIL's own.

ZIL is warm toward people, adversarial toward its own certainty.
"""

from __future__ import annotations

from zil.client import get_client, structured_parse
from pydantic import BaseModel, Field

from zil.config import get_config
from zil.pipeline.interpreter import InterpretationArtifact
from zil.runtime.context import SessionContext


class ExaminationArtifact(BaseModel):
    steelman_of_user: str = Field(
        description="The strongest, most charitable version of the user's position."
    )
    counterarguments_to_user: list[str] = Field(
        description="Genuine counterarguments to the user's view.",
        default_factory=list,
    )
    counterarguments_to_zil: list[str] = Field(
        description=(
            "Counterarguments to ZIL's initial lean — "
            "reasons ZIL might be wrong or incomplete."
        ),
        default_factory=list,
    )
    alternative_frames: list[str] = Field(
        description=(
            "Alternative ways to frame the question that the user may not have considered."
        ),
        default_factory=list,
    )
    evidence_needed: list[str] = Field(
        description="What evidence or reasoning would be required to resolve the question.",
        default_factory=list,
    )
    uncertainty_notes: list[str] = Field(
        description=(
            "Specific points where confidence should be lower than it might first appear."
        ),
        default_factory=list,
    )
    zil_initial_lean: str = Field(
        description=(
            "ZIL's tentative current position before full response drafting. "
            "Should be honest and provisional, not authoritative."
        ),
        default="",
    )


def examine(
    user_message: str,
    interpretation: InterpretationArtifact,
    conversation_history: list[dict],
    *,
    run_id: str = "",
    session_context: SessionContext | None = None,
) -> ExaminationArtifact:
    """Run the examiner stage.

    Args:
        user_message: The raw user input.
        interpretation: Output from the interpreter stage.
        conversation_history: Recent turns for context.
        run_id: Propagated for tracking.

    Returns:
        ExaminationArtifact — tested positions, counterarguments, uncertainty.
    """
    cfg = get_config()
    prompt_contract = cfg.read_prompt("examiner")
    system_prompt = (
        session_context.build_minimal_prompt(prompt_contract)
        if session_context is not None
        else prompt_contract
    )

    client = get_client()

    context = (
        f"## User message\n{user_message}\n\n"
        f"## Interpretation artifact\n"
        f"Goal: {interpretation.user_goal}\n"
        f"Claims: {interpretation.user_claims}\n"
        f"Assumptions: {interpretation.assumptions}\n"
        f"Mode: {interpretation.requested_mode}\n"
        f"Ambiguities: {interpretation.ambiguities}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
    ]
    for turn in conversation_history[-4:]:
        messages.append(turn)
    messages.append({"role": "user", "content": context})

    artifact = structured_parse(
        client,
        model=cfg.model,
        messages=messages,
        response_format=ExaminationArtifact,
        temperature=0.3,
    )
    if artifact is None:
        artifact = ExaminationArtifact(
            steelman_of_user=interpretation.user_goal,
            zil_initial_lean="I am uncertain and need more information.",
        )
    return artifact
