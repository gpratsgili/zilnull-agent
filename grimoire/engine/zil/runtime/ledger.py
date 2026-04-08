"""Daily conversation ledger.

Every inbound and outbound turn, audit decision, memory candidate/commit,
tool call, and error is appended here as a JSONL event. The ledger is
append-only. We never delete or rewrite entries.

File location: vessel/state/zil/conversations/<YYYY-MM-DD>-<run_id[:8]>.jsonl

Each session gets its own file. read_today() merges all files for the
current date so consolidation and recent_turns() see a unified view.
Old single-file ledgers (YYYY-MM-DD.jsonl) are matched by the same glob.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import orjson

from zil.config import get_config

EventType = Literal[
    "user_turn",
    "assistant_turn",
    "audit_result",
    "memory_candidate",
    "memory_commit",
    "tool_call",
    "tool_result",
    "charge_event",
    "error",
    "session_start",
    "session_end",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger_path(run_id: str | None = None) -> Path:
    cfg = get_config()
    cfg.conversations_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if run_id:
        return cfg.conversations_dir / f"{date_str}-{run_id[:8]}.jsonl"
    return cfg.conversations_dir / f"{date_str}.jsonl"


def append_event(
    event_type: EventType,
    payload: dict[str, Any],
    *,
    spirit: str = "zil",
    run_id: str | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    """Append one event to the session ledger. Returns the written event dict."""
    event: dict[str, Any] = {
        "timestamp": _now_iso(),
        "event_type": event_type,
        "spirit": spirit,
        "run_id": run_id or "",
        "turn_id": turn_id or str(uuid.uuid4()),
        "payload": payload,
    }
    path = _ledger_path(run_id)
    with path.open("ab") as fh:
        fh.write(orjson.dumps(event))
        fh.write(b"\n")
    return event


def read_today() -> list[dict[str, Any]]:
    """Return all events from today's ledger files, merged in chronological order.

    Matches both per-session files (YYYY-MM-DD-<run_id[:8]>.jsonl) and any
    legacy single-file ledgers (YYYY-MM-DD.jsonl).
    """
    cfg = get_config()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    paths = sorted(cfg.conversations_dir.glob(f"{date_str}*.jsonl"))
    events = []
    for path in paths:
        with path.open("rb") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(orjson.loads(line))
    return events


def recent_turns(n: int = 8) -> list[dict[str, Any]]:
    """Return the last n user/assistant turns from today's ledger."""
    events = read_today()
    turns = [
        e for e in events if e["event_type"] in ("user_turn", "assistant_turn")
    ]
    return turns[-n:]
