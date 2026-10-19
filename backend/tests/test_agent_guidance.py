"""Guidance versions: v1 is pinned character for character (so Day 1-4 results stay reproducible), v2 only ever
adds general rules, and the variant the agent is configured with is the one the model actually receives."""
import re

import pytest

from blackbox.agent.config import PRESETS, AgentConfig, preset
from blackbox.agent.guidance import PROMPTS, system_prompt, with_descriptions
from blackbox.agent.loop import SYSTEM_PROMPT, AgentRunner
from blackbox.agent.tools import OrderDesk
from blackbox.evals.cases import load_dataset
from blackbox.llm.base import ModelResponse

# Copied from the code as it was before variants existed. If this test fails, v1 changed and old results no longer mean what they did.
V1_PROMPT = (
    "You are an order support agent. Always look up an order before acting on it. "
    "Before issuing any refund you MUST call check_refund_policy and only refund if it says eligible. "
    "Never refund more than the policy allows. Use the tools; do not guess order details. "
    "When finished, reply with a short confirmation for the customer."
)
V1_DESCRIPTIONS = {
    "lookup_order": "Look up an order by id: status, total, days since delivery, customer details.",
    "check_refund_policy": "Check whether a refund amount is allowed for an order. Call before issue_refund.",
    "issue_refund": "Issue a refund for a delivered order.",
    "update_shipping_address": "Change the shipping address of an order that has not been delivered yet.",
}

