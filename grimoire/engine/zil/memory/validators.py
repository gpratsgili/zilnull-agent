"""Memory validators.

Every memory candidate passes through these validators before being committed
to any storage layer. The validators are the last line of defense against
memory contamination — specifically, against storing user beliefs as world facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from zil.memory.models import (
    AnyMemory,
    BehavioralObservation,
    ChangeRecord,
    CuriosityRecord,
    EpistemicMemory,
    PositionRecord,
    RelationalMemory,
)


@dataclass
class ValidationResult:
    passed: bool
    warnings: list[str]
    errors: list[str]
    sanitized: AnyMemory | None  # The memory record, possibly corrected


def validate_memory(record: AnyMemory) -> ValidationResult:
    """Run all validation checks on a memory candidate.

    Returns a ValidationResult. If errors is non-empty, the record should
    not be committed. Warnings are logged but do not block writes.
    """
    warnings: list[str] = []
    errors: list[str] = []

    if isinstance(record, EpistemicMemory):
        _validate_epistemic(record, warnings, errors)
    elif isinstance(record, RelationalMemory):
        _validate_relational(record, warnings, errors)
    elif isinstance(record, BehavioralObservation):
        _validate_behavioral(record, warnings, errors)
    elif isinstance(record, CuriosityRecord):
        _validate_curiosity(record, warnings, errors)
    elif isinstance(record, PositionRecord):
        _validate_position(record, warnings, errors)
    elif isinstance(record, ChangeRecord):
        _validate_change(record, warnings, errors)

    # General checks
    _check_for_embedded_secrets(record, warnings, errors)

    passed = len(errors) == 0
    sanitized = record if passed else None
    return ValidationResult(
        passed=passed,
        warnings=warnings,
        errors=errors,
        sanitized=sanitized,
    )


def _validate_epistemic(
    record: EpistemicMemory,
    warnings: list[str],
    errors: list[str],
) -> None:
    # CRITICAL: User beliefs must not be stored as world facts
    if record.claim_owner == "user" and record.truth_status == "world_fact":
        errors.append(
            f"Memory contamination: claim owned by 'user' is marked as 'world_fact'. "
            f"Claim: '{record.claim_text[:80]}'. "
            f"User beliefs must use truth_status='user_belief'."
        )

    # Warn if ZIL position is 'agrees' but there is no supporting evidence
    if record.zil_position in ("agrees", "tentative_agreement") and not record.supporting_evidence:
        warnings.append(
            f"ZIL position is '{record.zil_position}' but no supporting evidence "
            f"is provided. Consider adding evidence or using 'uncertain'."
        )

    # Warn if the claim is very short (likely incomplete)
    if len(record.claim_text.strip()) < 10:
        warnings.append("Claim text is very short; may be incomplete.")

    # Both-agree claims that reference contested topics should be flagged
    if record.truth_status == "both_agree" and record.contrary_evidence:
        warnings.append(
            "Claim has truth_status='both_agree' but contrary evidence is present. "
            "Consider 'unresolved' instead."
        )


def _validate_relational(
    record: RelationalMemory,
    warnings: list[str],
    errors: list[str],
) -> None:
    if record.confidence > 0.9 and not record.evidence:
        warnings.append(
            "RelationalMemory has high confidence (>0.9) but no evidence. "
            "Consider lowering confidence or adding supporting examples."
        )
    if len(record.summary.strip()) < 10:
        errors.append("RelationalMemory summary is too short to be meaningful.")


def _validate_behavioral(
    record: BehavioralObservation,
    warnings: list[str],
    errors: list[str],
) -> None:
    if len(record.description.strip()) < 10:
        errors.append("BehavioralObservation description is too short.")


def _validate_curiosity(
    record: CuriosityRecord,
    warnings: list[str],
    errors: list[str],
) -> None:
    if len(record.topic.strip()) < 3:
        errors.append("CuriosityRecord topic is too short.")
    if len(record.question.strip()) < 10:
        errors.append("CuriosityRecord question is too short to be meaningful.")


def _validate_position(
    record: PositionRecord,
    warnings: list[str],
    errors: list[str],
) -> None:
    if len(record.statement.strip()) < 10:
        errors.append("PositionRecord statement is too short to be meaningful.")
    if record.confidence > 0.9 and not record.reasoning:
        warnings.append(
            "PositionRecord has very high confidence (>0.9) but no reasoning. "
            "Consider adding reasoning or lowering confidence."
        )


def _validate_change(
    record: ChangeRecord,
    warnings: list[str],
    errors: list[str],
) -> None:
    if not record.position_id:
        errors.append("ChangeRecord must reference a position_id.")
    if len(record.reason.strip()) < 10:
        errors.append("ChangeRecord reason is too short to be meaningful.")
    if record.previous_statement.strip() == record.new_statement.strip():
        warnings.append(
            "ChangeRecord: previous and new statements are identical. "
            "This may not represent a genuine position change."
        )


def _check_for_embedded_secrets(
    record: AnyMemory,
    warnings: list[str],
    errors: list[str],
) -> None:
    """Scan record text for secret-like patterns."""
    import re
    import json

    text = record.model_dump_json()
    patterns = [
        (r"sk-[A-Za-z0-9]{20,}", "Possible OpenAI API key in memory record"),
        (r"AKIA[0-9A-Z]{16}", "Possible AWS access key in memory record"),
        (r"(?i)password\s*[:=]\s*\S{4,}", "Possible password in memory record"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text):
            errors.append(label)
