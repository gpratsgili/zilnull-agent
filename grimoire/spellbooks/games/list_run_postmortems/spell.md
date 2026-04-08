---
name: "list_run_postmortems"
description: "List all recorded run postmortems for a game."
---
Returns a list of postmortem files in `spirits/zil/games/<game_id>/runs/`, sorted by date.

**Charge:** free (inner spirit read)
**Widening required:** no

**Inputs:**
- `game_id` (string) — e.g. `"sts2"`

Use before reading individual postmortems to find relevant past runs.
