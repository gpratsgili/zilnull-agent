---
name: "record_checkpoint"
description: "Write an internal checkpoint event to the shared daily ledger without sending a user-facing message."
spellbook: "adept"
charge: 0
surface: "machine_local"
status: "active"
---

## What this cast does

Appends a structured event to the daily JSONL ledger. Used for audit results,
memory candidates, charge events, and other internal state that should be
preserved in the canonical thread without becoming a user-facing message.

## Inputs

- `event_type`: string — one of `audit_result`, `memory_candidate`, `memory_commit`,
  `tool_call`, `tool_result`, `charge_event`, `error`
- `payload`: object — the event data
- `run_id`: string — the current run identifier

## Outputs

- Event appended to `vessel/state/zil/conversations/<date>.jsonl`

## Charge

`0` — internal bookkeeping must never be taxed. If it were, ZIL would skip
checkpoints to preserve charge, breaking the ledger's integrity.

## Permission surface

`machine_local` — writes only to `vessel/state/zil/`.

## Implementation

`grimoire/engine/zil/runtime/ledger.py` — `append_event(event_type, payload, ...)`
