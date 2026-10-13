import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OTLP_ENDPOINT = "http://localhost:4318/v1/traces"


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/blackbox.db"
    # None disables OTLP export (spans still go to SQLite).
    otlp_endpoint: str | None = DEFAULT_OTLP_ENDPOINT
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_s: float = 300.0
    service_name: str = "agent-blackbox"
    max_agent_steps: int = 8


def get_settings() -> Settings:
    """Read settings from BLACKBOX_* environment variables; an empty OTLP endpoint disables export."""
    env = os.environ
    otlp = env.get("BLACKBOX_OTLP_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
    return Settings(
        db_path=env.get("BLACKBOX_DB_PATH", Settings.db_path),
        otlp_endpoint=otlp or None,
        ollama_host=env.get("BLACKBOX_OLLAMA_HOST", Settings.ollama_host),
        ollama_model=env.get("BLACKBOX_OLLAMA_MODEL", Settings.ollama_model),
        ollama_timeout_s=float(env.get("BLACKBOX_OLLAMA_TIMEOUT_S", Settings.ollama_timeout_s)),
        max_agent_steps=int(env.get("BLACKBOX_MAX_AGENT_STEPS", Settings.max_agent_steps)),
    )


def ensure_parent_dir(db_path: str) -> None:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
