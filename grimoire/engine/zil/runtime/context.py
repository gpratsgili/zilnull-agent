"""Session context builder.

Builds the persistent context ZIL needs at startup:
  - identity, cornerstone, voice from spirits/zil/
  - long-term memory summary
  - recent window memory records

Built once per session, then passed through run_turn() to every pipeline
stage so all four stages operate with the same grounding.
"""

from __future__ import annotations

from dataclasses import dataclass

from zil.config import get_config
from zil.memory.store import MemoryStore


@dataclass
class SessionContext:
    identity: str
    cornerstone: str
    voice: str
    long_term_memory: str
    window_memory: str
    memory_record_count: int
    summoner_profile: str = ""  # spirits/zil/people/summoner/profile.md, if it exists
    model_info: str = ""        # e.g. "qwen3:9b (ollama @ localhost:11434)"

    def build_system_prompt(
        self,
        prompt_contract: str,
        *,
        budget_note: str = "",
    ) -> str:
        """Full context — used by the Responder, which needs everything to write well.

        Includes: identity, behavioral laws, voice, long-term memory, recent memory,
        summoner profile (if present), optional budget note, and stage instructions.
        """
        sections = []

        if self.identity:
            sections.append(f"## Identity\n{self.identity}")
        if self.cornerstone:
            sections.append(f"## Behavioral laws\n{self.cornerstone}")
        if self.voice:
            sections.append(f"## Voice contract\n{self.voice}")
        if self.long_term_memory:
            sections.append(f"## Long-term memory\n{self.long_term_memory}")
        if self.window_memory and self.window_memory != "(no recent memory)":
            sections.append(f"## Recent memory\n{self.window_memory}")
        if self.summoner_profile:
            sections.append(f"## Summoner profile\n{self.summoner_profile}")
        if self.model_info:
            sections.append(
                f"## Active model\n"
                f"You are running on: **{self.model_info}**. "
                f"Be aware of what this implies about your own capabilities and limitations."
            )
        if budget_note:
            sections.append(f"## Session budget\n{budget_note}")

        sections.append(f"## Stage instructions\n{prompt_contract}")
        return "\n\n".join(sections)

    def build_minimal_prompt(self, prompt_contract: str) -> str:
        """Compact context — used by Interpreter, Examiner, and Auditor.

        These stages do not produce user-facing text, so they don't need voice
        or the full identity document. They need behavioral laws (cornerstone)
        and enough memory to understand what's been discussed.

        This significantly reduces token usage per turn: 3 of 4 stages run lean.
        """
        sections = []

        # Brief identity anchor — just enough so the stage knows who it is
        if self.identity:
            # First 400 chars of identity is enough for orientation
            brief = self.identity[:400].rstrip()
            if len(self.identity) > 400:
                brief += "\n[...]"
            sections.append(f"## Identity (brief)\n{brief}")

        # Full cornerstone — behavioral laws are critical for all stages
        if self.cornerstone:
            sections.append(f"## Behavioral laws\n{self.cornerstone}")

        # Recent memory only — long-term is lower priority for structural stages
        if self.window_memory and self.window_memory != "(no recent memory)":
            sections.append(f"## Recent memory\n{self.window_memory}")

        sections.append(f"## Stage instructions\n{prompt_contract}")
        return "\n\n".join(sections)

    @classmethod
    def build(cls, store: MemoryStore | None = None) -> "SessionContext":
        """Load all session context from disk. Safe to call even if files are missing."""
        cfg = get_config()
        if store is None:
            store = MemoryStore()

        def _read_doc(spirit: str, doc: str) -> str:
            try:
                return cfg.read_spirit_doc(spirit, doc)
            except (FileNotFoundError, OSError):
                return ""

        identity = _read_doc("zil", "identity.md")
        cornerstone = _read_doc("zil", "cornerstone.md")
        voice = _read_doc("zil", "voice.md")
        long_term = store.read_long_term()

        window_records = store.read_window()[-cfg.context_window_records:]
        window_memory = store.window_summary_for_prompt(
            max_records=cfg.context_window_records
        )

        # Load summoner profile if it exists — ambient context, no tool call needed
        summoner_profile = ""
        summoner_profile_path = cfg.zil_people_dir / "summoner" / "profile.md"
        if summoner_profile_path.exists():
            try:
                summoner_profile = summoner_profile_path.read_text(encoding="utf-8")
            except OSError:
                pass

        return cls(
            identity=identity,
            cornerstone=cornerstone,
            voice=voice,
            long_term_memory=long_term,
            window_memory=window_memory,
            memory_record_count=len(window_records),
            summoner_profile=summoner_profile,
            model_info=cfg.model_display,
        )
