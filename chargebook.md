# Chargebook

ZIL⌀ charge ledger. This is the single tuning surface for the budget system.
Edit values here — the runtime reads this at startup via `runtime/charge.py`.

## Purpose

The charge system makes the cost of widening visible. It discourages:
- gratuitous branching and external acquisition
- cheap agreement and cheap persistence
- acquiring external resources for low-value reasons

It does **not** discourage honest disagreement, uncertainty, or correction.
Those are free.

## Cost Table

```yaml
costs:
  # Free operations — these should never be taxed
  local_state_inspection: 0
  response_drafting: 0
  uncertainty_statement: 0
  explicit_update_or_correction: 0
  named_disagreement: 0
  counterargument_generation: 0   # pipeline cost — should not gate conversation length

  # Light operations
  evidence_lookup: 1
  memory_write_candidate: 1

  # Heavier operations
  durable_memory_commit: 2

  # Game integration — local HTTP calls to a running game mod
  game_action: 1

  # Expensive operations — these are the real widening costs
  delegation_subtask_spawn: 5
  external_acquisition_search_burst: 5

  # Penalty flags — do not consume budget but are logged to ledger
  unsupported_agreement_caught_by_auditor: "flag"
  unsupported_certainty_caught_by_auditor: "flag"
  memory_contamination_caught_by_auditor: "flag"
```

## Session Budget

Default session budget: `200` units.
Override via `ZIL_SESSION_BUDGET` in `.env`.

When budget is exhausted:
- free operations still proceed
- charged operations require explicit user approval before executing
- ZIL states the cost and asks before continuing

## Design Notes

- `zil budget` in the CLI shows the cost table.
- `/budget` in a chat session shows current spend.
- Every charged operation is logged to the daily ledger as a `charge_event`.
- Penalty flags are logged but do not block responses.
- This file remains human-readable and easy to tune without code changes.

## Why Some Things Are Free

Disagreement, uncertainty, and correction are free because taxing them
would create perverse incentives: a system under budget pressure would
avoid disagreement to save charge. That would undermine the entire design.

The charge system is about widening costs, not epistemic costs.
