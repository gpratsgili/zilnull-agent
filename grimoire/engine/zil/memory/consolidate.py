"""Memory consolidation.

Distills unprocessed ledger events into typed memory records and a compact
long-term summary. Safe to run at session end, mid-session, or both — a
cursor at vessel/state/zil/consolidation_cursor.json ensures idempotency.

Cursor structure:
  {"last_date": "2026-04-05", "last_event_index": 42}

Each run only processes ledger events after that cursor position.
After a successful run the cursor advances.
Running consolidation twice produces no new records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

from zil.config import get_config
from zil.memory.models import (
    BehavioralObservation,
    ChangeRecord,
    CuriosityRecord,
    EpistemicMemory,
    PositionRecord,
    RelationalMemory,
)
from zil.memory.store import MemoryStore
from zil.memory.validators import validate_memory
from zil.runtime import ledger as ledger_mod


class ConsolidationSummary(BaseModel):
    epistemic_records: list[EpistemicMemory] = Field(default_factory=list)
    relational_records: list[RelationalMemory] = Field(default_factory=list)
    behavioral_records: list[BehavioralObservation] = Field(default_factory=list)
    curiosity_records: list[CuriosityRecord] = Field(default_factory=list)
    position_records: list[PositionRecord] = Field(default_factory=list)
    change_records: list[ChangeRecord] = Field(default_factory=list)
    long_term_entry: str = Field(
        description="Compact markdown paragraph suitable for long-term.md.",
        default="",
    )


_CONSOLIDATION_SYSTEM_PROMPT = """
You are ZIL⌀'s memory consolidation process. Given a summary of today's
conversation events, extract the most important typed memory records.

Rules:
1. User beliefs must NEVER be stored as world facts. Use truth_status='user_belief'
   for any claim the user made that is not independently verified.
2. Only extract genuinely novel or significant records — skip trivial social exchanges.
3. Behavioral observations should be honest about ZIL's failures, not just its successes.
4. Keep claim_text concise but precise.
5. The long_term_entry should be a compact 2–4 sentence paragraph for the
   long-term.md file. It should capture what was discussed and any significant
   epistemic developments.
6. Curiosity records mark threads ZIL finds genuinely interesting and wants to return to.
   Only extract these when ZIL expressed genuine interest or opened a real question.
7. Position records mark views ZIL arrived at independently through the session.
   Do not extract these for views ZIL stated as established facts — only for positions
   ZIL reasoned its way to.
8. Change records mark when ZIL revised a position it previously held.
   Only extract these when a genuine position change occurred, not just clarification.

You must return a ConsolidationSummary JSON object.
"""


def _read_cursor(cfg) -> dict:
    """Read the consolidation cursor. Returns empty dict if not found."""
    path: Path = cfg.consolidation_cursor_path
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cursor(cfg, cursor: dict) -> None:
    """Persist the consolidation cursor."""
    path: Path = cfg.consolidation_cursor_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursor, indent=2), encoding="utf-8")


def consolidate_session(
    store: MemoryStore | None = None,
    run_id: str = "",
) -> ConsolidationSummary:
    """Consolidate unprocessed ledger events into typed memory records.

    Cursor-based: only processes events after the last cursor position.
    Advances the cursor after a successful run. Idempotent.

    Returns the ConsolidationSummary (may be empty if nothing to process).
    """
    cfg = get_config()
    if store is None:
        store = MemoryStore()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Read cursor ───────────────────────────────────────────────────────
    cursor = _read_cursor(cfg)
    cursor_date = cursor.get("last_date", "")
    cursor_index = cursor.get("last_event_index", -1)

    # ── Read all events from today's ledger ───────────────────────────────
    all_events = ledger_mod.read_today()

    # ── Slice to unprocessed events ───────────────────────────────────────
    if cursor_date == today and cursor_index >= 0:
        # Same day: process only events after the cursor
        unprocessed = all_events[cursor_index + 1:]
    else:
        # New day or no cursor: process everything from today
        unprocessed = all_events

    # ── Filter to conversation turns only ─────────────────────────────────
    turns = [
        e for e in unprocessed
        if e.get("event_type") in ("user_turn", "assistant_turn")
    ]

    if not turns:
        # Nothing new to process — exit cleanly without writing anything
        return ConsolidationSummary()

    # ── Compute where the cursor should land after this run ───────────────
    # Point to the last event in all_events that falls within unprocessed
    last_unprocessed = unprocessed[-1]
    new_cursor_index = len(all_events) - 1
    # Walk backwards to find the exact index of last_unprocessed
    for i in range(len(all_events) - 1, -1, -1):
        if all_events[i].get("turn_id") == last_unprocessed.get("turn_id"):
            new_cursor_index = i
            break

    # ── Build conversation text ───────────────────────────────────────────
    conversation_lines = []
    for t in turns:
        role = "User" if t["event_type"] == "user_turn" else "ZIL"
        text = t.get("payload", {}).get("text", "")
        conversation_lines.append(f"{role}: {text}")

    conversation_text = "\n".join(conversation_lines)

    # ── Call LLM to extract records ───────────────────────────────────────
    client = OpenAI(api_key=cfg.openai_api_key)
    try:
        response = client.beta.chat.completions.parse(
            model=cfg.model,
            messages=[
                {"role": "system", "content": _CONSOLIDATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Today's unprocessed conversation turns:\n\n{conversation_text}\n\n"
                        f"Extract typed memory records and write a long-term entry."
                    ),
                },
            ],
            response_format=ConsolidationSummary,
            temperature=0.2,
        )
    except Exception:
        # If the LLM call fails, do NOT advance the cursor — try again next time
        return ConsolidationSummary()

    summary = response.choices[0].message.parsed
    if summary is None:
        return ConsolidationSummary()

    # ── Validate and write each record ────────────────────────────────────
    committed = 0
    for record in (
        summary.epistemic_records
        + summary.relational_records
        + summary.behavioral_records
        + summary.curiosity_records
        + summary.position_records
        + summary.change_records
    ):
        result = validate_memory(record)
        ledger_mod.append_event(
            "memory_candidate",
            {
                "kind": getattr(record, "kind", "unknown"),
                "passed_validation": result.passed,
                "warnings": result.warnings,
                "errors": result.errors,
                "consolidation": True,
            },
            run_id=run_id,
        )
        if result.passed:
            store.write_window(record)
            committed += 1

    # ── Write long-term entry ─────────────────────────────────────────────
    if summary.long_term_entry.strip():
        store.append_long_term(summary.long_term_entry)

    # ── Advance cursor (only after successful writes) ─────────────────────
    _write_cursor(cfg, {"last_date": today, "last_event_index": new_cursor_index})

    # ── Log completion ────────────────────────────────────────────────────
    ledger_mod.append_event(
        "memory_commit",
        {
            "source": "consolidation",
            "turns_processed": len(turns),
            "records_committed": committed,
            "long_term_updated": bool(summary.long_term_entry.strip()),
            "new_cursor_index": new_cursor_index,
        },
        run_id=run_id,
    )

    return summary
