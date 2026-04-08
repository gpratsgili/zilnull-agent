---
name: "list_spellbooks"
description: "List all spellbooks in grimoire/spellbooks/ and report which are active in the current session."
spellbook: "adept"
charge: 0
surface: "internal"
status: "active"
---

## What this cast does

Reads `grimoire/spellbooks/` and returns the name, description, and active status
of each spellbook. Active means: opened explicitly this session, or always-open (adept).

## Outputs

List of `{ name, description, status: active|available|deferred }`.

## Charge

`0` — discovery is free.

## Implementation

`grimoire/engine/zil/tools/registry.py` — `ToolRegistry.list_available(include_widening_required=True)`
