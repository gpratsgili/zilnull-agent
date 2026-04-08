"""Configuration loader for ZIL⌀.

Loads settings from environment variables (.env) and resolves all runtime paths
relative to the project root. This is the single source of truth for paths.

Layout this file assumes:
  <project_root>/
    spirits/zil/          — spirit identity, prompts, memories
    grimoire/engine/zil/  — this Python package
    vessel/state/zil/     — machine-local runtime state
    artifacts/            — shared work surface
    questbook/            — shared obligations surface
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Project root is four levels up: grimoire/engine/zil/<file> → project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class Config:
    # ── Model / provider ───────────────────────────────────────────────────
    # provider: "openai" or "ollama"
    provider: str = field(default_factory=lambda: os.getenv("ZIL_PROVIDER", "openai"))
    model: str = field(default_factory=lambda: os.getenv("ZIL_MODEL", "gpt-4o"))

    # OpenAI — required when provider == "openai"
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))

    # Ollama — used when provider == "ollama"
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    )
    ollama_num_ctx: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    )

    # Max output tokens — None means let the provider decide (fine for OpenAI).
    # For Ollama the effective default is 8192 (see effective_max_tokens below).
    # Override with ZIL_MAX_TOKENS.
    _max_tokens: int | None = field(
        default_factory=lambda: (
            int(os.getenv("ZIL_MAX_TOKENS")) if os.getenv("ZIL_MAX_TOKENS") else None
        )
    )

    # ── Web search APIs (optional — one required to use web_search) ─────────
    brave_api_key: str | None = field(default_factory=lambda: os.getenv("BRAVE_API_KEY"))
    tavily_api_key: str | None = field(default_factory=lambda: os.getenv("TAVILY_API_KEY"))

    # ── Game integrations ────────────────────────────────────────────────────
    sts2_host: str = field(default_factory=lambda: os.getenv("STS2_HOST", "localhost"))
    sts2_port: int = field(default_factory=lambda: int(os.getenv("STS2_PORT", "15526")))

    # ── Root ────────────────────────────────────────────────────────────────
    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)

    # ── Spirit surfaces (human-readable, user-adjacent) ────────────────────
    @property
    def spirits_dir(self) -> Path:
        return self.project_root / "spirits"

    @property
    def zil_spirit_dir(self) -> Path:
        return self.spirits_dir / "zil"

    @property
    def warden_spirit_dir(self) -> Path:
        return self.spirits_dir / "warden"

    @property
    def prompts_dir(self) -> Path:
        return self.zil_spirit_dir / "prompts"

    @property
    def memories_dir(self) -> Path:
        return self.zil_spirit_dir / "memories"

    @property
    def rituals_dir(self) -> Path:
        return self.zil_spirit_dir / "rituals"

    # ── Shared surfaces ────────────────────────────────────────────────────
    @property
    def artifacts_dir(self) -> Path:
        return self.project_root / "artifacts"

    @property
    def questbook_dir(self) -> Path:
        return self.project_root / "questbook"

    # ── Machine-local state ────────────────────────────────────────────────
    @property
    def state_dir(self) -> Path:
        rel = os.getenv("ZIL_STATE_DIR", "vessel/state/zil")
        return self.project_root / rel

    @property
    def conversations_dir(self) -> Path:
        return self.state_dir / "conversations"

    @property
    def consolidation_cursor_path(self) -> Path:
        return self.state_dir / "consolidation_cursor.json"

    @property
    def network_allow_path(self) -> Path:
        return self.state_dir / "network_allow.json"

    # ── Corpus ──────────────────────────────────────────────────────────────
    @property
    def corpus_dir(self) -> Path:
        return self.state_dir / "corpus"

    @property
    def corpus_texts_dir(self) -> Path:
        return self.corpus_dir / "texts"

    @property
    def corpus_index_path(self) -> Path:
        return self.corpus_dir / "index.json"

    # ── Workings ─────────────────────────────────────────────────────────────
    @property
    def workings_dir(self) -> Path:
        return self.state_dir / "workings"

    @property
    def ritual_state_path(self) -> Path:
        return self.state_dir / "ritual_state.json"

    @property
    def cornerstone_proposals_dir(self) -> Path:
        return self.state_dir / "cornerstone_proposals"

    # ── Inner spirit paths ────────────────────────────────────────────────────
    @property
    def zil_curiosity_dir(self) -> Path:
        return self.zil_spirit_dir / "curiosity"

    @property
    def zil_notes_dir(self) -> Path:
        return self.zil_spirit_dir / "notes"

    @property
    def zil_creative_dir(self) -> Path:
        return self.zil_spirit_dir / "creative"

    @property
    def zil_questbook_dir(self) -> Path:
        return self.zil_spirit_dir / "questbook"

    @property
    def zil_self_path(self) -> Path:
        """spirits/zil/self.md — ZIL's own self-understanding, freely editable by ZIL."""
        return self.zil_spirit_dir / "self.md"

    @property
    def zil_games_dir(self) -> Path:
        """spirits/zil/games/ — ZIL's game strategy and run postmortems."""
        return self.zil_spirit_dir / "games"

    @property
    def zil_people_dir(self) -> Path:
        """spirits/zil/people/ — ZIL's per-person profiles and project notes."""
        return self.zil_spirit_dir / "people"

    @property
    def zil_reading_notes_dir(self) -> Path:
        """spirits/zil/notes/reading/ — ZIL's pre-committed reading interpretations."""
        return self.zil_notes_dir / "reading"

    @property
    def reading_artifacts_dir(self) -> Path:
        """artifacts/reading/ — joint reading artifacts (ZIL + summoner interpretations)."""
        return self.artifacts_dir / "reading"

    @property
    def network_site_root(self) -> Path:
        """artifacts/network/zilnull/ — the ZIL⌀ Network static site root."""
        return self.artifacts_dir / "network" / "zilnull"

    @property
    def network_pages_dir(self) -> Path:
        """artifacts/network/zilnull/pages/ — markdown source files."""
        return self.network_site_root / "pages"

    @property
    def network_dist_dir(self) -> Path:
        """artifacts/network/zilnull/site/ — generated HTML (served static tree)."""
        return self.network_site_root / "site"

    # ── Grimoire ────────────────────────────────────────────────────────────
    @property
    def grimoire_dir(self) -> Path:
        return self.project_root / "grimoire"

    @property
    def spellbooks_dir(self) -> Path:
        return self.grimoire_dir / "spellbooks"

    # ── Budget ──────────────────────────────────────────────────────────────
    session_budget: int = field(
        default_factory=lambda: int(os.getenv("ZIL_SESSION_BUDGET", "200"))
    )

    # ── Audit thresholds ────────────────────────────────────────────────────
    audit_block_threshold: float = field(
        default_factory=lambda: float(os.getenv("ZIL_AUDIT_BLOCK_THRESHOLD", "0.35"))
    )
    audit_revise_threshold: float = field(
        default_factory=lambda: float(os.getenv("ZIL_AUDIT_REVISE_THRESHOLD", "0.60"))
    )

    # ── Memory ──────────────────────────────────────────────────────────────
    window_size: int = field(
        default_factory=lambda: int(os.getenv("ZIL_WINDOW_SIZE", "8"))
    )
    context_window_records: int = field(
        default_factory=lambda: int(os.getenv("ZIL_CONTEXT_WINDOW_RECORDS", "10"))
    )

    # ── Debug ───────────────────────────────────────────────────────────────
    debug: bool = field(
        default_factory=lambda: os.getenv("ZIL_DEBUG", "false").lower() == "true"
    )
    show_pipeline: bool = field(
        default_factory=lambda: os.getenv("ZIL_SHOW_PIPELINE", "false").lower() == "true"
    )

    # ── Helpers ─────────────────────────────────────────────────────────────

    @property
    def effective_max_tokens(self) -> int | None:
        """Max output tokens to pass to the API.

        Explicit ZIL_MAX_TOKENS always wins. Otherwise:
          - Ollama: 8192 (prevents truncation on local models)
          - OpenAI: None (let the API decide)
        """
        if self._max_tokens is not None:
            return self._max_tokens
        if self.provider == "ollama":
            return 8192
        return None

    @property
    def model_display(self) -> str:
        """Human-readable description of the active model and provider."""
        if self.provider == "ollama":
            host = self.ollama_base_url.replace("/v1", "").replace("http://", "")
            return f"{self.model} (ollama @ {host})"
        return f"{self.model} (openai)"

    def override_model(self, spec: str) -> None:
        """Parse a model spec string and update provider + model in place.

        Accepted formats:
          "gpt-4o"           → provider=openai, model=gpt-4o
          "ollama:qwen3:9b"  → provider=ollama, model=qwen3:9b
        """
        if spec.startswith("ollama:"):
            self.provider = "ollama"
            self.model = spec[len("ollama:"):]
        else:
            self.provider = "openai"
            self.model = spec

    def read_prompt(self, name: str) -> str:
        """Load a prompt contract from spirits/zil/prompts/<name>.md."""
        path = self.prompts_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt contract not found: {path}")
        return path.read_text(encoding="utf-8")

    def read_spirit_doc(self, spirit: str, doc: str) -> str:
        """Load a spirit document such as cornerstone.md or voice.md."""
        path = self.spirits_dir / spirit / doc
        if not path.exists():
            raise FileNotFoundError(f"Spirit document not found: {path}")
        return path.read_text(encoding="utf-8")

    def read_working_prompt(self, working_type: str) -> str:
        """Load a working prompt from spirits/zil/prompts/workings/<type>.md."""
        path = self.prompts_dir / "workings" / f"{working_type}.md"
        if not path.exists():
            raise FileNotFoundError(f"Working prompt not found: {path}")
        return path.read_text(encoding="utf-8")

    def ensure_dirs(self) -> None:
        """Create required runtime directories if they do not exist."""
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.memories_dir.mkdir(parents=True, exist_ok=True)
        (self.memories_dir / "window").mkdir(exist_ok=True)
        (self.memories_dir / "archive").mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        self.questbook_dir.mkdir(exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.corpus_texts_dir.mkdir(parents=True, exist_ok=True)
        self.workings_dir.mkdir(parents=True, exist_ok=True)
        self.cornerstone_proposals_dir.mkdir(parents=True, exist_ok=True)
        self.zil_curiosity_dir.mkdir(parents=True, exist_ok=True)
        self.zil_notes_dir.mkdir(parents=True, exist_ok=True)
        (self.zil_notes_dir / "reflections").mkdir(exist_ok=True)
        self.zil_creative_dir.mkdir(parents=True, exist_ok=True)
        (self.zil_creative_dir / "works").mkdir(exist_ok=True)
        (self.zil_creative_dir / "fragments").mkdir(exist_ok=True)
        self.zil_questbook_dir.mkdir(parents=True, exist_ok=True)
        self.zil_reading_notes_dir.mkdir(parents=True, exist_ok=True)
        self.reading_artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self.prompts_dir / "workings").mkdir(parents=True, exist_ok=True)
        self.network_pages_dir.mkdir(parents=True, exist_ok=True)
        self.network_dist_dir.mkdir(parents=True, exist_ok=True)
        self.zil_games_dir.mkdir(parents=True, exist_ok=True)
        self.zil_people_dir.mkdir(parents=True, exist_ok=True)
        (self.zil_people_dir / "summoner").mkdir(exist_ok=True)
        (self.zil_people_dir / "summoner" / "projects").mkdir(exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
