---
name: "games"
description: "Game integration surface. Each supported game has its own sub-spellbook with dedicated casts wired to the game's local API."
---
This widening-required spellbook governs direct game integration.

Unlike the original Phase 11 vision (screenshot + click), games are integrated via their native mod APIs — no vision inference, no screen capture. Each supported game exposes a local HTTP service that this spellbook communicates with.

**Supported games** are those with a sub-spellbook present under `grimoire/spellbooks/games/`. Use `list_supported_games` to see what is currently available and whether the connection is live.

**To add a new game:** create a sub-directory here with a `spellbook.md` manifest and add its casts to the Python tools layer.

Each cast in this spellbook requires game access to be widened for the session. The game must be running with its mod active.
