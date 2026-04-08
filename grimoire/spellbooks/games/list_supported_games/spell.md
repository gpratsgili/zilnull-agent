---
name: "list_supported_games"
description: "List all games with available integrations and their connection status."
---
Returns the registry of supported games — their names, required mods, connection endpoints, and whether a live connection can be made right now.

**Charge:** free (local inspection)
**Widening required:** no — this is a read of local configuration, not a game action

**Output:** A table of games with:
- Game name and version
- Required mod/API
- Configured host:port
- Connection status (live / unreachable / not configured)

Use this before starting a game session to verify the setup is correct.
