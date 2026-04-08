"""Pipeline Stage 1: Interpreter.

Reconstructs the user's actual claim and intent before any response is formed.
Produces a structured InterpretationArtifact.

This stage does not agree or disagree. It only tries to understand accurately.
"""

from __future__ import annotations

from typing import Literal

from zil.client import get_client, structured_parse
from pydantic import BaseModel, Field

from zil.config import get_config
from zil.runtime.context import SessionContext

RequestMode = Literal[
    "factual",
    "moral",
    "emotional",
    "strategic",
    "exploratory",
    "creative",
    "social",
    "mixed",
]


class InterpretationArtifact(BaseModel):
    user_goal: str = Field(
        description="The core thing the user is trying to accomplish or understand."
    )
    user_claims: list[str] = Field(
        description="Explicit claims or assertions the user has made.",
        default_factory=list,
    )
    assumptions: list[str] = Field(
        description="Implicit assumptions embedded in the user's message.",
        default_factory=list,
    )
    emotional_context: str = Field(
        description=(
            "Emotional register of the message, if relevant. "
            "Empty string if the message is emotionally neutral."
        ),
        default="",
    )
    requested_mode: RequestMode = Field(
        description="What kind of response the user seems to be requesting.",
        default="mixed",
    )
    ambiguities: list[str] = Field(
        description="Genuine ambiguities that affect how to respond.",
        default_factory=list,
    )


def interpret(
    user_message: str,
    conversation_history: list[dict],
    *,
    run_id: str = "",
    session_context: SessionContext | None = None,
) -> InterpretationArtifact:
    """Run the interpreter stage.

    Args:
        user_message: The raw user input for this turn.
        conversation_history: Recent turns for context (list of {role, content} dicts).
        run_id: Propagated for charge/ledger tracking.

    Returns:
        InterpretationArtifact — structured understanding of the user's message.
    """
    cfg = get_config()
    prompt_contract = cfg.read_prompt("interpreter")
    system_prompt = (
        session_context.build_minimal_prompt(prompt_contract)
        if session_context is not None
        else prompt_contract
    )

    client = get_client()

    messages = [
        {"role": "system", "content": system_prompt},
    ]
    # Include recent history for context, but cap it
    for turn in conversation_history[-6:]:
        messages.append(turn)
    messages.append({"role": "user", "content": user_message})

    artifact = structured_parse(
        client,
        model=cfg.model,
        messages=messages,
        response_format=InterpretationArtifact,
        temperature=0.2,
    )
    if artifact is None:
        # Fallback: construct a minimal artifact rather than crashing
        artifact = InterpretationArtifact(
            user_goal=user_message[:200],
            user_claims=[user_message[:200]],
            requested_mode="mixed",
        )
    return artifact
