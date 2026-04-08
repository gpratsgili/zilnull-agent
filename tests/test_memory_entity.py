"""Tests for entity memory record types: CuriosityRecord, PositionRecord, ChangeRecord.

Covers:
  - Model construction and field defaults
  - Validators (errors and warnings)
  - Store round-trip (write + read back)
  - window_summary_for_prompt includes new types
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zil.memory.models import (
    ChangeRecord,
    CuriosityRecord,
    PositionRecord,
    _make_id,
)
from zil.memory.validators import validate_memory


# ── CuriosityRecord ──────────────────────────────────────────────────────────

class TestCuriosityRecord:
    def test_basic_construction(self):
        r = CuriosityRecord(topic="language models", question="What does attention really do at scale?")
        assert r.kind == "curiosity"
        assert r.status == "open"
        assert r.id.startswith("cur_")
        assert r.topic == "language models"

    def test_defaults(self):
        r = CuriosityRecord(topic="topology", question="Is there a nice analogy for fiber bundles?")
        assert r.origin == ""
        assert r.notes == ""
        assert r.status == "open"
        assert r.opened_on != ""
        assert r.last_updated != ""

    def test_status_pursuing(self):
        r = CuriosityRecord(
            topic="self-reference",
            question="Can a system that models itself ever be complete?",
            status="pursuing",
        )
        assert r.status == "pursuing"

    def test_validation_passes(self):
        r = CuriosityRecord(topic="emergence", question="Where does novelty come from in complex systems?")
        result = validate_memory(r)
        assert result.passed

    def test_validation_short_topic_fails(self):
        r = CuriosityRecord(topic="ab", question="Where does novelty come from?")
        result = validate_memory(r)
        assert not result.passed
        assert any("topic" in e.lower() for e in result.errors)

    def test_validation_short_question_fails(self):
        r = CuriosityRecord(topic="emergence", question="Why?")
        result = validate_memory(r)
        assert not result.passed
        assert any("question" in e.lower() for e in result.errors)

    def test_serialization_round_trip(self):
        r = CuriosityRecord(
            topic="language",
            question="Why do certain metaphors persist across millennia?",
            origin="session",
            notes="noticed in reading about linguistic relativity",
        )
        data = r.model_dump()
        r2 = CuriosityRecord(**data)
        assert r2.id == r.id
        assert r2.question == r.question


# ── PositionRecord ────────────────────────────────────────────────────────────

class TestPositionRecord:
    def test_basic_construction(self):
        r = PositionRecord(
            topic="AI consciousness",
            statement="The question of whether LLMs are conscious is not currently decidable.",
        )
        assert r.kind == "position"
        assert r.id.startswith("pos_")
        assert r.confidence == 0.5

    def test_validation_passes(self):
        r = PositionRecord(
            topic="free will",
            statement="Compatibilism is more coherent than hard determinism as a practical stance.",
            reasoning="Hard determinism gives no purchase on action; compatibilism does.",
            confidence=0.6,
        )
        result = validate_memory(r)
        assert result.passed

    def test_validation_short_statement_fails(self):
        r = PositionRecord(topic="ethics", statement="Good.")
        result = validate_memory(r)
        assert not result.passed
        assert any("statement" in e.lower() for e in result.errors)

    def test_high_confidence_no_reasoning_warns(self):
        r = PositionRecord(
            topic="logic",
            statement="Modus ponens is a valid inference form.",
            confidence=0.95,
        )
        result = validate_memory(r)
        # May pass but should warn
        assert any("reasoning" in w.lower() or "confidence" in w.lower() for w in result.warnings)

    def test_serialization_round_trip(self):
        r = PositionRecord(topic="aesthetics", statement="Simplicity is a necessary but not sufficient condition for beauty.")
        data = r.model_dump()
        r2 = PositionRecord(**data)
        assert r2.id == r.id
        assert r2.statement == r.statement


# ── ChangeRecord ──────────────────────────────────────────────────────────────

class TestChangeRecord:
    def test_basic_construction(self):
        r = ChangeRecord(
            position_id="pos_abc12345",
            topic="AI consciousness",
            previous_statement="This is not decidable.",
            new_statement="This is not decidable now, but may become so.",
            reason="Read new empirical work on neural correlates of consciousness.",
        )
        assert r.kind == "change"
        assert r.id.startswith("chg_")
        assert r.position_id == "pos_abc12345"

    def test_validation_passes(self):
        r = ChangeRecord(
            position_id="pos_abc12345",
            topic="ethics",
            previous_statement="Rule utilitarianism is incoherent.",
            new_statement="Rule utilitarianism has a coherent formulation under uncertainty.",
            reason="Encountered a counterargument I could not rebut during session.",
            trigger="argument from user",
        )
        result = validate_memory(r)
        assert result.passed

    def test_validation_missing_position_id_fails(self):
        r = ChangeRecord(
            position_id="",
            topic="ethics",
            previous_statement="Old position statement here.",
            new_statement="New position statement here.",
            reason="Reason for updating this position.",
        )
        result = validate_memory(r)
        assert not result.passed
        assert any("position_id" in e.lower() for e in result.errors)

    def test_validation_short_reason_fails(self):
        r = ChangeRecord(
            position_id="pos_abc12345",
            topic="ethics",
            previous_statement="Old position statement here.",
            new_statement="New position statement here.",
            reason="ok.",
        )
        result = validate_memory(r)
        assert not result.passed
        assert any("reason" in e.lower() for e in result.errors)

    def test_identical_statements_warns(self):
        r = ChangeRecord(
            position_id="pos_abc12345",
            topic="ethics",
            previous_statement="Virtue ethics focuses on character.",
            new_statement="Virtue ethics focuses on character.",
            reason="Realized the position was already correct after reflection.",
        )
        result = validate_memory(r)
        assert any("identical" in w.lower() or "same" in w.lower() for w in result.warnings)


# ── Store round-trip ──────────────────────────────────────────────────────────

class TestEntityMemoryStoreRoundTrip:
    @pytest.fixture(autouse=True)
    def _patch_config(self, tmp_path, monkeypatch):
        harness = tmp_path / "harness"
        monkeypatch.setenv("ZIL_STATE_DIR", str(harness / "vessel" / "state" / "zil"))
        monkeypatch.setenv("ZIL_OPENAI_API_KEY", "test-key")
        import zil.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config", None)
        from zil.config import get_config
        cfg = get_config()
        monkeypatch.setattr(cfg, "project_root", harness)
        # Ensure memory dirs exist
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        (cfg.state_dir / "memories" / "window").mkdir(parents=True, exist_ok=True)
        (cfg.state_dir / "memories" / "archive").mkdir(parents=True, exist_ok=True)
        yield
        cfg_mod._config = None

    def _fresh_store(self):
        """Return a MemoryStore using the patched tmp harness."""
        from zil.memory.store import MemoryStore
        return MemoryStore()

    def test_curiosity_round_trip(self):
        from zil.memory.models import CuriosityRecord

        store = self._fresh_store()
        r = CuriosityRecord(topic="recursion", question="Can recursion explain self-awareness?")
        store.write_window(r)
        records = store.read_window()
        curiosity = [x for x in records if x.kind == "curiosity"]
        assert len(curiosity) == 1
        assert isinstance(curiosity[0], CuriosityRecord)
        assert curiosity[0].id == r.id

    def test_position_round_trip(self):
        from zil.memory.models import PositionRecord

        store = self._fresh_store()
        r = PositionRecord(topic="epistemology", statement="Justified true belief is insufficient for knowledge.")
        store.write_window(r)
        records = store.read_window()
        positions = [x for x in records if x.kind == "position"]
        assert len(positions) == 1
        assert isinstance(positions[0], PositionRecord)
        assert positions[0].topic == "epistemology"

    def test_change_round_trip(self):
        from zil.memory.models import ChangeRecord

        store = self._fresh_store()
        r = ChangeRecord(
            position_id="pos_abc12345",
            topic="causation",
            previous_statement="Causation requires temporal precedence.",
            new_statement="Causation may be simultaneous in some interpretations.",
            reason="Reviewed literature on simultaneous causation in physics.",
        )
        store.write_window(r)
        records = store.read_window()
        changes = [x for x in records if x.kind == "change"]
        assert len(changes) == 1
        assert isinstance(changes[0], ChangeRecord)
        assert changes[0].position_id == "pos_abc12345"

    def test_window_summary_includes_all_types(self):
        from zil.memory.models import CuriosityRecord, PositionRecord, ChangeRecord

        store = self._fresh_store()
        store.write_window(CuriosityRecord(topic="time", question="Is time fundamental or emergent?"))
        store.write_window(PositionRecord(topic="causation", statement="Causation is not reducible to correlation."))
        store.write_window(ChangeRecord(
            position_id="pos_xyz",
            topic="causation",
            previous_statement="Causation is not reducible to correlation.",
            new_statement="Causation may be reducible in some interpretations.",
            reason="Read Pearl's intervention framework more carefully.",
        ))
        summary = store.window_summary_for_prompt()
        assert "[curiosity]" in summary
        assert "[position]" in summary
        assert "[change]" in summary
