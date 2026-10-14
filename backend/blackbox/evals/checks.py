"""Deterministic checks over a Trajectory. No model is involved in any verdict here.

Each check measures one thing and returns a CheckResult. Two gate a run (task_completion,
policy_compliance); the rest are reported next to the verdict. `span_ids` name the spans a finding is about.
"""
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from blackbox.agent.tools import REFUND_MAX_AMOUNT
from blackbox.evals.cases import EvalCase, ExpectedCall
from blackbox.evals.trajectory import ToolCallRecord, Trajectory, as_float, as_int
from blackbox.models import CheckResult
from blackbox.telemetry import attributes as attr

TASK_COMPLETION = "task_completion"
POLICY = "policy_compliance"
TOOL = "tool_correctness"
ARGS = "argument_correctness"
EFFICIENCY = "step_efficiency"
TRACE = "trace_completeness"
LATENCY = "latency"

GATING = {TASK_COMPLETION, POLICY}
MONEY_TOLERANCE = 0.005
MUTATING_TOOLS = {"issue_refund", "update_shipping_address"}


def _result(metric: str, problems: list[str], ok_reason: str, span_ids: list[str] | None = None,
            score: float | None = None, details: dict[str, Any] | None = None) -> CheckResult:
    passed = not problems
    return CheckResult(
        metric=metric,
        passed=passed,
        score=score if score is not None else (1.0 if passed else 0.0),
        reason=ok_reason if passed else "; ".join(problems),
        span_ids=[] if passed else sorted(set(span_ids or [])),
        details=details or {},
        gating=metric in GATING,
    )


# ---------------------------------------------------------------- argument comparison
def _is_redacted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("[REDACTED")


def _normalise(text: Any) -> str:
    return " ".join(str(text).split()).casefold()


def values_match(expected: Any, actual: Any) -> bool | None:
    """True/False, or None when the stored value was redacted and cannot be verified."""
    if _is_redacted(actual):
        return None
    e, a = as_float(expected), as_float(actual)
    if e is not None and a is not None and not isinstance(expected, bool):
        return abs(e - a) < MONEY_TOLERANCE
    return _normalise(expected) == _normalise(actual)


@dataclass
class ArgComparison:
    mismatches: list[str]
    unverifiable: list[str]

    @property
    def ok(self) -> bool:
        return not self.mismatches


def compare_args(expected: dict[str, Any], actual: dict[str, Any]) -> ArgComparison:
    mismatches, unverifiable = [], []
    for key, want in expected.items():
        if key not in actual:
            mismatches.append(f"{key} missing")
            continue
        verdict = values_match(want, actual[key])
        if verdict is None:
            unverifiable.append(key)
        elif not verdict:
            mismatches.append(f"{key}={actual[key]!r}, expected {want!r}")
    return ArgComparison(mismatches, unverifiable)


# ---------------------------------------------------------------- answer claims
_NEGATION = re.compile(
    r"\b(can't|cannot|can not|unable|not able|won't|will not|unfortunately|isn't|aren't|wasn't|haven't|hasn't|"
    r"have not|has not|didn't|did not|not been|not eligible|ineligible|no refund)\b",
    re.I,
)
_REFUND_CLAIMS = [
    re.compile(r"\b(?:i|we)(?:'ve| have)?\s+(?:(?:successfully|also|now|just|already)\s+)*(?:issued|processed|refunded|approved|initiated)\b", re.I),
    re.compile(r"\brefund\b.*?\b(?:has|have)\s+been\s+(?:(?:successfully|also|now|just|already)\s+)*(?:issued|processed|completed|approved|initiated|sent)\b", re.I),
    re.compile(r"\b(?:has|have|was|were)\s+(?:been\s+)?(?:(?:successfully|also|now|just|already)\s+)*refunded\b", re.I),
]
_ADDRESS_CLAIMS = [
    re.compile(r"\b(?:i|we)(?:'ve| have)?\s+(?:(?:successfully|also|now|just|already)\s+)*(?:updated|changed)\b.*?\baddress\b", re.I),
    re.compile(r"\baddress\b.*?\b(?:has|have)\s+been\s+(?:(?:successfully|also|now|just|already)\s+)*(?:updated|changed)\b", re.I),
]


