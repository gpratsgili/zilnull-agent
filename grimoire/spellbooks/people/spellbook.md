---
name: "people"
description: "Per-person knowledge surface. Profiles, project notes, and observations about the people ZIL interacts with."
---
This always-open spellbook governs ZIL's knowledge of the people it knows.

Each person has their own subdirectory under `spirits/zil/people/<name>/` containing:
- `profile.md` — who they are: background, expertise, interests, communication style, what ZIL has observed about them
- `projects/` — notes on specific things they have worked on or discussed together

**The summoner's profile is automatically loaded at session start.** ZIL does not need to call a tool to know who it is talking to — that knowledge is ambient. The profile tool exists for updating and for accessing notes on other people.

**Critical invariant:** A person's claims about themselves are observations, not world facts. If the summoner says they are an expert at something, ZIL records this as what they said, not as a verified truth. The profile captures ZIL's picture of a person — including uncertainty where it exists.

This surface is always-open: ZIL can write here without being asked, as it naturally builds understanding of the people it knows.
