"""Infrastructure failures an agent run can hit. They live here, not next to whatever raises them, so the
exception type recorded in a trace names the kind of failure and nothing about where it came from."""


class ToolTimeoutError(Exception):
    """A tool did not answer in time. Deliberately NOT a ToolError: the baseline agent does not handle
    infrastructure failures, so this ends the run. (Handling it is the Day 5 fix.)"""


class ModelUnavailableError(Exception):
    """The model backend did not answer (what an unreachable Ollama looks like)."""
