---
name: "relay_to_summoner"
description: "Send the final response text to the user via the foreground thread."
spellbook: "adept"
charge: 0
surface: "machine_local"
status: "active"
---

## What this cast does

Delivers the auditor-approved response to the user and writes the `assistant_turn`
event to the daily ledger.

This is the terminal step of every pipeline run. It only fires after the Auditor
has issued an `allow` decision.

## Inputs

- `text`: string — the final response text
- `run_id`: string — the current run identifier

## Outputs

- Response displayed to the user in the foreground terminal
- `assistant_turn` event appended to `vessel/state/zil/conversations/<date>.jsonl`

## Charge

`0` — sending a response to the user is never taxed. Taxing it would create
perverse incentives: ZIL might withhold responses to preserve budget.

## Permission surface

`machine_local` — writes only to the ledger. Does not touch shared surfaces.

## Implementation

`grimoire/engine/zil/runtime/loop.py` — the `chat_loop` function handles display
and ledger write after `run_turn` returns.
