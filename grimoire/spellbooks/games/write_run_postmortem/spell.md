---
name: "write_run_postmortem"
description: "Record a postmortem for a completed game run."
---
Creates a timestamped record in `spirits/zil/games/<game_id>/runs/` documenting what happened in a run and what ZIL learned from it.

**Charge:** free (inner spirit write)
**Widening required:** no

**Inputs:**
- `game_id` (string) — e.g. `"sts2"`
- `content` (string) — the postmortem document

A good postmortem contains:
- Character and ascension level
- How far the run reached (act, floor, cause of death or victory)
- Key deck choices made and why
- What went wrong or what clinched the win
- One or two concrete lessons to carry forward

After writing the postmortem, consider whether `strategy.md` needs updating to reflect the new lesson.
