"""What the agent is allowed to do about trouble. `baseline` is the agent as it was on Days 1-4 and must stay
exactly that, so every stored result stays reproducible. The other presets switch on one group of fixes at a
time, so a before/after table can say which fix did the work.

  resilience  retry infrastructure errors (tool timeout, model unavailable) and reject tool output that breaks
              its contract, up to `retries` extra attempts
  guidance    a prompt and tool descriptions that say "look the order up first", "ask instead of invent" and
              "say so when you cannot" (agent/guidance.py)
"""
from dataclasses import dataclass

from blackbox.agent.guidance import PROMPT_VERSIONS, TOOL_DESCRIPTION_VERSIONS


@dataclass(frozen=True)
class AgentConfig:
    name: str = "baseline"
    retries: int = 0  # extra attempts after the first for a retryable failure; 0 = never retry
    backoff_s: float = 0.0  # wait before attempt n+1 is backoff_s * n
    enforce_contracts: bool = False  # treat tool output that breaks its contract as a (retryable) failure
    prompt_version: str = "v1"
    tool_descriptions: str = "v1"

    def __post_init__(self) -> None:
        if self.prompt_version not in PROMPT_VERSIONS:
            raise ValueError(f"unknown prompt version {self.prompt_version!r}")
        if self.tool_descriptions not in TOOL_DESCRIPTION_VERSIONS:
            raise ValueError(f"unknown tool description version {self.tool_descriptions!r}")


PRESETS: dict[str, AgentConfig] = {
    "baseline": AgentConfig(),
    "resilient": AgentConfig(name="resilient", retries=2, backoff_s=0.05, enforce_contracts=True),
    "guided": AgentConfig(name="guided", prompt_version="v2", tool_descriptions="v2"),
    "full": AgentConfig(name="full", retries=2, backoff_s=0.05, enforce_contracts=True,
                        prompt_version="v2", tool_descriptions="v2"),
}


def preset(name: str) -> AgentConfig:
    try:
        return PRESETS[name]
    except KeyError:
        raise KeyError(f"unknown agent variant {name!r}; choose from {', '.join(PRESETS)}") from None
