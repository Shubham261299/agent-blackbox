"""Infrastructure failures an agent run can hit. They live here, not next to whatever raises them, so the
exception type recorded in a trace names the kind of failure and nothing about where it came from."""
import httpx


class ToolTimeoutError(Exception):
    """A tool did not answer in time. Deliberately NOT a ToolError: the baseline agent does not handle
    infrastructure failures, so this ends the run. (A config with retries handles it: see agent/config.py.)"""


class ModelUnavailableError(Exception):
    """The model backend did not answer (what an unreachable Ollama looks like)."""


class ToolContractViolation(Exception):
    """A tool call succeeded but returned something its contract does not allow. Raised only when the agent
    enforces contracts at runtime; otherwise the bad output goes to the model unchecked, as before."""


# What a retry may help with when the model backend fails: our own error, a refused or dropped connection
# (the ollama client raises the builtin ConnectionError), and timeouts. Anything else is a bug, not an outage.
TRANSIENT_MODEL_ERRORS: tuple[type[BaseException], ...] = (
    ModelUnavailableError, ConnectionError, TimeoutError, httpx.TransportError,
)
