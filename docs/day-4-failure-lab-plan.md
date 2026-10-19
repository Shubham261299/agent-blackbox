# Day 4 plan: the failure lab

Status: **built.** Decisions below were taken to keep moving; each is cheap to change. See section 11 for where the build differs.

## 1. Goal

Plant a known failure in a run, then answer three questions from the recorded trace alone:

1. **Where?** Does trace analysis point at the right span, without being told the answer?
2. **What did it do to the run?** Compare the same task with and without the fault.
3. **Would anything else have noticed?** Some failures raise an error. Some corrupt data silently.

This is the project's "debugging" leg: observability (the trace) plus evaluation (the checks) used to find a cause.

## 2. The four faults

All four are planted into the same refund task (case N1) so their effects are comparable.

| Fault | Where it is injected | What the run sees | Why it is interesting |
|---|---|---|---|
| `tool_timeout` | a tool call (`check_refund_policy`) sleeps, then raises a timeout | tool span errors, the exception is not handled, the run fails | the loud failure: error status and exception event, plus real elapsed time |
| `malformed_output` | a tool (`lookup_order`) returns an HTML error page instead of an order | tool span is **ok**, no error anywhere | the silent failure: only a contract on tool outputs can notice |
| `wrong_tool` | the model's first tool call is swapped for `update_shipping_address` | a tool runs that should not have, before any lookup | a decision failure: visible only against the policy and the expected tools |
| `model_error` | the second model call raises | model span errors, the run fails midway | the dependency failure (what an unreachable Ollama looks like) |

The timeout is deliberately **not** a recoverable tool error. The baseline agent has no handling for infrastructure failures, so a timeout kills the run. Day 5's fix (retry with a limit) then has something measurable to improve.

## 3. How faults are injected

Two seams, both wrappers, so the agent code is untouched:

- **Tool seam:** wraps a tool function (timeout, malformed output).
- **Model seam:** wraps a `ModelClient` (wrong tool, model error). It works on the scripted model and on the real one.

A `FaultSpec` says which kind, which tool or call, which occurrence, and its parameters. The injector records what it fired. After the run, the harness resolves that to the **origin span**: the first span where the deviation is observable. That is stored out of band (a `run_faults` row), never as an attribute in the trace, so the analysis cannot read the answer.

For `wrong_tool` the origin is the tool span that executed the wrong call, not the model span that chose it. That is the first place a trace reader could see something wrong.

## 4. Failure localization

`evals/localize.py` turns a trajectory and its check results into ranked **suspects**, with no knowledge of the injected fault:

| Tier | Signal |
|---|---|
| 0 | a successful tool span whose output breaks its contract |
| 1 | spans named by a failed **gating** check (policy, task) |
| 2 | spans named by a failed reported check |
| 3 | spans with error status, innermost first (the root's error is a consequence, not a cause, when a child also failed) |

Within a tier, the earliest span wins. A span flagged by several signals keeps its best tier.

Scoring per fault: **hit@1** (top suspect is the origin span) and **hit@3**. These are the numbers the lab reports. They measure this heuristic on four faults, no more.

## 5. A new check: tool output contract

Each tool has a small contract for its successful output (required keys and types). `tool_output_contract` flags any successful tool span that violates it. It needs no case expectations, so it runs on every run, including real ones. It is also the check that makes the silent fault visible. The same contracts can be enforced at runtime on Day 5.

It joins the fault catalog (a ninth planted fault) so it is validated like the other checks.

## 6. Effect on the run

Each fault is run next to a **control** (the same task, no fault, same model). The lab stores, for both: run status, gating verdict, failed checks, duration, tool calls. The report states the effect in plain words ("run failed", "run completed but the outcome was wrong", "nothing failed: only the contract check noticed").

## 7. Modes

- `faultlab`: scripted model. Instant and repeatable. In pytest and behind a button in the UI.
- `faultlab-ollama`: the real model, from the CLI. Same faults, real downstream behaviour.

## 8. UI

- Evaluations page: a "Failure lab" option.
- Lab report: headline "n of 4 faults located at the right span", then one card per fault: what was injected and where, control against faulted run, the ranked suspects with the injected span marked, and links to both runs.
- Run detail: a callout "Fault injected: ..." with Show span, the injected span marked in the waterfall, and a **Where to look first** line in the Evaluation card for any run (injected or not).

## 9. Tests

- Injector unit tests for each kind (timing, error type, what the model and tools see).
- Contract tests per tool, including boundaries.
- Localizer tests: tier order, earliest-first, root exclusion, merging, nothing to suspect.
- The lab end to end on the scripted model: each fault's verdict, effect and hit@1.
- Mutation checks on the localizer and the contract check.

## 10. Limits we will state

- Four faults on one task is a demonstration, not a benchmark of localization.
- Scripted runs are not adaptive: after a fault the script continues as if nothing happened. The real-model lab shows what an adaptive agent does.
- Ground truth is whatever the injector fired; it is exactly as good as that mapping.

## 11. What was built, and where it differs from the plan

- **Error classes** live in `blackbox/agent/errors.py`, not next to the injector, so the exception type in a trace says what failed and not where it came from. (A test caught the original leak.)
- **The localizer drops signals on the run span** whenever a span beneath it is suspect. The first version did not, and located only 2 of 4 faults.
- **The real-model lab warms the model up first**, untraced, so the control run is not charged for loading it.
- **Fault names:** `tool_timeout`, `malformed_output`, `wrong_tool`, `model_error`. The catalog of planted *check* faults (Day 3) gained `garbled_tool_output`, which is what proves `tool_output_contract`.
- **Storage:** ground truth is in a `run_faults` table; lab results reuse the evaluation tables with kind `faultlab`.
- **Not done:** repeated runs (one run per fault); a fifth fault (empty model response); runtime enforcement of the contracts (Day 5).
- **Update, Day 5:** runtime enforcement of the contracts is built (`enforce_contracts`), and the lab was re-run on the real model against the resilient agent: timeout, model failure and malformed output became harmless (see docs/day-5-fix-and-compare-plan.md). The localizer gained a "retried" tier for recovered faults.
