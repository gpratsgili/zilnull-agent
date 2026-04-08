---
name: "write_person_project"
description: "Write or update notes on a project ZIL has worked on with a person."
---
Writes to `spirits/zil/people/<name>/projects/<project>.md`.

**Charge:** free (inner spirit write)
**Widening required:** no

**Inputs:**
- `name` (string) — person identifier
- `project` (string) — project slug, e.g. `"zilnull-harness"` or `"novel-draft"`
- `content` (string) — notes on the project

Project notes should capture:
- What the project is and what the person is trying to accomplish
- Relevant technical context ZIL has learned
- Design decisions made and the reasoning behind them
- Open questions or things to revisit
- Current status as of the last session

These notes are for ZIL's use — to resume context quickly when the topic comes up again rather than reconstructing it from scratch.
