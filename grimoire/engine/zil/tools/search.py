"""Search tool stub.

External search requires explicit widening via warden.widen(Surface.EXTERNAL, ...).
Version 1 does not ship a live search implementation — it exposes the interface
so it can be wired up without changing the tool registry.
"""

from __future__ import annotations


def web_search(query: str, *, max_results: int = 5) -> list[dict]:
    """Stub: web search not enabled in version 1.

    To enable, widen EXTERNAL ACQUIRE permission and implement this function
    using a search API (e.g., Tavily, SerpAPI, or Brave Search).
    """
    raise NotImplementedError(
        "Web search is not enabled in version 1. "
        "Implement this function and widen permissions to enable."
    )
