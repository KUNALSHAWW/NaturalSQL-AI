"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_MASK_PATTERNS = (
    r"e?mail",
    r"phone|mobile",
    r"ssn|social_?security|national_?id|passport|aadhaar|pan_?no",
    r"password|passwd|pwd|secret|token|api_?key",
    r"card_?(no|num|number)|cvv|iban|account_?(no|num|number)",
)

PROVIDER_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("http://localhost:11434", "llama3.1:8b"),
    "ollama_cloud": ("https://ollama.com", "gpt-oss:120b"),
}

PROVIDER_KEY_ENV = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "ollama_cloud": "OLLAMA_API_KEY"}


@dataclass
class Settings:
    db_url: str = "sqlite:///demo_retail.db"
    provider: str = "groq"
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    # generation
    n_candidates: int = 3
    temperature: float = 0.6          # for the extra candidates; the first is greedy
    max_repairs: int = 2
    parallel: bool = True
    max_tokens: int = 400
    # safety
    max_rows: int = 1000
    timeout_s: float = 10.0
    max_joins: int = 8
    allowed_tables: set[str] | None = None
    denied_columns: set[str] = field(default_factory=set)
    mask_patterns: tuple[str, ...] = DEFAULT_MASK_PATTERNS
    # persistence
    audit_path: str = "naturalsql_audit.jsonl"
    memory_path: str = "naturalsql_memory.db"

    def __post_init__(self) -> None:
        self.provider = self.provider.lower().replace("-", "_")
        base, model = PROVIDER_DEFAULTS.get(self.provider, ("", ""))
        if not self.api_key:
            self.api_key = os.environ.get(PROVIDER_KEY_ENV.get(self.provider, ""), "")
        self.base_url = self.base_url or base
        self.model = self.model or model
        if self.provider == "ollama":
            self.parallel = False  # a local model serves one request at a time

    @classmethod
    def from_env(cls) -> Settings:
        provider = os.environ.get("NATURALSQL_PROVIDER", "groq").lower()
        key = os.environ.get(
            "NATURALSQL_API_KEY",
            os.environ.get(PROVIDER_KEY_ENV.get(provider.replace("-", "_"), ""), ""),
        )
        denied = {c.strip().lower() for c in os.environ.get("NATURALSQL_DENIED_COLUMNS", "").split(",") if c.strip()}
        allowed = {t.strip().lower() for t in os.environ.get("NATURALSQL_ALLOWED_TABLES", "").split(",") if t.strip()}
        return cls(
            db_url=os.environ.get("NATURALSQL_DB_URL", "sqlite:///demo_retail.db"),
            provider=provider,
            model=os.environ.get("NATURALSQL_MODEL", ""),
            base_url=os.environ.get("NATURALSQL_BASE_URL", os.environ.get("OLLAMA_HOST", "") if provider == "ollama" else ""),
            api_key=key,
            n_candidates=int(os.environ.get("NATURALSQL_CANDIDATES", "3")),
            max_repairs=int(os.environ.get("NATURALSQL_MAX_REPAIRS", "2")),
            max_rows=int(os.environ.get("NATURALSQL_MAX_ROWS", "1000")),
            timeout_s=float(os.environ.get("NATURALSQL_TIMEOUT_S", "10")),
            allowed_tables=allowed or None,
            denied_columns=denied,
            audit_path=os.environ.get("NATURALSQL_AUDIT_PATH", "naturalsql_audit.jsonl"),
            memory_path=os.environ.get("NATURALSQL_MEMORY_PATH", "naturalsql_memory.db"),
        )
