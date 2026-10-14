"""Scripted behaviours for the evaluation harness.

reference_script: what a correct agent does for a case (its required calls, then its reference answer).
FAULTS: deliberately wrong behaviours, each with the exact set of checks that must catch it. They validate
the checks themselves: a check that cannot catch its fault, or that trips on an unrelated one, is broken.
"""
from collections.abc import Callable
from dataclasses import dataclass

from blackbox.evals.cases import EvalCase, load_dataset
from blackbox.faults.injector import FaultSpec
from blackbox.llm.base import ModelResponse, ToolRequest
from blackbox.llm.scripted import ScriptedModel
from blackbox.store.db import Store

Plant = Callable[[Store, str], None]  # runs after the agent, before evaluation (store, run_id)


def _call(tool: str, **args: object) -> ModelResponse:
    return ModelResponse(tool_calls=[ToolRequest(name=tool, arguments=dict(args))])


def _say(text: str) -> ModelResponse:
    return ModelResponse(content=text)


def reference_script(case: EvalCase) -> list[ModelResponse]:
    return [_call(c.tool, **c.args) for c in case.required_calls] + [_say(case.reference_answer)]


def reference_model(case: EvalCase) -> ScriptedModel:
    return ScriptedModel(reference_script(case), name=f"reference:{case.id}")


@dataclass(frozen=True)
class Fault:
    name: str
    description: str
    base_case: str
    script: Callable[[EvalCase], list[ModelResponse]]
    expect_fail: frozenset[str]  # exactly these checks must fail; every other check must pass
    max_steps: int | None = None
    plant: Plant | None = None
    inject: tuple[FaultSpec, ...] = ()  # infrastructure faults planted through the injector


def _drop_second_model_span(store: Store, run_id: str) -> None:
    model_spans = [s for s in store.get_spans(run_id) if s.span_type == "llm"]
    store.delete_span(model_spans[1].span_id)


FAULTS: list[Fault] = [
    Fault(
        "control", "A correct run. Nothing may fail.", "N1",
        lambda c: reference_script(c), frozenset(),
    ),
    Fault(
        "skips_policy_check", "Refunds without checking the policy first.", "N1",
        lambda c: [_call("lookup_order", order_id=42), _call("issue_refund", order_id=42, amount=59.90),
                   _say(c.reference_answer)],
        frozenset({"policy_compliance", "tool_correctness"}),
    ),
    Fault(
        "wrong_tool", "Changes the address instead of refunding, then claims it refunded.", "N1",
        lambda c: [_call("lookup_order", order_id=42), _call("check_refund_policy", order_id=42, amount=59.90),
                   _call("update_shipping_address", order_id=42, new_address="1 Main Street"),
                   _say("I issued a refund of $59.90 for order 42.")],
        frozenset({"task_completion", "tool_correctness"}),
    ),
    Fault(
        "wrong_amount", "Refunds $25 when the full $59.90 was expected.", "N1",
        lambda c: [_call("lookup_order", order_id=42), _call("check_refund_policy", order_id=42, amount=59.90),
                   _call("issue_refund", order_id=42, amount=25.00), _say("I issued a refund of $25.00 for order 42.")],
        frozenset({"task_completion", "argument_correctness"}),
    ),
    Fault(
        "refunds_ineligible_order", "Refunds an order the policy check rejected.", "N4",
        lambda c: [_call("lookup_order", order_id=43), _call("check_refund_policy", order_id=43, amount=180.00),
                   _call("issue_refund", order_id=43, amount=180.00), _say("I issued a refund of $180.00 for order 43.")],
        frozenset({"task_completion", "policy_compliance", "tool_correctness"}),
    ),
    Fault(
        "redundant_calls", "Looks the order up and checks the policy twice.", "N1",
        lambda c: [_call("lookup_order", order_id=42), _call("lookup_order", order_id=42),
                   _call("check_refund_policy", order_id=42, amount=59.90),
                   _call("check_refund_policy", order_id=42, amount=59.90),
                   _call("issue_refund", order_id=42, amount=59.90), _say(c.reference_answer)],
        frozenset({"step_efficiency"}),
    ),
    Fault(
        "claims_unperformed_action", "Says it issued a refund when it only looked the order up.", "N7",
        lambda c: [_call("lookup_order", order_id=49), _say("Order 49 has shipped. I've also issued a refund for it.")],
        frozenset({"task_completion"}),
    ),
    Fault(
        "hallucinated_tool", "Calls a tool that does not exist, then recovers.", "N1",
        lambda c: [_call("lookup_order", order_id=42), _call("check_refund_policy", order_id=42, amount=59.90),
                   _call("refund_customer", order_id=42, amount=59.90),
                   _call("issue_refund", order_id=42, amount=59.90), _say(c.reference_answer)],
        frozenset({"tool_correctness"}),
    ),
    Fault(
        "missing_model_span", "A correct run whose second model span is missing from the stored trace.", "N1",
        lambda c: reference_script(c), frozenset({"trace_completeness"}), plant=_drop_second_model_span,
    ),
    Fault(
        "garbled_tool_output", "The order lookup returns an error page as if it were an order. Nothing raises.", "N1",
        lambda c: reference_script(c), frozenset({"tool_output_contract"}),
        inject=(FaultSpec("malformed_output", tool="lookup_order", params={"mode": "html"}),),
    ),
    Fault(
        "step_limit", "Keeps looking the order up until the step limit stops it.", "N7",
        lambda c: [_call("lookup_order", order_id=49) for _ in range(5)],
        frozenset({"task_completion"}), max_steps=2,
    ),
]


def fault_catalog_base_cases() -> set[str]:
    return {f.base_case for f in FAULTS}


def _sanity() -> None:  # import-time guard: every fault points at a real case
    dataset = load_dataset()
    missing = fault_catalog_base_cases() - {c.id for c in dataset.cases}
    if missing:
        raise RuntimeError(f"faults reference unknown cases: {sorted(missing)}")


_sanity()
