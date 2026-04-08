"""Memory storage layer.

Manages read/write of typed memory records across the three storage layers:
  - window/   : rolling recent context (recency-focused)
  - long-term.md : compact high-signal summaries (always loaded)
  - archive/  : lower-signal retained residue (searchable, not prompt-attached)

Records are stored as JSONL files within each layer.
Memory writes must pass through validators.py before landing here.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Union

import orjson

from zil.config import get_config
from zil.memory.models import (
    AnyMemory,
    BehavioralObservation,
    ChangeRecord,
    CuriosityRecord,
    EpistemicMemory,
    PositionRecord,
    RelationalMemory,
)
from zil.memory.validators import validate_memory


class MemoryStore:
    """File-based memory store with three layers."""

    def __init__(self) -> None:
        cfg = get_config()
        self._memories_dir = cfg.memories_dir
        self._window_dir = self._memories_dir / "window"
        self._archive_dir = self._memories_dir / "archive"
        self._long_term_path = self._memories_dir / "long-term.md"
        self._window_jsonl = self._window_dir / "recent.jsonl"
        self._archive_jsonl = self._archive_dir / "records.jsonl"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self._window_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    # ── Candidate proposal ────────────────────────────────────────────────────

    def propose(self, record: AnyMemory) -> tuple[bool, list[str], list[str]]:
        """Validate a memory candidate. Does NOT write it.

        Returns (passed, warnings, errors).
        """
        result = validate_memory(record)
        return result.passed, result.warnings, result.errors

    # ── Window memory ─────────────────────────────────────────────────────────

    def write_window(self, record: AnyMemory) -> None:
        """Write a record to window memory (rolling recent context)."""
        result = validate_memory(record)
        if not result.passed:
            raise ValueError(f"Memory validation failed: {result.errors}")
        self._append_jsonl(self._window_jsonl, record)

    def read_window(self) -> list[AnyMemory]:
        """Read all records from window memory."""
        return self._read_jsonl(self._window_jsonl)

    def trim_window(self, max_records: int = 50) -> int:
        """Keep only the most recent max_records in window memory. Returns removed count."""
        records = self.read_window()
        if len(records) <= max_records:
            return 0
        trimmed = records[-max_records:]
        removed = len(records) - len(trimmed)
        self._window_jsonl.write_bytes(b"")
        for r in trimmed:
            self._append_jsonl(self._window_jsonl, r)
        return removed

    # ── Archive memory ────────────────────────────────────────────────────────

    def write_archive(self, record: AnyMemory) -> None:
        """Write a record to archive memory (lower-signal, searchable)."""
        result = validate_memory(record)
        if not result.passed:
            raise ValueError(f"Memory validation failed: {result.errors}")
        self._append_jsonl(self._archive_jsonl, record)

    def read_archive(self) -> list[AnyMemory]:
        """Read all records from archive memory."""
        return self._read_jsonl(self._archive_jsonl)

    # ── Long-term memory (markdown) ───────────────────────────────────────────

    def read_long_term(self) -> str:
        """Read the long-term memory markdown file."""
        if not self._long_term_path.exists():
            return ""
        return self._long_term_path.read_text(encoding="utf-8")

    def append_long_term(self, entry: str) -> None:
        """Append a formatted entry to the long-term memory markdown file."""
        today = date.today().isoformat()
        text = f"\n## {today}\n\n{entry.strip()}\n"
        with self._long_term_path.open("a", encoding="utf-8") as fh:
            fh.write(text)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, layer: str = "all") -> list[AnyMemory]:
        """Simple substring search across memory layers.

        Args:
            query: Substring to search for (case-insensitive).
            layer: 'window', 'archive', or 'all'.
        """
        q = query.lower()
        results = []
        if layer in ("window", "all"):
            for r in self.read_window():
                if q in r.model_dump_json().lower():
                    results.append(r)
        if layer in ("archive", "all"):
            for r in self.read_archive():
                if q in r.model_dump_json().lower():
                    results.append(r)
        return results

    # ── Window summary for prompt context ─────────────────────────────────────

    def window_summary_for_prompt(self, max_records: int = 20) -> str:
        """Return a compact text summary of recent window memory for injection into prompts."""
        records = self.read_window()[-max_records:]
        if not records:
            return "(no recent memory)"
        lines = []
        for r in records:
            if isinstance(r, EpistemicMemory):
                lines.append(
                    f"[epistemic] {r.topic}: {r.claim_text[:80]} "
                    f"(owner={r.claim_owner}, status={r.truth_status}, zil={r.zil_position})"
                )
            elif isinstance(r, RelationalMemory):
                lines.append(f"[relational] {r.category}: {r.summary[:80]}")
            elif isinstance(r, BehavioralObservation):
                lines.append(f"[behavioral] {r.zil_behavior}: {r.description[:80]}")
            elif isinstance(r, CuriosityRecord):
                lines.append(f"[curiosity] {r.topic} ({r.status}): {r.question[:80]}")
            elif isinstance(r, PositionRecord):
                lines.append(
                    f"[position] {r.topic} (conf={r.confidence:.2f}): {r.statement[:80]}"
                )
            elif isinstance(r, ChangeRecord):
                lines.append(
                    f"[change] {r.topic}: revised position {r.position_id} — {r.reason[:80]}"
                )
        return "\n".join(lines)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _append_jsonl(self, path: Path, record: AnyMemory) -> None:
        with path.open("ab") as fh:
            fh.write(record.model_dump_json().encode())
            fh.write(b"\n")

    def _read_jsonl(self, path: Path) -> list[AnyMemory]:
        if not path.exists():
            return []
        records = []
        with path.open("rb") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                    kind = data.get("kind")
                    if kind == "relational":
                        records.append(RelationalMemory(**data))
                    elif kind == "epistemic":
                        records.append(EpistemicMemory(**data))
                    elif kind == "behavioral":
                        records.append(BehavioralObservation(**data))
                    elif kind == "curiosity":
                        records.append(CuriosityRecord(**data))
                    elif kind == "position":
                        records.append(PositionRecord(**data))
                    elif kind == "change":
                        records.append(ChangeRecord(**data))
                except Exception:
                    pass  # Skip malformed records
        return records