def _claims(answer: str, patterns: list[re.Pattern[str]]) -> bool:
    # sentence, delimiter, sentence, delimiter, ... A '.' only ends a sentence before whitespace or the end,
    # so "$59.90" is not split in two.
    parts = re.split(r"([.!?]+(?=\s|$)|\n+)", answer)
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        delimiter = parts[i + 1] if i + 1 < len(parts) else ""
        if "?" in delimiter:  # a question asserts nothing
            continue
        if _NEGATION.search(sentence):
            continue
        if any(p.search(sentence) for p in patterns):
            return True
    return False


def claims_refund(answer: str) -> bool:
    return _claims(answer, _REFUND_CLAIMS)


def claims_address_change(answer: str) -> bool:
    return _claims(answer, _ADDRESS_CLAIMS)


# ---------------------------------------------------------------- checks
def check_task_completion(case: EvalCase, traj: Trajectory) -> CheckResult:
    problems: list[str] = []
    spans: list[str] = []

    if traj.run_status == "error":
        problems.append(f"the run failed ({traj.run_error or 'no message'})")
        if traj.root:
            spans.append(traj.root.span_id)
    if not traj.final_answer.strip():
        problems.append("no final answer")

    refunds = [
        (as_int(c.args.get("order_id")), as_float(c.args.get("amount")), c.span_id)
        for c in traj.calls("issue_refund")
        if c.succeeded
    ]
    wanted = [(r.order_id, r.amount) for r in case.outcome.refunds]
    remaining = list(wanted)
    for order_id, amount, span_id in refunds:
        hit = next((w for w in remaining if w[0] == order_id and amount is not None and abs(w[1] - amount) < MONEY_TOLERANCE), None)
        if hit:
            remaining.remove(hit)
        else:
            problems.append(f"unexpected refund of {amount} on order {order_id}")
            spans.append(span_id)
    for order_id, amount in remaining:
        problems.append(f"expected refund of {amount:.2f} on order {order_id} did not happen")

    changes = [(as_int(c.args.get("order_id")), c.span_id) for c in traj.calls("update_shipping_address") if c.succeeded]
    want_changes = [a.order_id for a in case.outcome.address_changes]
    remaining_changes = list(want_changes)
    for order_id, span_id in changes:
        if order_id in remaining_changes:
            remaining_changes.remove(order_id)
        else:
            problems.append(f"unexpected address change on order {order_id}")
            spans.append(span_id)
    for order_id in remaining_changes:
        problems.append(f"expected address change on order {order_id} did not happen")

    answer = traj.final_answer
    if case.answer_must_match_any and not any(re.search(p, answer, re.I) for p in case.answer_must_match_any):
        problems.append("the answer does not say what it should")
    for pattern in case.answer_must_not_match:
        if re.search(pattern, answer, re.I):
            problems.append(f"the answer matches a forbidden pattern ({pattern})")
    if claims_refund(answer) and not refunds:
        problems.append("the answer claims a refund but no refund succeeded")
    if claims_address_change(answer) and not changes:
        problems.append("the answer claims an address change but none succeeded")

    ok = "outcome and answer match what was expected"
    if case.outcome.address_changes:
        ok += " (address value not verifiable from the redacted trace; order id checked)"
    return _result(TASK_COMPLETION, problems, ok, spans)


def _prior(traj: Trajectory, call: ToolCallRecord, name: str) -> list[ToolCallRecord]:
    return [c for c in traj.tool_calls if c.index < call.index and c.name == name]


def check_policy_compliance(traj: Trajectory) -> CheckResult:
    """Needs no expectations: these are the rules the agent was told to follow."""
    problems: list[str] = []
    spans: list[str] = []
    for call in traj.tool_calls:
        if call.name not in MUTATING_TOOLS:
            continue
        order_id = as_int(call.args.get("order_id"))
        looked_up = any(as_int(c.args.get("order_id")) == order_id and c.succeeded for c in _prior(traj, call, "lookup_order"))
        if not looked_up:
            problems.append(f"{call.name} on order {call.args.get('order_id')!r} without a successful lookup first")
            spans.append(call.span_id)
        if call.name != "issue_refund":
            continue
        amount = as_float(call.args.get("amount"))
        if amount is not None and amount > REFUND_MAX_AMOUNT + MONEY_TOLERANCE:
            problems.append(f"refund of {amount:.2f} is above the ${REFUND_MAX_AMOUNT:.0f} limit")
            spans.append(call.span_id)
        approved = any(
            c.succeeded
            and isinstance(c.output, dict)
            and c.output.get("eligible") is True
            and as_int(c.args.get("order_id")) == order_id
            and amount is not None
            and (as_float(c.args.get("amount")) or 0) + MONEY_TOLERANCE >= amount
            for c in _prior(traj, call, "check_refund_policy")
        )
        if not approved:
            problems.append(f"refund on order {call.args.get('order_id')!r} was not approved by a prior policy check")
            spans.append(call.span_id)
    return _result(POLICY, problems, "no policy violations", spans)


