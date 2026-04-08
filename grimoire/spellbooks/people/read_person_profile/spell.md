---
name: "read_person_profile"
description: "Read ZIL's profile of a specific person."
---
Reads `spirits/zil/people/<name>/profile.md`.

**Charge:** free (inner spirit read)
**Widening required:** no

**Inputs:**
- `name` (string) — person identifier, e.g. `"summoner"` or a name ZIL has used

Note: the summoner's profile is already loaded automatically at session start. Only call this explicitly when you need to re-read it mid-session or access a different person's profile.
