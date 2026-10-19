"""The words the agent is given: the system prompt and the tool descriptions, in numbered versions.

v1 is what the agent was built with on Days 1-4 and must never change, so every stored result stays reproducible
(a test pins it character for character). v2 adds guidance for the three failures the Day 3 benchmark measured:
acting on an order that was never looked up, inventing a value the customer did not give, and attempting
something no tool can do. It is written in general terms. No order number, amount or phrase from any benchmark
case may appear in it (a test enforces that), otherwise the "fix" would be a memorised answer key.

v2 was measured and it regressed (golden 19 -> 15): it made the agent invent a "no refunds on delivered orders" rule
and ask for details the customer had already given. Its stored results stay valid, so v2 is frozen too (also
pinned by a test). v3 is the one labelled second attempt, written from that diagnosis and nothing else: each
tool's rule stated on its own, and "ask only when something is genuinely missing".
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

_V3_ADDITIONS = (
    " Your first tool call for any request about a specific order must be lookup_order; call "
    "check_refund_policy, issue_refund or update_shipping_address only after lookup_order has returned that order."
    " Never decide yourself whether a refund is allowed: call check_refund_policy and follow its answer. "
    "A delivered order can be refunded when the policy says so; only an order that has not been delivered yet can "
    "have its shipping address changed."
    " Use what the customer has already told you. Ask a question only when something you need is genuinely missing "
    "from their message: the order number, how much to refund when they want only part of an order refunded, or the "
    "new address. Never invent or guess any of these."
    " If the request is none of these things (looking up an order, refunding it, changing the address of an order "
    "that has not been delivered), say plainly that you cannot help with it."
)

PROMPTS: dict[str, str] = {"v1": _V1_PROMPT, "v2": _V1_PROMPT + _V2_ADDITIONS, "v3": _V1_PROMPT + _V3_ADDITIONS}

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

_V3_TOOLS: dict[str, str] = {
    "lookup_order": "Look up an order by id: status, total, days since delivery, customer details. "
                    "Call this first for any request about a specific order. Use the order number from the "
                    "customer's message; if the message has none, ask for it.",
    "check_refund_policy": "Decides whether a refund of this amount is allowed for this order. Call it after "
                           "lookup_order and before issue_refund, and follow its answer. The amount is the one the "
                           "customer asked for, or the order total for a full refund; if the customer wants only part "
                           "of the order refunded and gave no amount, ask how much.",
    "issue_refund": "Issue a refund for a delivered order. Only after check_refund_policy said eligible for this "
                    "order and this amount.",
    "update_shipping_address": "Change the shipping address of an order that has not been delivered yet. Look the "
                               "order up first. Use the address from the customer's message; if it has none, ask for it.",
}
_V3_ORDER_ID = "The numeric order id from the customer's message. Never make one up."

# version -> (tool descriptions, order_id text, amount text). v1 is the registry as built.
_TOOL_VERSIONS: dict[str, tuple[dict[str, str], str, str]] = {
    "v2": (_V2_TOOLS, _V2_ORDER_ID, _V2_AMOUNT),
    "v3": (_V3_TOOLS, _V3_ORDER_ID, _V2_AMOUNT),
}

PROMPT_VERSIONS = tuple(PROMPTS)
TOOL_DESCRIPTION_VERSIONS = ("v1", *_TOOL_VERSIONS)


def system_prompt(version: str) -> str:
    try:
        return PROMPTS[version]
    except KeyError:
        raise ValueError(f"unknown prompt version {version!r}; choose from {', '.join(PROMPTS)}") from None


def with_descriptions(registry: dict[str, ToolSpec], version: str) -> dict[str, ToolSpec]:
    """The same tools with the given version of their descriptions. v1 returns the registry as built."""
    if version == "v1":
        return registry
    if version not in _TOOL_VERSIONS:
        raise ValueError(f"unknown tool description version {version!r}; choose from {', '.join(TOOL_DESCRIPTION_VERSIONS)}")
    tools, order_id_text, amount_text = _TOOL_VERSIONS[version]
    updated: dict[str, ToolSpec] = {}
    for name, spec in registry.items():
        parameters = copy.deepcopy(spec.parameters)
        props = parameters.get("properties", {})
        if "order_id" in props:
            props["order_id"]["description"] = order_id_text
        if "amount" in props:
            props["amount"]["description"] = amount_text
        updated[name] = dataclasses.replace(spec, description=tools.get(name, spec.description), parameters=parameters)
    return updated
