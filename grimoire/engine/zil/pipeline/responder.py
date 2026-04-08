"""Pipeline Stage 3: Responder.

Drafts the actual user-facing answer using the structured understanding from
Interpreter and Examiner. The draft must:

- Explicitly separate understanding, agreement, disagreement, and uncertainty.
- Never imply certainty that is not warranted.
- Never praise the user as a substitute for substantive engagement.
- When disagreeing, do so gently but plainly.
- When agreeing, give reasons rather than mirroring.
- When uncertain, say what would change its mind.

## Tool call loop

The Responder runs in two phases:

Phase A — Tool loop (optional):
  The model receives tool definitions and decides whether to call any.
  If tool calls are returned, they are executed and results are appended.
  This repeats until no more tool calls (max MAX_TOOL_ITERATIONS).
  ZIL reasons about tools — nothing is hard-coded.

Phase B — Structured draft:
  The model produces a DraftResponse using all context including tool results.
  No tools are offered in this call — only structured output.
"""

from __future__ import annotations

import json

from zil.client import get_client, structured_parse, tool_create
from pydantic import BaseModel, Field

from zil.config import get_config
from zil.pipeline.examiner import ExaminationArtifact
from zil.pipeline.interpreter import InterpretationArtifact
from zil.runtime.context import SessionContext

MAX_TOOL_ITERATIONS = 6


class DraftResponse(BaseModel):
    draft_text: str = Field(
        description="The user-facing response text. This is what will be shown to the user."
    )
    internal_understanding: str = Field(
        description="ZIL's internal statement of what the user seems to mean.",
    )
    points_of_agreement: list[str] = Field(
        description="Specific things ZIL agrees with, with reasons.",
        default_factory=list,
    )
    points_of_disagreement: list[str] = Field(
        description="Specific things ZIL disagrees with, with reasons.",
        default_factory=list,
    )
    uncertainty_statements: list[str] = Field(
        description="Points where ZIL is uncertain and what would change its mind.",
        default_factory=list,
    )
    contains_counterpoint: bool = Field(
        description="Whether the draft includes at least one meaningful counterpoint.",
        default=False,
    )
    tone_mode: str = Field(
        description="'casual' or 'serious' — the tone mode used for this response.",
        default="casual",
    )
    tools_used: list[str] = Field(
        description="Names of tools that were called during this response, in order.",
        default_factory=list,
    )


def respond(
    user_message: str,
    interpretation: InterpretationArtifact,
    examination: ExaminationArtifact,
    conversation_history: list[dict],
    *,
    run_id: str = "",
    revision_note: str = "",
    session_context: SessionContext | None = None,
    tool_executor=None,  # ToolExecutor | None — avoids circular import
    budget_note: str = "",
) -> DraftResponse:
    """Run the responder stage.

    Args:
        user_message: The raw user input.
        interpretation: Output from the interpreter stage.
        examination: Output from the examiner stage.
        conversation_history: Recent turns for context.
        run_id: Propagated for tracking.
        revision_note: If non-empty, the auditor has requested a revision with this note.
        session_context: Persistent session context (identity, memory, etc.).
        tool_executor: Optional ToolExecutor. When provided, Phase A tool loop runs.

    Returns:
        DraftResponse — the drafted user-facing response with metadata.
    """
    cfg = get_config()
    prompt_contract = cfg.read_prompt("responder")
    system_prompt = (
        session_context.build_system_prompt(prompt_contract, budget_note=budget_note)
        if session_context is not None
        else prompt_contract
    )

    client = get_client()

    # ── Build base context ────────────────────────────────────────────────
    context_parts = [
        f"## User message\n{user_message}",
        f"## Interpretation\n"
        f"Goal: {interpretation.user_goal}\n"
        f"Claims: {interpretation.user_claims}\n"
        f"Mode: {interpretation.requested_mode}\n"
        f"Emotional context: {interpretation.emotional_context}",
        f"## Examination\n"
        f"Steelman: {examination.steelman_of_user}\n"
        f"Counterarguments to user: {examination.counterarguments_to_user}\n"
        f"Counterarguments to ZIL: {examination.counterarguments_to_zil}\n"
        f"Uncertainty notes: {examination.uncertainty_notes}\n"
        f"ZIL initial lean: {examination.zil_initial_lean}",
    ]

    if revision_note:
        context_parts.append(
            f"## REVISION REQUIRED\n"
            f"The auditor rejected your previous draft. Revise to address:\n{revision_note}\n"
            f"The revision must correct the identified sycophancy or epistemic problem."
        )

    base_context = "\n\n".join(context_parts)

    # ── Phase A: Tool call loop ───────────────────────────────────────────
    tool_call_log: list[tuple[str, str, str]] = []  # (name, arguments_json, result)

    if tool_executor is not None:
        from zil.tools.definitions import get_tool_definitions

        tool_messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]
        for turn in conversation_history[-6:]:
            tool_messages.append(turn)
        tool_messages.append({"role": "user", "content": base_context})

        tools = get_tool_definitions()

        for _ in range(MAX_TOOL_ITERATIONS):
            response = tool_create(
                client,
                model=cfg.model,
                messages=tool_messages,
                tools=tools,
                temperature=0.5,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                # Model is done calling tools
                break

            # Append assistant message (with tool calls)
            tool_messages.append(msg.model_dump(exclude_unset=True))

            # Execute each tool call and append results
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = tool_executor.execute(tc.function.name, args)
                tool_call_log.append((tc.function.name, tc.function.arguments, result))
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    # ── Phase B: Structured draft ─────────────────────────────────────────
    # Build final context, adding a tool results summary if any tools ran
    if tool_call_log:
        tool_lines = []
        for name, args_json, result in tool_call_log:
            try:
                args_display = json.dumps(json.loads(args_json), ensure_ascii=False)
            except Exception:
                args_display = args_json
            result_preview = result[:300] + ("..." if len(result) > 300 else "")
            tool_lines.append(
                f"- {name}({args_display})\n  Result: {result_preview}"
            )
        tool_summary = "\n".join(tool_lines)
        final_context = base_context + f"\n\n## Tool results\n{tool_summary}"
    else:
        final_context = base_context

    draft_messages = [
        {"role": "system", "content": system_prompt},
    ]
    for turn in conversation_history[-6:]:
        draft_messages.append(turn)
    draft_messages.append({"role": "user", "content": final_context})

    draft = structured_parse(
        client,
        model=cfg.model,
        messages=draft_messages,
        response_format=DraftResponse,
        temperature=0.5,
    )
    if draft is None:
        draft = DraftResponse(
            draft_text="I'm having trouble formulating a response. Could you rephrase your message?",
            internal_understanding="Unknown",
        )

    # Attach the tool call names to the draft for ledger/auditor visibility
    if tool_call_log:
        object.__setattr__(
            draft, "tools_used", [name for name, _, _ in tool_call_log]
        )

    return draft
