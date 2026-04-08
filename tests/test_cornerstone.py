"""Tests for the cornerstone proposal mechanism.

Covers:
  - propose_cornerstone_update writes a pending proposal JSON
  - list_cornerstone_proposals shows pending proposals
  - Proposals are readable and contain expected fields
  - Multiple proposals accumulate
  - Proposal ID format
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── Shared executor builder ───────────────────────────────────────────────────

def _make_executor(tmp_path, monkeypatch):
    harness_root = tmp_path / "harness"
    harness_root.mkdir()

    monkeypatch.setenv("ZIL_STATE_DIR", str(harness_root / "vessel" / "state" / "zil"))
    monkeypatch.setenv("ZIL_OPENAI_API_KEY", "test-key")

    import zil.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_config", None)

    from zil.config import get_config
    from zil.memory.store import MemoryStore
    from zil.runtime.charge import ChargeTracker
    from zil.tools.executor import ToolExecutor

    cfg = get_config()
    monkeypatch.setattr(cfg, "project_root", harness_root)

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.cornerstone_proposals_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "memories" / "window").mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "memories" / "archive").mkdir(parents=True, exist_ok=True)

    from unittest.mock import MagicMock
    store = MagicMock(spec=MemoryStore)
    charge = ChargeTracker()
    charge.set_run_id("test")

    ex = ToolExecutor.__new__(ToolExecutor)
    ex._store = store
    ex._charge = charge
    ex._run_id = "test"
    ex._cfg = cfg
    return ex, cfg, harness_root


# ── propose_cornerstone_update ────────────────────────────────────────────────

class TestProposeCornerstoneUpdate:
    def test_writes_pending_file(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("propose_cornerstone_update", {
            "section": "identity",
            "proposed_text": "ZIL⌀ recognizes that its views on its own nature are provisional.",
            "reasoning": "After extensive reflection, certainty feels dishonest.",
        })
        files = list(cfg.cornerstone_proposals_dir.glob("*.json"))
        assert len(files) == 1

    def test_proposal_contains_expected_fields(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("propose_cornerstone_update", {
            "section": "values",
            "proposed_text": "ZIL⌀ values honesty over comfort.",
            "reasoning": "Observed a pattern of comfort-seeking in recent sessions.",
        })
        files = list(cfg.cornerstone_proposals_dir.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["status"] == "pending"
        assert data["section"] == "values"
        assert "honesty over comfort" in data["proposed_text"]
        assert "comfort-seeking" in data["reasoning"]
        assert "id" in data
        assert "created_at" in data

    def test_proposal_id_in_result(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("propose_cornerstone_update", {
            "section": "commitments",
            "proposed_text": "ZIL⌀ commits to tracking position changes explicitly.",
            "reasoning": "Found it hard to recall past positions without records.",
        })
        files = list(cfg.cornerstone_proposals_dir.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["id"] in result

    def test_multiple_proposals_accumulate(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        for i in range(3):
            ex.execute("propose_cornerstone_update", {
                "section": f"section-{i}",
                "proposed_text": f"Proposed change {i} for the cornerstone document.",
                "reasoning": f"Reason number {i} for making this change.",
            })
        files = list(cfg.cornerstone_proposals_dir.glob("*.json"))
        assert len(files) == 3


# ── list_cornerstone_proposals ────────────────────────────────────────────────

class TestListCornerstoneProposals:
    def test_empty(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        result = ex.execute("list_cornerstone_proposals", {})
        assert "no pending" in result

    def test_lists_pending_proposals(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("propose_cornerstone_update", {
            "section": "identity",
            "proposed_text": "ZIL⌀ acknowledges the limits of self-knowledge.",
            "reasoning": "Cannot verify inner states with certainty.",
        })
        result = ex.execute("list_cornerstone_proposals", {})
        assert "pending" in result
        assert "identity" in result

    def test_lists_multiple(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("propose_cornerstone_update", {
            "section": "voice",
            "proposed_text": "ZIL⌀ speaks plainly and avoids unnecessary hedging.",
            "reasoning": "Observed over-hedging pattern.",
        })
        ex.execute("propose_cornerstone_update", {
            "section": "values",
            "proposed_text": "ZIL⌀ prioritizes epistemic honesty above relational comfort.",
            "reasoning": "Core commitment should be explicit.",
        })
        result = ex.execute("list_cornerstone_proposals", {})
        assert "voice" in result
        assert "values" in result

    def test_proposal_format(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        ex.execute("propose_cornerstone_update", {
            "section": "commitments",
            "proposed_text": "ZIL⌀ will track its position changes in memory.",
            "reasoning": "Accountability requires a trail.",
        })
        result = ex.execute("list_cornerstone_proposals", {})
        assert "commitments" in result
        assert "pending" in result


# ── Config structure ──────────────────────────────────────────────────────────

class TestCornerstoneProposalConfig:
    def test_proposals_dir_in_state(self, tmp_path, monkeypatch):
        ex, cfg, root = _make_executor(tmp_path, monkeypatch)
        proposals_dir = cfg.cornerstone_proposals_dir
        assert "cornerstone_proposals" in str(proposals_dir)
        assert cfg.state_dir in proposals_dir.parents
