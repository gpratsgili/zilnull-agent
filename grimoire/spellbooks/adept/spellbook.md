---
name: "adept"
description: "Universal always-open spellbook for ZIL⌀. Active in every run."
---

This spellbook is always open. It cannot be closed.

It holds the minimum surface ZIL needs to function in any context: staying responsive,
acknowledging work, managing memory, reading its own manifests, and stopping safely.

## Active casts (ZIL v1)

| Cast | Charge | Purpose |
|------|-------:|---------|
| `relay_to_summoner` | 0 | Send a response to the user |
| `record_checkpoint` | 0 | Write an internal event to the ledger |
| `halt_activity` | 0 | Stop all activity immediately |
| `list_spellbooks` | 0 | List available spellbooks |
| `open_spellbook` | 0 | Open an optional spellbook for this session |
| `reclaim_charge` | 0 | Recover charge after durable ritual progress |
| `read_memory` | 0 | Read typed memory records from a memory layer |
| `write_memory` | 1 | Propose a validated typed memory record |
| `search_memory` | 1 | Search across memory layers by query |

## Deferred casts (not active in ZIL v1)

These casts exist in the scaffold but are not wired in v1. They are preserved as
documented placeholders so they can be activated without restructuring.

| Cast | Reason deferred |
|------|----------------|
| `codex_emanation` | Requires working/subtask infrastructure |
| `echo_emanation` | Requires working/subtask infrastructure |
| `genius_emanation` | Requires working/subtask infrastructure |
| `kimi_emanation` | Requires working/subtask infrastructure |
| `send_signal` | Requires transport widening |
| `send_user_update` | Covered by relay_to_summoner in v1 |

## Design notes

The adept surface is narrow on purpose. A spirit that needs to widen beyond adept
must open an optional spellbook explicitly. That widening is visible in the session
and logged.

Memory casts are in adept (not a separate memory spellbook) because memory access
is core to ZIL's function on every turn — it is not an optional capability.
