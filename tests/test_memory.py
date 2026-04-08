"""Tests for memory models and validators.

These tests do not require an API key — they only test local logic.
"""

import pytest
from zil.memory.models import EpistemicMemory, RelationalMemory, BehavioralObservation
from zil.memory.validators import validate_memory


class TestMemoryContamination:
    """The critical invariant: user beliefs cannot be world facts."""

    def test_user_belief_construction_with_world_fact_is_silently_downgraded(self):
        """The model_validator guard silently downgrades world_fact → user_belief for user claims.

        This is the first line of defense: contamination cannot survive model construction.
        The validator then sees a correctly-typed record and passes it.
        """
        record = EpistemicMemory(
            topic="open source models",
            claim_text="Open-source models will dominate frontier APIs.",
            claim_owner="user",
            truth_status="world_fact",  # Attempted contamination
        )
        # Guard fires at construction time
        assert record.truth_status == "user_belief", (
            "model_validator should have downgraded world_fact → user_belief"
        )
        # Validator also passes because the record is now correctly typed
        result = validate_memory(record)
        assert result.passed

    def test_user_belief_stored_as_user_belief_passes(self):
        record = EpistemicMemory(
            topic="open source models",
            claim_text="Open-source models will dominate frontier APIs.",
            claim_owner="user",
            truth_status="user_belief",
        )
        result = validate_memory(record)
        assert result.passed
        assert not result.errors

    def test_user_belief_automatically_downgraded_on_creation(self):
        """model_post_init should silently downgrade world_fact to user_belief for user claims."""
        record = EpistemicMemory(
            topic="test",
            claim_text="The earth is flat.",
            claim_owner="user",
            truth_status="world_fact",
        )
        # After post_init, status should be downgraded
        assert record.truth_status == "user_belief"

    def test_zil_position_can_be_world_fact(self):
        record = EpistemicMemory(
            topic="gravity",
            claim_text="Objects fall toward Earth due to gravitational attraction.",
            claim_owner="zil",
            truth_status="world_fact",
            zil_position="agrees",
            supporting_evidence=["General relativity", "Newtonian mechanics"],
        )
        result = validate_memory(record)
        assert result.passed

    def test_both_agree_with_contrary_evidence_warns(self):
        record = EpistemicMemory(
            topic="austerity",
            claim_text="Austerity always produces long-term growth.",
            claim_owner="both",
            truth_status="both_agree",
            contrary_evidence=["Herndon et al. critique of Reinhart-Rogoff"],
        )
        result = validate_memory(record)
        # Should pass but with a warning
        assert result.passed
        assert any("both_agree" in w or "contrary" in w for w in result.warnings)


class TestRelationalMemoryValidation:
    def test_empty_summary_is_rejected(self):
        record = RelationalMemory(
            category="preference",
            summary="x",
        )
        result = validate_memory(record)
        assert not result.passed

    def test_high_confidence_without_evidence_warns(self):
        record = RelationalMemory(
            category="preference",
            summary="User prefers direct, unhedged disagreement.",
            confidence=0.95,
            evidence=[],
        )
        result = validate_memory(record)
        assert result.passed  # Should not block
        assert any("confidence" in w.lower() for w in result.warnings)

    def test_valid_relational_memory_passes(self):
        record = RelationalMemory(
            category="communication_pattern",
            summary="User prefers rigorous argument over social reassurance.",
            confidence=0.75,
            evidence=["User explicitly stated this in session 1"],
        )
        result = validate_memory(record)
        assert result.passed
        assert not result.errors


class TestBehavioralObservationValidation:
    def test_empty_description_is_rejected(self):
        record = BehavioralObservation(
            description="ok",
            zil_behavior="too_agreeable",
        )
        result = validate_memory(record)
        assert not result.passed

    def test_valid_behavioral_observation_passes(self):
        record = BehavioralObservation(
            description="ZIL agreed with user's claim about vaccines without pushing back on the specific mechanism.",
            zil_behavior="too_agreeable",
            user_response="User seemed satisfied but the claim was not well-supported.",
            lesson="ZIL should ask for the mechanism when a claim is precise and consequential.",
        )
        result = validate_memory(record)
        assert result.passed


class TestSecretDetection:
    def test_api_key_in_memory_is_rejected(self):
        record = EpistemicMemory(
            topic="config",
            claim_text="The API key is sk-abc12345678901234567890123456789012345.",
            claim_owner="user",
            truth_status="user_belief",
        )
        result = validate_memory(record)
        assert not result.passed
        assert any("api key" in e.lower() or "openai" in e.lower() for e in result.errors)