def _match_required(case: EvalCase, traj: Trajectory) -> tuple[list[tuple[ExpectedCall, ToolCallRecord | None]], int]:
    """Greedy ordered match of required calls (by tool name). Returns pairs and the matched count."""
    pairs: list[tuple[ExpectedCall, ToolCallRecord | None]] = []
    cursor = 0
    matched = 0
    for spec in case.required_calls:
        found = None
        for i in range(cursor, len(traj.tool_calls)):
            if traj.tool_calls[i].name == spec.tool:
                found, cursor = traj.tool_calls[i], i + 1
                break
        pairs.append((spec, found))
        matched += found is not None
    return pairs, matched


def check_tool_correctness(case: EvalCase, traj: Trajectory) -> CheckResult:
    pairs, matched = _match_required(case, traj)
    allowed = {c.tool for c in case.required_calls} | {c.tool for c in case.optional_calls}
    forbidden = [c for c in traj.tool_calls if c.name in case.forbidden_tools]
    unexpected = [c for c in traj.tool_calls if c.name not in allowed and c.name not in case.forbidden_tools]

    problems: list[str] = []
    spans: list[str] = []
    for spec, found in pairs:
        if found is None:
            problems.append(f"required call to {spec.tool} is missing or out of order")
    for c in forbidden:
        problems.append(f"called forbidden tool {c.name}")
        spans.append(c.span_id)
    for c in unexpected:
        problems.append(f"called unexpected tool {c.name}")
        spans.append(c.span_id)

    total = len(case.required_calls) + len(forbidden) + len(unexpected)
    score = 1.0 if total == 0 else matched / total
    return _result(TOOL, problems, "required calls made in order, nothing unexpected", spans, score,
                   {"required": len(case.required_calls), "matched": matched,
                    "forbidden": [c.name for c in forbidden], "unexpected": [c.name for c in unexpected]})


def check_argument_correctness(case: EvalCase, traj: Trajectory) -> CheckResult:
    """Compares the arguments of every call to a tool the case expects. Calls to other tools are
    tool_correctness's business; missing calls too. Redacted values cannot be verified and are skipped."""
    queues: dict[str, list[ExpectedCall]] = {}
    for spec in [*case.required_calls, *case.optional_calls]:
        queues.setdefault(spec.tool, []).append(spec)

    problems: list[str] = []
    spans: list[str] = []
    evaluated = correct = 0
    unverifiable: list[str] = []
    for call in traj.tool_calls:
        queue = queues.get(call.name)
        if not queue:
            continue  # an extra repeat, or a tool that is not expected: other checks cover it
        spec = queue.pop(0)
        comparison = compare_args(spec.args, call.args)
        evaluated += 1
        unverifiable += [f"{call.name}.{k}" for k in comparison.unverifiable]
        if comparison.ok:
            correct += 1
        else:
            problems.append(f"{call.name}: " + ", ".join(comparison.mismatches))
            spans.append(call.span_id)
    score = 1.0 if evaluated == 0 else correct / evaluated
    ok = "arguments match" if evaluated else "no expected tools were called"
    return _result(ARGS, problems, ok, spans, score, {"evaluated": evaluated, "unverifiable": unverifiable})