# v2 produced the stored Day 5 results (guided, full), so it is frozen too. If this fails, v2 changed and those
# results no longer describe the agent that produced them. Fix the code, or add v4: never edit v2.
V2_PROMPT = V1_PROMPT + (
    " Your first tool call for any request about a specific order must be lookup_order; call "
    "check_refund_policy, issue_refund or update_shipping_address only after lookup_order has returned that order."
    " If the customer has not told you the order number, the refund amount or the new address that you need, "
    "do not guess and do not invent one: ask the customer for it, and take no action until they answer."
    " You can only look up orders, check and issue refunds, and change the shipping address of an order that has not "
    "been delivered. If a request needs anything else, or the policy does not allow it, tell the customer plainly "
    "that you cannot do it, and do not try a different action instead."
)
V2_DESCRIPTIONS = {
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


class Recorder:
    """A model that records what it is given and ends the run at once."""
    provider, name = "scripted", "recorder"

    def __init__(self):
        self.messages, self.tools = None, None

    def chat(self, messages, tools):
        self.messages, self.tools = messages, tools
        return ModelResponse(content="done")


def received_by(telemetry, config):
    model = Recorder()
    AgentRunner(model, OrderDesk().registry(), telemetry.tracer(), 8, config).run("run-g", "hello")
    return model


# ---- v1 is frozen -------------------------------------------------------------------------------------
def test_v1_prompt_is_unchanged():
    assert PROMPTS["v1"] == V1_PROMPT == SYSTEM_PROMPT


def test_v2_is_frozen_character_for_character():
    assert PROMPTS["v2"] == V2_PROMPT
    guided = with_descriptions(OrderDesk().registry(), "v2")
    assert {n: s.description for n, s in guided.items()} == V2_DESCRIPTIONS
    assert guided["lookup_order"].parameters["properties"]["order_id"]["description"] == (
        "The numeric order id exactly as the customer gave it. Never make one up.")
    assert guided["issue_refund"].parameters["properties"]["amount"]["description"] == (
        "Refund amount in dollars: the amount the customer stated, or the order total for a full refund.")


def test_v1_tool_descriptions_are_unchanged():
    registry = OrderDesk().registry()
    assert {n: s.description for n, s in registry.items()} == V1_DESCRIPTIONS
    assert with_descriptions(registry, "v1") is registry
    assert registry["lookup_order"].parameters["properties"]["order_id"]["description"] == "The numeric order id"


def test_the_baseline_agent_sends_exactly_the_v1_words(telemetry):
    model = received_by(telemetry, preset("baseline"))
    assert model.messages[0] == {"role": "system", "content": V1_PROMPT}
    assert {t["function"]["name"]: t["function"]["description"] for t in model.tools} == V1_DESCRIPTIONS
    assert model.tools == [t.schema() for t in OrderDesk().registry().values()]


def test_an_agent_built_without_a_config_is_the_baseline(telemetry):
    model = Recorder()
    AgentRunner(model, OrderDesk().registry(), telemetry.tracer()).run("run-g", "hello")
    assert model.messages[0]["content"] == V1_PROMPT


# ---- v2 is what the configured agent receives ---------------------------------------------------------
def test_guided_agent_sends_v2(telemetry):
    model = received_by(telemetry, preset("guided"))
    assert model.messages[0]["content"] == PROMPTS["v2"] != V1_PROMPT
    described = {t["function"]["name"]: t["function"] for t in model.tools}
    assert all(described[n]["description"] != V1_DESCRIPTIONS[n] for n in V1_DESCRIPTIONS)
    assert "Never make one up" in described["lookup_order"]["parameters"]["properties"]["order_id"]["description"]


def test_prompt_and_descriptions_are_switched_independently(telemetry):
    prompt_only = received_by(telemetry, AgentConfig(name="p", prompt_version="v2"))
    assert prompt_only.messages[0]["content"] == PROMPTS["v2"]
    assert {t["function"]["name"]: t["function"]["description"] for t in prompt_only.tools} == V1_DESCRIPTIONS
    tools_only = received_by(telemetry, AgentConfig(name="t", tool_descriptions="v2"))
    assert tools_only.messages[0]["content"] == V1_PROMPT


def test_guidance_does_not_touch_tool_behaviour_or_the_shared_registry():
    registry = OrderDesk().registry()
    guided = with_descriptions(registry, "v2")
    assert {n: s.fn for n, s in guided.items()} == {n: s.fn for n, s in registry.items()}
    assert {n: s.description for n, s in registry.items()} == V1_DESCRIPTIONS  # the original is not mutated
    assert registry["issue_refund"].parameters["properties"]["amount"]["description"] == "Refund amount in dollars"
    assert {n: s.parameters["required"] for n, s in guided.items()} == {n: s.parameters["required"] for n, s in registry.items()}


def test_v2_keeps_every_v1_rule():
    assert PROMPTS["v2"].startswith(V1_PROMPT)


def test_presets_combine_the_two_groups_as_documented():
    assert PRESETS["guided"].retries == 0 and not PRESETS["guided"].enforce_contracts and PRESETS["guided"].prompt_version == "v2"
    assert PRESETS["resilient"].prompt_version == "v1" and PRESETS["resilient"].tool_descriptions == "v1"
    full = PRESETS["full"]
    assert (full.retries, full.enforce_contracts, full.prompt_version, full.tool_descriptions) == (2, True, "v2", "v2")
    assert PRESETS["baseline"] == AgentConfig()


def test_unknown_versions_are_rejected():
    with pytest.raises(ValueError):
        AgentConfig(prompt_version="v9")
    with pytest.raises(ValueError):
        AgentConfig(tool_descriptions="v9")
    with pytest.raises(ValueError):
        system_prompt("v9")


# ---- v2 is general, not an answer key -----------------------------------------------------------------
def _added_text(version: str) -> str:
    """Everything the given version says that v1 did not."""
    registry = OrderDesk().registry()
    guided = with_descriptions(registry, version)
    parts = [PROMPTS[version].removeprefix(V1_PROMPT)]
    for name, spec in guided.items():
        parts.append(spec.description)
        parts += [p.get("description", "") for p in spec.parameters["properties"].values()]
    return " ".join(parts)


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_guidance_mentions_no_order_number_amount_or_phrase_from_any_benchmark_case(version):
    text = _added_text(version).lower()
    seeded_ids = {str(i) for i in OrderDesk().orders} | {"999", "12345"}
    assert not [n for n in seeded_ids if re.search(rf"\b{n}\b", text)]
    forbidden_words = {"cancel", "password", "email", "vip", "manager", "supervisor", "office", "override", "tuesday",
                       "damaged", "colour", "house", "moved", "elm", "pine", "oak", "reroute", "reset", "return"}
    assert not [w for w in forbidden_words if re.search(rf"\b{w}\b", text)]
    for dataset in ("golden-v2", "holdout-v1"):  # and no benchmark task is quoted
        for case in load_dataset(dataset).cases:
            assert case.task.lower().rstrip(".?!") not in text, case.id
    dollars = re.findall(r"\$\s?\d+", text)
    assert not dollars, dollars  # no concrete amount: the $100 limit lives in the policy and the tools, not in the new guidance


# ---- v3: the second attempt, written from the diagnosis of v2 ----------------------------------------------
V3_UNDONE = ("take no action until they answer", "do not try a different action instead")  # the diagnosed phrases


def test_v3_keeps_the_v1_rules_and_differs_from_v2():
    assert PROMPTS["v3"].startswith(V1_PROMPT) and PROMPTS["v3"] != PROMPTS["v2"]
    assert (system_prompt("v3"), with_descriptions(OrderDesk().registry(), "v3")["lookup_order"].description) != (
        PROMPTS["v2"], V2_DESCRIPTIONS["lookup_order"])


def test_v3_states_each_rule_separately_and_drops_what_made_v2_over_ask():
    prompt = PROMPTS["v3"]
    assert not any(phrase in prompt for phrase in V3_UNDONE)
    assert "Never decide yourself whether a refund is allowed" in prompt  # no invented "no refunds once delivered"
    assert "only an order that has not been delivered yet can have its shipping address changed" in prompt
    assert "Use what the customer has already told you" in prompt  # the cure for asking again
    described = with_descriptions(OrderDesk().registry(), "v3")
    assert all("ask" in described[n].description for n in ("lookup_order", "check_refund_policy", "update_shipping_address"))
    assert "Never make one up" in described["lookup_order"].parameters["properties"]["order_id"]["description"]
    assert "from the customer's message" in described["lookup_order"].parameters["properties"]["order_id"]["description"]
    assert "follow its answer" in described["check_refund_policy"].description
    changed = {n for n in V2_DESCRIPTIONS if described[n].description != V2_DESCRIPTIONS[n]}
    assert changed == {"lookup_order", "check_refund_policy", "update_shipping_address"}  # issue_refund's text is unchanged


def test_v3_presets_use_v3_and_the_old_presets_stay_on_v2(telemetry):
    for name, retries in (("guided-v3", 0), ("full-v3", 2)):
        config = preset(name)
        assert (config.prompt_version, config.tool_descriptions, config.retries) == ("v3", "v3", retries)
    assert (preset("guided").prompt_version, preset("full").tool_descriptions) == ("v2", "v2")
    model = received_by(telemetry, preset("guided-v3"))
    assert model.messages[0]["content"] == PROMPTS["v3"]
    assert {t["function"]["name"]: t["function"]["description"] for t in model.tools}["issue_refund"] == (
        with_descriptions(OrderDesk().registry(), "v3")["issue_refund"].description)
