"""Working data models.

A working is a named, scoped task ZIL runs outside the conversation loop.
Every working has a manifest (current state) and an append-only checkpoint log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

WorkingStatus = Literal["pending", "running", "completed", "halted", "failed"]

WorkingType = Literal["reflection", "research", "creative", "corpus_read", "questbook_work"]

# Tools available per working type. Research requires web permission widening.
WORKING_TOOL_SETS: dict[str, list[str]] = {
    "reflection": [
        "read_curiosity_log",
        "write_curiosity_log",
        "read_self",
        "write_self",
        "list_memory_files",
        "read_memory_file",
        "search_memory",
        "write_inner_note",
        "read_inner_note",
        "list_inner_notes",
        "list_zil_questbook",
        "read_zil_quest",
        "list_rituals",
        "read_ritual",
    ],
    "questbook_work": [
        "list_zil_questbook",
        "read_zil_quest",
        "write_zil_quest",
        "write_curiosity_log",
        "write_inner_note",
        "read_inner_note",
        "list_inner_notes",
        "read_self",
        "write_self",
        "search_memory",
        "read_artifact",
        "list_artifacts",
    ],
    "creative": [
        "write_inner_note",
        "read_inner_note",
        "list_inner_notes",
        "write_curiosity_log",
        "read_curiosity_log",
        "read_self",
        "write_self",
        "list_zil_questbook",
        "read_zil_quest",
        "write_zil_quest",
        "write_creative_work",
        "read_creative_work",
        "list_creative_works",
        "update_creative_index",
        "read_creative_index",
        "search_corpus",
        "read_corpus_file",
        "list_corpus_files",
        "search_memory",
    ],
    "corpus_read": [
        "list_corpus_files",
        "read_corpus_file",
        "search_corpus",
        "write_inner_note",
        "read_inner_note",
        "list_inner_notes",
        "write_curiosity_log",
        "read_curiosity_log",
        "read_self",
        "write_self",
        "list_zil_questbook",
        "write_zil_quest",
    ],
    "research": [
        "web_search",
        "fetch_page",
        "download_pdf",
        "trace_links",
        "enshrine_snapshot",
        "create_artifact",
        "read_artifact",
        "edit_artifact",
        "list_artifacts",
        "search_artifacts",
        "search_corpus",
        "read_corpus_file",
        "ingest_corpus_file",
        "write_curiosity_log",
        "write_inner_note",
        "write_zil_quest",
        "read_self",
        "write_self",
    ],
}

# Max LLM steps per working type before auto-completing
WORKING_MAX_STEPS: dict[str, int] = {
    "reflection": 12,
    "questbook_work": 10,
    "creative": 15,
    "corpus_read": 15,
    "research": 20,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_checkpoint(
    step: int,
    event_type: str,
    message: str = "",
    tool: str = "",
    args: dict | None = None,
    ok: bool = True,
) -> dict:
    """Build a checkpoint record for the working log."""
    record: dict = {
        "timestamp": now_iso(),
        "step": step,
        "type": event_type,
    }
    if message:
        record["message"] = message
    if tool:
        record["tool"] = tool
    if args is not None:
        record["args"] = args
    if not ok:
        record["ok"] = False
    return record
