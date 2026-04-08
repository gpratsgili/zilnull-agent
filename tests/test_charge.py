"""Tests for the charge tracking system (no API required)."""

import pytest
from unittest.mock import patch
from zil.runtime.charge import ChargeTracker, BudgetExceeded


class TestChargeTracker:
    def setup_method(self):
        # Patch ledger to avoid file I/O during tests
        self.ledger_patch = patch("zil.runtime.charge.ledger_mod.append_event")
        self.ledger_patch.start()

    def teardown_method(self):
        self.ledger_patch.stop()

    def test_free_operations_do_not_consume_budget(self):
        tracker = ChargeTracker()
        initial = tracker.remaining
        tracker.charge("local_state_inspection")
        tracker.charge("response_drafting")
        tracker.charge("uncertainty_statement")
        assert tracker.remaining == initial
        assert tracker.spent == 0

    def test_charged_operations_reduce_budget(self):
        tracker = ChargeTracker()
        tracker.charge("evidence_lookup")
        assert tracker.spent == 1
        assert tracker.remaining == tracker._budget - 1

    def test_budget_exceeded_raises(self):
        tracker = ChargeTracker()
        tracker._budget = 2
        tracker.charge("evidence_lookup")  # costs 1
        tracker.charge("evidence_lookup")  # costs 1, now at 2
        with pytest.raises(BudgetExceeded):
            tracker.charge("evidence_lookup")  # would exceed

    def test_penalty_flags_do_not_consume_budget(self):
        tracker = ChargeTracker()
        initial = tracker.remaining
        tracker.flag_penalty("unsupported_agreement", "test reason")
        assert tracker.remaining == initial

    def test_summary_returns_correct_values(self):
        tracker = ChargeTracker()
        tracker.charge("memory_write_candidate")  # costs 1
        summary = tracker.summary()
        assert summary["spent"] == 1
        assert summary["remaining"] == summary["budget"] - 1

    def test_cost_of_known_operations(self):
        tracker = ChargeTracker()
        assert tracker.cost_of("local_state_inspection") == 0
        assert tracker.cost_of("counterargument_generation") == 0
        assert tracker.cost_of("evidence_lookup") == 1
        assert tracker.cost_of("durable_memory_commit") == 2
        assert tracker.cost_of("delegation_subtask_spawn") == 5
        assert tracker.cost_of("external_acquisition_search_burst") == 5

    def test_unknown_operation_costs_zero(self):
        tracker = ChargeTracker()
        assert tracker.cost_of("nonexistent_operation") == 0
