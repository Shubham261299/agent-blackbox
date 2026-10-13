"""Local Ollama model with native tool calling. No fallback to any hosted provider, ever."""
from typing import Any

import ollama

from blackbox.llm.base import ModelResponse, ToolRequest


class OllamaClient:
    provider = "ollama"

    def __init__(self, host: str, model: str, timeout_s: float = 300.0, seed: int = 0) -> None:
        self.name = model
        self._seed = seed
        self._client = ollama.Client(host=host, timeout=timeout_s)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        response = self._client.chat(
            model=self.name,
            messages=messages,
            tools=tools,
            options={"temperature": 0, "seed": self._seed},
        )
        message = response.message
        calls = [
            ToolRequest(name=tc.function.name, arguments=dict(tc.function.arguments or {}))
            for tc in (message.tool_calls or [])
        ]
        return ModelResponse(
            content=message.content or "",
            tool_calls=calls,
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )
