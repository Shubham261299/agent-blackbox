"""Where should you look first? Ranks spans from the recorded trace and the check results.

It never sees what was injected, and it does not read exception text or stack traces: only span status,
the spans that failed checks name, and the tool-output contract. Signals, strongest first:

  tier 0  a successful tool span whose output breaks its contract (silent corruption)
  tier 1  spans named by a failed gating check (policy, task completion)
  tier 2  spans named by a failed reported check
  tier 3  spans with error status

The run span is a consequence, not a cause: any signal naming it is dropped when something beneath it is suspect.

Within a tier the earliest span wins (an early mistake explains the ones after it). A span flagged by several
signals keeps its strongest. This is a heuristic, validated by the failure lab on a handful of faults; it is
not a general root-cause finder.
"""
from blackbox.evals.checks import CONTRACT
from blackbox.evals.trajectory import Trajectory
from blackbox.models import CheckResult, Suspect


def _tier(check: CheckResult) -> int:
    if check.metric == CONTRACT:
        return 0
    return 1 if check.gating else 2


def locate(traj: Trajectory, checks: list[CheckResult]) -> list[Suspect]:
    spans = {s.span_id: s for s in traj.spans}
    found: dict[str, tuple[int, str, str]] = {}  # span id -> (tier, source, reason) of its strongest signal

    def note(span_id: str, tier: int, source: str, reason: str) -> None:
        if span_id in spans and (span_id not in found or tier < found[span_id][0]):
            found[span_id] = (tier, source, reason)

    for check in checks:
        if check.passed is False:
            for span_id in check.span_ids:
                note(span_id, _tier(check), check.metric.replace("_", " "), check.reason)

    errored = [s for s in traj.spans if s.status == "error"]
    below_root = [s for s in errored if s.parent_span_id is not None]
    for span in below_root or errored:  # the run span only counts when nothing beneath it failed
        note(span.span_id, 3, "error status", span.status_message or "the span ended with an error")

    # Anything naming the run span only says the run failed; that is the consequence. Keep it as a suspect
    # only when nothing beneath it is suspect.
    root_ids = {sid for sid, span in spans.items() if span.parent_span_id is None}
    if any(sid not in root_ids for sid in found):
        found = {sid: signal for sid, signal in found.items() if sid not in root_ids}

    ranked = sorted(found.items(), key=lambda kv: (kv[1][0], spans[kv[0]].start_offset_ms, spans[kv[0]].parent_span_id is not None))
    return [
        Suspect(span_id=span_id, span_name=spans[span_id].name, tier=tier, source=source, reason=reason)
        for span_id, (tier, source, reason) in ranked
    ]
