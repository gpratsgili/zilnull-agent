---
name: "read_run_postmortem"
description: "Read a specific run postmortem for a game."
---
Reads a postmortem file from `spirits/zil/games/<game_id>/runs/<name>.md`.

**Charge:** free (inner spirit read)
**Widening required:** no

**Inputs:**
- `game_id` (string) — e.g. `"sts2"`
- `name` (string) — filename without `.md` extension (use `list_run_postmortems` to find names)
