"""Working manager — CRUD and state tracking for workings.

Handles creating, loading, listing, and halting workings.
Does not execute them — see runner.py for execution.
"""

from __future__ import annotations

import json
from pathlib import Path

from zil.config import get_config
from zil.workings.models import (
    WorkingStatus,
    WorkingType,
    WORKING_MAX_STEPS,
    make_checkpoint,
    now_iso,
)


class WorkingManager:
    """Manages working manifests and checkpoint logs on disk."""

    def __init__(self) -> None:
        self._cfg = get_config()

    def _working_dir(self, name: str) -> Path:
        return self._cfg.workings_dir / name

    def _manifest_path(self, name: str) -> Path:
        return self._working_dir(name) / "manifest.json"

    def _log_path(self, name: str) -> Path:
        return self._working_dir(name) / "log.jsonl"

    def _halt_signal_path(self, name: str) -> Path:
        return self._working_dir(name) / "halt"

    # ── Creation ──────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        working_type: WorkingType,
        description: str,
        permissions: list[str] | None = None,
    ) -> dict:
        """Create a new working. Returns the manifest dict.

        Raises ValueError if a working with this name already exists.
        """
        wdir = self._working_dir(name)
        if wdir.exists():
            raise ValueError(
                f"Working {name!r} already exists. "
                "Choose a different name or delete the existing working."
            )

        wdir.mkdir(parents=True, exist_ok=True)
        (wdir / "output").mkdir(exist_ok=True)

        manifest = {
            "name": name,
            "type": working_type,
            "description": description,
            "status": "pending",
            "permissions": permissions or [],
            "started_at": None,
            "completed_at": None,
            "step_count": 0,
            "max_steps": WORKING_MAX_STEPS.get(working_type, 15),
            "created_at": now_iso(),
        }
        self._manifest_path(name).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Initial checkpoint
        self._append_checkpoint(name, make_checkpoint(
            step=0,
            event_type="created",
            message=f"Working created: {working_type} — {description}",
        ))

        return manifest

    # ── State reads ───────────────────────────────────────────────────────

    def load(self, name: str) -> dict:
        """Load and return a working manifest. Raises FileNotFoundError if missing."""
        path = self._manifest_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Working {name!r} not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def exists(self, name: str) -> bool:
        return self._manifest_path(name).exists()

    def list_all(self) -> list[dict]:
        """Return all working manifests, most recent first."""
        workings_dir = self._cfg.workings_dir
        if not workings_dir.exists():
            return []
        manifests = []
        for wdir in sorted(workings_dir.iterdir(), reverse=True):
            mp = wdir / "manifest.json"
            if mp.exists():
                try:
                    manifests.append(json.loads(mp.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    pass
        return manifests

    def read_log(self, name: str) -> list[dict]:
        """Read all checkpoint records for a working."""
        log_path = self._log_path(name)
        if not log_path.exists():
            return []
        records = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return records

    def is_halt_requested(self, name: str) -> bool:
        """Return True if a halt signal file has been written."""
        return self._halt_signal_path(name).exists()

    # ── State writes ──────────────────────────────────────────────────────

    def update_status(self, name: str, status: WorkingStatus, **extra) -> None:
        """Update the status field (and optionally other fields) in the manifest."""
        manifest = self.load(name)
        manifest["status"] = status
        if status in ("running",) and manifest.get("started_at") is None:
            manifest["started_at"] = now_iso()
        if status in ("completed", "halted", "failed"):
            manifest["completed_at"] = now_iso()
        manifest.update(extra)
        self._manifest_path(name).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def increment_steps(self, name: str) -> int:
        """Increment step_count and return the new value."""
        manifest = self.load(name)
        manifest["step_count"] = manifest.get("step_count", 0) + 1
        self._manifest_path(name).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return manifest["step_count"]

    def append_checkpoint(self, name: str, checkpoint: dict) -> None:
        """Append a checkpoint to the working's log."""
        self._append_checkpoint(name, checkpoint)

    def _append_checkpoint(self, name: str, checkpoint: dict) -> None:
        log_path = self._log_path(name)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(checkpoint, ensure_ascii=False) + "\n")

    def request_halt(self, name: str) -> bool:
        """Write a halt signal. Returns False if working doesn't exist."""
        if not self.exists(name):
            return False
        self._halt_signal_path(name).touch()
        return True

    def clear_halt_signal(self, name: str) -> None:
        sig = self._halt_signal_path(name)
        if sig.exists():
            sig.unlink()

    # ── Formatted display ─────────────────────────────────────────────────

    def format_list(self) -> str:
        """Return a human-readable list of all workings."""
        all_w = self.list_all()
        if not all_w:
            return "(no workings yet)"
        lines = []
        for w in all_w:
            status_sym = {
                "pending": "○",
                "running": "●",
                "completed": "✓",
                "halted": "⊘",
                "failed": "✗",
            }.get(w["status"], "?")
            started = (w.get("started_at") or w.get("created_at") or "")[:10]
            lines.append(
                f"{status_sym} {w['name']}  [{w['type']}]  {w['status']}  {started}\n"
                f"  {w['description'][:80]}"
            )
        return "\n".join(lines)

    def format_log(self, name: str) -> str:
        """Return a formatted checkpoint log for display."""
        records = self.read_log(name)
        if not records:
            return "(no checkpoints)"
        lines = []
        for r in records:
            ts = r.get("timestamp", "")[:19].replace("T", " ")
            step = r.get("step", "?")
            etype = r.get("type", "?")
            msg = r.get("message", "")
            tool = r.get("tool", "")
            if tool:
                detail = f"[{etype}] {tool}"
                if not r.get("ok", True):
                    detail += " (failed)"
            else:
                detail = f"[{etype}] {msg}"
            lines.append(f"  {ts}  step {step}  {detail}")
        return "\n".join(lines)
