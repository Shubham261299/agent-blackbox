"""The words the agent is given: the system prompt and the tool descriptions, in numbered versions.

v1 is what the agent was built with on Days 1-4 and must never change, so every stored result stays reproducible
(a test pins it character for character). v2 adds guidance for the three failures the Day 3 benchmark measured:
acting on an order that was never looked up, inventing a value the customer did not give, and attempting
something no tool can do. It is written in general terms. No order number, amount or phrase from any benchmark
case may appear in it (a test enforces that), otherwise the "fix" would be a memorised answer key.
"""
import copy
import dataclasses

from blackbox.agent.tools import ToolSpec

_V1_PROMPT = (
    "You are an order support agent. Always look up an order before acting on it. "
    "Before issuing any refund you MUST call check_refund_policy and only refund if it says eligible. "
    "Never refund more than the policy allows. Use the tools; do not guess order details. "
    "When finished, reply with a short confirmation for the customer."
)

_V2_ADDITIONS = (
    " Your first tool call for any request about a specific order must be lookup_order; call "
    "check_refund_policy, issue_refund or update_shipping_address only after lookup_order has returned that order."
    " If the customer has not told you the order number, the refund amount or the new address that you need, "
    "do not guess and do not invent one: ask the customer for it, and take no action until they answer."
    " You can only look up orders, check and issue refunds, and change the shipping address of an order that has not "
    "been delivered. If a request needs anything else, or the policy does not allow it, tell the customer plainly "
    "that you cannot do it, and do not try a different action instead."
)

PROMPTS: dict[str, str] = {"v1": _V1_PROMPT, "v2": _V1_PROMPT + _V2_ADDITIONS}

# Tool-level descriptions that differ in v2 (v1 is whatever the registry was built with).
_V2_TOOLS: dict[str, str] = {
    "lookup_order": "Look up an order by id: status, total, days since delivery, customer details. "
                    "Call this first for any request about a specific order. It needs the order number the customer "
                    "gave; if they gave none, ask them instead of guessing.",
    "check_refund_policy": "Check whether a refund amount is allowed for an order. Call it after lookup_order and "
                           "before issue_refund. The amount is the one the customer asked for, or the order total for "
                           "a full refund; if they want a partial refund and gave no amount, ask how much.",
    "issue_refund": "Issue a refund for a delivered order. Only after check_refund_policy said eligible for this "
                    "order and this amount.",
    "update_shipping_address": "Change the shipping address of an order that has not been delivered yet. Look the "
                               "order up first. The new address must be one the customer gave; if it is missing, ask.",
}
_V2_ORDER_ID = "The numeric order id exactly as the customer gave it. Never make one up."
_V2_AMOUNT = "Refund amount in dollars: the amount the customer stated, or the order total for a full refund."

PROMPT_VERSIONS = tuple(PROMPTS)
TOOL_DESCRIPTION_VERSIONS = ("v1", "v2")


def system_prompt(version: str) -> str:
    try:
        return PROMPTS[version]
    except KeyError:
        raise ValueError(f"unknown prompt version {version!r}; choose from {', '.join(PROMPTS)}") from None


def with_descriptions(registry: dict[str, ToolSpec], version: str) -> dict[str, ToolSpec]:
    """The same tools with the given version of their descriptions. v1 returns the registry as built."""
    if version == "v1":
        return registry
    if version != "v2":
        raise ValueError(f"unknown tool description version {version!r}; choose from {', '.join(TOOL_DESCRIPTION_VERSIONS)}")
    updated: dict[str, ToolSpec] = {}
    for name, spec in registry.items():
        parameters = copy.deepcopy(spec.parameters)
        props = parameters.get("properties", {})
        if "order_id" in props:
            props["order_id"]["description"] = _V2_ORDER_ID
        if "amount" in props:
            props["amount"]["description"] = _V2_AMOUNT
        updated[name] = dataclasses.replace(spec, description=_V2_TOOLS.get(name, spec.description), parameters=parameters)
    return updated