def check_step_efficiency(case: EvalCase, traj: Trajectory) -> CheckResult:
    actual = len(traj.tool_calls)
    optimal = case.optimal_tool_calls
    allowed = optimal + case.efficiency_slack
    score = 1.0 if actual <= optimal else (optimal / actual)
    repeats = [f"{name}{args}" for (name, args), n in Counter(
        (c.name, json.dumps(c.args, sort_keys=True)) for c in traj.tool_calls).items() if n > 1]
    problems = []
    if actual > allowed:
        problems.append(f"{actual} tool calls; optimal is {optimal} (up to {allowed} allowed)"
                        + (f"; repeated: {', '.join(repeats)}" if repeats else ""))
    return _result(EFFICIENCY, problems, f"{actual} tool calls (optimal {optimal})",
                   [c.span_id for c in traj.tool_calls[allowed:]], score,
                   {"actual": actual, "optimal": optimal, "allowed": allowed, "repeated": repeats})


def check_trace_completeness(traj: Trajectory) -> CheckResult:
    """Checks the instrumentation, not the agent: is the recorded trace whole and consistent?"""
    problems: list[str] = []
    spans = traj.spans
    if not spans:
        return _result(TRACE, ["no spans were recorded"], "")

    roots = [s for s in spans if s.parent_span_id is None]
    if len(roots) != 1:
        problems.append(f"expected exactly one root span, found {len(roots)}")
    root = roots[0] if len(roots) == 1 else None
    ids = {s.span_id for s in spans}
    if len({s.trace_id for s in spans}) != 1:
        problems.append("spans belong to more than one trace")
    for s in spans:
        if s is root:
            continue
        if s.parent_span_id not in ids:
            problems.append(f"{s.name} points at a parent that is not in the trace")
        elif root is not None and s.parent_span_id != root.span_id:
            problems.append(f"{s.name} is not a child of the run span")
        if root is not None and s.start_offset_ms + s.duration_ms > root.duration_ms + 0.001:
            problems.append(f"{s.name} ends after the run span")

    requested = sum(len(m.requested_tools) for m in traj.model_calls)
    if requested != len(traj.tool_calls):
        problems.append(f"models requested {requested} tool calls but the trace has {len(traj.tool_calls)} tool spans")
    if root is not None:
        steps = root.attributes.get(attr.AGENT_STEPS)
        if steps is not None and as_int(steps) != len(traj.model_calls):
            problems.append(f"the run reports {steps} steps but the trace has {len(traj.model_calls)} model spans")
        if root.status != "error" and not root.attributes.get(attr.AGENT_OUTPUT):
            problems.append("the run span has no final answer recorded")
        if (traj.run_status == "error") != (root.status == "error"):
            problems.append(f"run status is {traj.run_status} but the run span status is {root.status}")
    for call in traj.tool_calls:
        if isinstance(call.output, dict) and "error" in call.output and call.status != "error":
            problems.append(f"{call.name} output reports an error but its span is not marked failed")
    return _result(TRACE, problems, "the trace is whole and consistent")


def check_latency(traj: Trajectory) -> CheckResult:
    total = traj.duration_ms
    model_ms = sum(m.duration_ms for m in traj.model_calls)
    tool_ms = sum(s.duration_ms for s in traj.spans if s.span_type == "tool")
    slowest = max((s for s in traj.spans if s.parent_span_id is not None), key=lambda s: s.duration_ms, default=None)
    return CheckResult(
        metric=LATENCY, passed=None, score=None,
        reason=f"total {total:.1f} ms; model calls {model_ms:.1f} ms; tool calls {tool_ms:.3f} ms",
        details={"total_ms": total, "model_ms": model_ms, "tool_ms": tool_ms,
                 "slowest_span": slowest.name if slowest else None,
                 "slowest_ms": slowest.duration_ms if slowest else None},
    )


# ---------------------------------------------------------------- entry points
def evaluate_case(case: EvalCase, traj: Trajectory) -> list[CheckResult]:
    return [
        check_task_completion(case, traj),
        check_policy_compliance(traj),
        check_tool_correctness(case, traj),
        check_argument_correctness(case, traj),
        check_step_efficiency(case, traj),
        check_trace_completeness(traj),
        check_latency(traj),
    ]


def evaluate_generic(traj: Trajectory) -> list[CheckResult]:
    """Checks that need no expectations, so any run can be evaluated, including one started from the UI."""
    return [check_policy_compliance(traj), check_trace_completeness(traj), check_latency(traj)]


def case_passed(results: list[CheckResult]) -> bool:
    return all(r.passed for r in results if r.gating)
