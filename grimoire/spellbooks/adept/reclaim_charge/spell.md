---
name: "reclaim_charge"
description: "Recover charge after completing a durable unit of ritual work. Recovery must be earned and declared, not silent."
spellbook: "adept"
charge: 0
surface: "machine_local"
status: "active"
---

## What this cast does

Restores a declared amount of charge to the session budget after completing a
meaningful, durable unit of work. The recovery amount must be specified in the
ritual manifest and cannot exceed what was spent.

Charge should not quietly reappear. A ritual either earns recovery under its own
declared conditions or it does not.

## Inputs

- `amount`: int — charge units to recover
- `reason`: string — what durable work was completed to earn recovery

## Rules

- `amount` must be ≤ charge spent in the current run
- Recovery is logged as a `charge_event` in the ledger
- Silent reclamation (without a logged reason) is not permitted

## Charge

`0` — the cast itself is free.

## Implementation

`grimoire/engine/zil/runtime/charge.py` — recovery path (Phase 3/4 addition).
