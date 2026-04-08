---
name: "open_spellbook"
description: "Activate an optional spellbook for the rest of the current session, widening ZIL's capability surface."
spellbook: "adept"
charge: 0
surface: "internal"
status: "active"
---

## What this cast does

Registers the casts of the named spellbook as available for the current session.
Widening is explicit — it does not persist across sessions unless configured.

## Inputs

- `name`: string — the spellbook to open (e.g. `"artifact"`, `"web"`)

## Rules

- Only spellbooks listed in `identity.md` under `available_spellbooks` may be opened
- The `adept` spellbook cannot be closed
- External spellbooks (web, network) additionally require warden permission widening

## Charge

`0` — the cast itself is free; the casts it unlocks carry their own costs.

## Implementation

`grimoire/engine/zil/tools/registry.py` + `grimoire/engine/zil/runtime/permissions.py`
