"""Game integration tools for ZIL⌀.

Each supported game has its own module here. The registry below maps
game IDs to metadata used by list_supported_games.
"""

from __future__ import annotations

SUPPORTED_GAMES: dict[str, dict] = {
    "sts2": {
        "name": "Slay the Spire 2",
        "mod": "STS2MCP (Gennadiyev)",
        "mod_url": "https://github.com/Gennadiyev/STS2MCP",
        "default_host": "localhost",
        "default_port": 15526,
        "env_host": "STS2_HOST",
        "env_port": "STS2_PORT",
    },
}
