from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolRequest:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    content: str = ""
    tool_calls: list[ToolRequest] = field(default_factory=list)
    # None means "not measured" (e.g. scripted model) -- never a made-up number.
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelClient(Protocol):
    """What the agent loop needs from a model. Implementations must never fall back to another provider."""

    provider: str
    name: str

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse: ...
