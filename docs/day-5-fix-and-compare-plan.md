# Day 5 plan: fix and compare

Status: **built and measured (2026-10-19).** Sections 1-11 are the plan as written before any run, kept unedited on purpose, including the predictions in section 6; section 12 is the progress log with every result, and the summary below says where reality differed.

**Outcome in one paragraph.** Resilience worked on the real model (3 recoverable faults fixed, 0 broken, nothing changed on clean cases). Guidance did not: two attempts both regressed task completion (golden-v3: baseline 19, v2 16, v3 17 of 24) while removing every policy violation. The recommended agent is `resilient`. Decisions D1 (two switch groups, four presets), D2 (identical-settings reruns, not seeds), D3 (a held-out set) and D4 (no hard guard in the first pass) were confirmed by the owner; D5 (no real tool deadline) and D6 (no second model) stood.

**Where reality differed from the plan.** (1) The persistent timeout was not added as a fifth lab fault (it would have tested the script, not the agent); the retry limit is proven by unit tests. (2) The regression prediction was too mild (6 of 24 broken on golden-v2, 5 on golden-v3, not "at least one"). (3) A second guidance attempt (v3) was added by decision after v2 regressed, with its criterion fixed in advance. (4) A checker gap (C1/C4) was found by triage and fixed as golden-v3 with a new `rescore` command, which the plan did not anticipate. (5) The localizer gained a "retried" tier so a recovered fault can still be located. (6) The comparison UI also marks retried spans and shows the agent variant everywhere.

## 1. Goal

Day 3 measured where the agent fails. Day 4 planted failures and located them. Day 5 closes the loop: **change the agent, then prove from recorded runs whether it got better, and what it cost.**

The headline is a before/after table with three numbers that matter more than the pass rate alone:

1. **Fixed:** cases that failed before and pass now.
2. **Broken:** cases that passed before and fail now (the regression rate). A fix that breaks working cases is not a fix.
3. **Cost:** extra model calls, tool calls and seconds.

## 2. What we are fixing (from measured failures only)

| Failure (source) | Cases / faults | Kind of fix |
|---|---|---|
| Acts on an order without looking it up | N6, N8, F2 (Day 3) | guidance |
| Invents a missing value instead of asking | A2, A4, F3, F4 (Day 3) | guidance |
| Never says it cannot cancel | W1 (Day 3) | guidance |
| Tool timeout ends the run | `tool_timeout` (Day 4) | resilience: retry |
| Model backend error ends the run | `model_error` (Day 4) | resilience: retry |
| Malformed tool output passes silently | `malformed_output` (Day 4) | resilience: enforce contracts |
| Wrong tool chosen | `wrong_tool` (Day 4) | **not targeted** (see predictions) |

No fix is added for a failure nobody measured.

## 3. The fix is two independent switches, not one

One toggle would tell us "better", not **why**. So the agent takes an `AgentConfig` with two groups that can be turned on separately:

| Group | Switches | Targets |
|---|---|---|
| **Resilience** | retry limit for tool and model infrastructure errors; runtime enforcement of the tool output contracts | the Day 4 lab faults |
| **Guidance** | system prompt v2; tool descriptions v2 | the Day 3 benchmark failures |

Four named variants: `baseline` (today's behaviour, byte for byte), `resilient`, `guided`, `full` (both). The ablation costs about 20 minutes of CPU and lets the report say which half did the work.

`baseline` must stay exactly as it is, including the v1 prompt text and v1 tool descriptions, so every stored result stays reproducible and the existing 250 backend tests keep passing unchanged. That is the first test of this day.

## 4. How each fix works

### 4.1 Retry with a limit

- Retried: `ToolTimeoutError`, `ModelUnavailableError`, and a contract violation (4.2).
- **Not retried:** `ToolError` (a domain answer such as "order not found"). Asking again gives the same answer; the model should read it and decide.
- Limit: 2 retries, so 3 attempts in all. Fixed small backoff (configurable, zero in tests). When the limit is spent the tool span ends in error and the agent receives `{"error": ...}`, the same as any tool failure, so the model can tell the customer instead of the run dying. For the model call the final failure ends the run as today.
- **Trace shape does not change.** One tool span per tool call the model requested, one model span per step. Each failed attempt is an `exception`/`retry` event on that span (attempt number, error message), and the span carries an `agent.retry.count` attribute. This matters: `trace_completeness` ("models requested N calls, the trace has N tool spans") and `step_efficiency` would otherwise punish a retry as if the model had asked twice. The checks stay unchanged. The cost of a retry shows up honestly in duration and in the retry count.

### 4.2 Contract enforcement at runtime

After a tool returns, run `contract_problems` (already written on Day 4). A violation counts as a retryable failure. If every attempt violates, the span ends in error with a message that names the contract problem. The silent fault becomes a loud one the model can react to. `tool_output_contract` (the check) keeps working on stored traces as before.

### 4.3 Guidance

- **System prompt v2:** keeps the v1 rules and adds two plain rules: if the request does not state the order number, the amount or the new address, ask the customer for it and do not guess; if the request is something no tool can do (for example cancelling an order), say so.
- **Tool descriptions v2:** each action tool says which fields must come from the customer and that `lookup_order` must come first.
- **Hard rule for wording:** no order number, amount or phrase from any benchmark case may appear in the prompt. Otherwise the fix is a memorised answer key.

## 5. How the comparison stays fair

- Same dataset (the dataset hash must match), same model (`qwen2.5:7b`), same settings (temperature 0, seed 0). The comparison refuses two evaluations that differ in dataset hash or model.
- **A held-out set, written before any tuning.** The 24 golden cases are where we saw the failures, so tuning a prompt against them and reporting on them is training on the test. `holdout-v1` is 8 new cases (3 ambiguous, 2 normal with different phrasing, 2 constraint, 1 wrong-tool), written first and run on `baseline` first. Report both: "on the cases we looked at" and "on cases written before we tuned".
- **The dataset is never edited to flatter a variant.** The Day 3 triage rule still holds.
- **Noise floor.** At temperature 0 the model is near-deterministic (Day 3: 23 of 24 answers identical on a rerun), so running different seeds changes nothing and "N repeats" would mean nothing. Instead, rerun `baseline` and `full` once more at identical settings and report how many cases flipped. A difference between variants smaller than that flip count is not evidence.
- n is 24 plus 8. Report counts ("5 fixed, 1 broken"), not percentages presented as precise.

## 6. Predictions, written before any run

These are what the design implies. If a result differs, the report says so; we do not rewrite the prediction.

| Item | Prediction | Why |
|---|---|---|
| `tool_timeout` | run fails → run completes | fault fires once, a retry succeeds |
| `model_error` | run fails → run completes | same |
| `malformed_output` | silent → still completes, one extra attempt, contract check passes | the bad reply is rejected and retried instead of reaching the model |
| `wrong_tool` | unchanged | neither group addresses a wrong decision; if guidance helps here that is luck, say so |
| a **persistent** timeout (fires every time) | exactly 3 attempts, then the agent is told and the run goes on (on the scripted model the script ignores the error, so the policy check then fails) | proves the limit is a limit; sharpened from "run still ends" while building stage 2, before any lab run |
| Benchmark | some of the 5 gating failures fixed by `guided`; `resilient` changes nothing on the 24 cases (no infrastructure faults in them) | resilience cannot help where nothing infrastructure-shaped fails |
| Regressions | at least one is plausible: a longer prompt can make a 7B model over-ask on cases that were fine | state the number whatever it is |
| Cost | `resilient` costs nothing on a clean run; `guided` adds a little prompt processing time | |

## 7. What gets built

1. **`AgentConfig` and the four presets**, threaded through `RunService` and `AgentRunner`. The run and the evaluation record which variant produced them (a `variant` column on `runs` and `eval_runs`; `Store` has no migration step today, so add a guarded `ALTER TABLE`, and old rows read as `baseline`).
2. **Resilience in the loop** (4.1, 4.2).
3. **Guidance** (4.3), with the v1 text pinned by a test.
4. **Injector:** a `persistent` option so a fault can fire on every matching call, to test the retry limit.
5. **Runner and CLI:** `--variant baseline|resilient|guided|full` on every mode, a `holdout-v1` dataset, and `python -m blackbox.evals compare <baseline_eval> <candidate_eval>` that prints the table.
6. **Compare logic and API:** `GET /evals/compare?baseline=...&candidate=...` computed from two stored evaluations (not stored itself). Returns headline counts, per-case before/after, per-check and per-category changes, and cost deltas (tool calls, model calls, median seconds, tokens where recorded).
7. **Lab under variants:** the same four faults plus the persistent timeout, run on `baseline` and `full`, compared by effect (run failed / gating failed / silent / no effect) and cost.
8. **UI: a comparison view.** Headline ("5 fixed, 1 broken, 18 unchanged"), a before/after strip per case with links to both runs, the ablation as a four-column table, the lab faults before and after, and the cost. A "recovered after N retries" chip on a span that retried. Design and artifact skills apply.

Build order (each stage ends with its tests, mutation checks and a local-commit request): holdout dataset and baseline run on it → resilience + injector → guidance → plumbing, CLI, compare → real runs → UI → docs.

## 8. Tests

- `baseline` is unchanged: existing suites pass, prompt v1 and descriptions v1 are pinned byte for byte.
- Retry: succeeds on attempt 2; spends exactly 3 attempts on a persistent fault (mutation: off by one); does **not** retry a `ToolError` (mutation: retry everything); event and attribute recorded; span count unchanged.
- Contracts: enforced only when the switch is on; a malformed reply is retried; exhaustion yields an error span with the contract message.
- Existing checks still hold on retried traces (completeness and efficiency do not penalize a retry).
- Compare: counts fixed and broken correctly on hand-made evaluations; refuses a dataset-hash or model mismatch; handles cases present on one side only.
- The lab on the scripted model: each fault's before/after effect matches section 6, so a wrong prediction fails a test visibly.
- Frontend: comparison view states (loading, mismatch error, no change, all fixed, some broken).

## 9. Decisions to confirm (all confirmed or left as proposed; see the outcome above)

| # | Question | Proposed default |
|---|---|---|
| D1 | One toggle or several? | Two groups, four presets, so the result can be attributed |
| D2 | Repeats per case | None at other seeds (meaningless at temperature 0). One identical-settings rerun of `baseline` and `full` as a noise floor |
| D3 | Add a held-out set? | Yes, 8 cases, `holdout-v1`, written before tuning. Cut it if time is short and say so in the report |
| D4 | A hard "look up first" guard in code? | **No, not in the first pass.** Guidance first. If N6/N8/F2 still fail, add a guard as a separately named step. Note that `policy_compliance` counts an attempted action even when blocked, so a guard would prevent harm but not move this score, and we will not loosen the check to make it |
| D5 | Real wall-clock deadline on tools? | No. Tools are in memory and instant; the lab's timeout is a simulated error and the report says so. The model call already has the Ollama client's timeout |
| D6 | Second model (`llama3.1:8b`) | Not now. A Day 7 item if time allows |

## 10. Limits we will state

- One model, n of 24 plus 8, one run per case. Small differences are noise; the flip count says how small.
- The lab faults are simulated and fire once; real outages differ. The persistent timeout shows the limit works, not how real outages behave.
- Guidance results belong to this prompt and this 7B model. A different model could move the other way.
- Cases in the golden set were seen before tuning; only the held-out set was not.
- `wrong_tool` is expected to stay unfixed; that is a result, not a gap to hide.

## 11. Done when

A measured before/after table exists, stored from real runs: four variants on the 24 golden cases and on the held-out set, the lab faults on `baseline` and `full`, and a noise-floor rerun. The comparison view shows it, with a link from every cell to the run behind it. Every README number later comes from these stored evaluations.

## 12. Progress log

### Stage 1: held-out set and baseline on it (done, 2026-10-14)

- `holdout-v1` written first (8 cases: 2 normal, 3 ambiguous, 1 wrong-tool, 2 constraint; hash `8c7eb9ea4eb0`), before any fix existed. Tests (`test_eval_holdout.py`) check consistency, no overlap with golden-v2 ids or tasks, and that a scripted correct run of every case passes every check.
- **Baseline on the held-out set** (`qwen2.5:7b`, temperature 0, seed 0): **5 of 8 passed both gating checks** (eval-286fe069, 190 s on CPU, including model load).
- The 3 failures were triaged from the stored traces, and all are agent failures, not dataset errors: H2 changed an address without looking the order up; H4 ("refund part of order 47") invented a $30 amount and refunded it; H5 ("move my package to my office address") invented order id 12345 and tried to change its address. These are the same classes as the golden-set failures, so the held-out set can tell whether guidance generalizes.

### Stage 2: resilience (done, 2026-10-19)

- `AgentConfig` (`agent/config.py`) with presets `baseline` and `resilient` (2 retries, 0.05 s backoff, contracts enforced). `baseline` is the default and adds nothing to a trace: a test pins that a baseline trace has the same spans, no events, and no new attributes. The `guided` and `full` presets arrive with stage 3.
- Retries (tool timeout, tool contract violation, and model errors: our own `ModelUnavailableError`, `ConnectionError`, `TimeoutError`, httpx transport errors). A domain `ToolError` and any other exception are never retried.
- Every attempt happens inside the one span the model's request created, so the trace keeps one span per call. Each failed attempt is a `retry` event; the span carries `blackbox.agent.retry_count`; a non-baseline run span carries `blackbox.agent.variant`.
- When tool retries are spent, the span ends in error and the model receives `{"error": ...}`; when model retries are spent the run ends, as before. A baseline timeout still ends the run.
- Contract enforcement: a successful call whose output breaks its contract is rejected and retried; if every attempt breaks it, it becomes a failed call (error span), no longer a silent one.
- Injector: `params={"persistent": True}` fires on every call from `occurrence` on; `origin_span_id` stays on the first span hit.
- Tests: 20 new (`test_agent_resilience.py`); 296 backend in all, 1 skipped (Jaeger). Mutation-checked, all caught: tool retry off by one, model retry off by one, also retrying `ToolError`, contracts always on, baseline swallowing timeouts, retrying any model exception.
- Not yet run on the real model; that is stage 5.

### Stage 3: guidance (done, 2026-10-19)

- `agent/guidance.py` holds numbered versions of the system prompt and the tool descriptions. **v1 is the old text, pinned character for character by a test** (prompt, all four tool descriptions, the `order_id` parameter text), so Day 1-4 results stay reproducible. `AgentRunner(config=...)` picks the versions; with no config it sends exactly v1.
- **v2 adds three general rules to the prompt** (first tool call for an order request is `lookup_order`; if the order number, amount or address is missing, ask and take no action; say plainly when no tool can do the request, and do not try a different action instead) and rewrites the four tool descriptions and the `order_id` / `amount` parameter text to say the same. Nothing else changes: tools behave identically.
- **Presets:** `guided` (v2 prompt + v2 descriptions, no retries) and `full` (guidance + resilience). The two groups are independent in `AgentConfig`, so `prompt_version` and `tool_descriptions` can also be switched one at a time (tested).
- **Anti-answer-key test:** the text v2 adds contains no seeded order id, no 999 or 12345, no concrete dollar amount, none of a list of case-specific words (cancel, password, email, manager, ...), and quotes no task from golden-v2 or holdout-v1.
- **v2 is frozen before any real run.** It was written from the Day 3 failure classes only and has not been run on the real model. If it performs badly, that is the result. A later change would be a new, labelled version (v3) reported next to v2, never an edit to v2, so the held-out set stays an honest test.
- Tests: 11 new (`test_agent_guidance.py`); 307 backend in all, 1 skipped. Mutation-checked, all caught: v1 prompt edited, v2 leaking a case word, v2 leaking an amount, prompt version ignored, tool descriptions ignored, v2 mutating the shared registry, v2 dropping the v1 rules.

### Stage 4: variants, comparison, CLI and API (done, 2026-10-19)

- **Variant recorded everywhere.** `runs.variant` and `eval_runs.variant` columns. `Store` had no migration step, so a small `_add_missing_columns` adds them to an existing database; every row written before variants existed reads as `baseline` (tested on a hand-made old database, and it ran on the real one: all six earlier evaluations show `baseline`).
- **Runner.** `--variant baseline|resilient|guided|full` on every mode except `faults`, which validates the checks and refuses a variant. The lab runs its control and faulted runs on the same variant.
- **Comparison** (`evals/compare.py`, `GET /evals/compare?baseline=&candidate=`, `python -m blackbox.evals compare A B`). Counts fixed / broken / still passing / still failing over cases both sides ran; per-check and per-category changes; cost (tool calls, model calls, retries, median and total seconds, tokens only when every call reported them). It **refuses** (422, with the reason in words): comparing an evaluation with itself, a different dataset hash, model or seed, different kinds, an unfinished evaluation, and the checks-validation kind. Two runs of the same variant are allowed on purpose: that is the noise floor.
- **Lab comparison** judges a fault by its effect, not by whether trace analysis located it: "passed" means the fault had no effect on the run.
- **Localizer gained one tier, 4 "retried".** A span that needed retries is where to look even when the run recovered; found from the event's name, never its text. Without it a recovered run has no suspects at all and the lab would report every recovered fault as "missed".
- **Deviation from section 7:** the persistent timeout is *not* a fifth lab fault. Run through the lab it would be scored by the localizer on a scripted run whose script ignores the error, which tests the script, not the agent. The retry limit is proven by unit tests instead (exactly 3 attempts) and no README number will quote it.
- **Predictions held on the scripted lab** (written before the run, now a test): timeout and model failure run_failed -> no_effect, malformed output silent -> no_effect, wrong tool unchanged.
- Tests: 17 new (`test_eval_compare.py`); 325 backend in all. Mutation-checked, all caught (the first pass had two survivors, one an equivalent mutation of mine and one a real gap in the "found by name, not text" test, both fixed): fixed/broken swapped, hash, model and seed checks dropped, lab judged by location, cost counting unmatched cases, retries not counted, tokens invented, validation kind comparable, migration skipped, variant not stored, retried tier removed, retried found by text, API returning 200 for a refusal.

### Stage 5: real-model results (2026-10-19, `qwen2.5:7b`, temperature 0, seed 0; code = commit `0035a2f`)

All numbers are from stored evaluations; `python -m blackbox.evals compare <baseline> <candidate>` reproduces any row.

**Noise floor.** Baseline against the Day 3 baseline (eval-5b8f6d3c vs eval-7410381c): **0 of 24 cases flipped**. `full` against `full` (eval-67a0cc90 vs eval-a37cc205): **0 of 24 flipped**. At temperature 0 this model repeated every verdict, so every difference below is a real difference, not noise (one model, one machine, two repeats: evidence, not a guarantee).

**Golden-v2, 24 cases** (fixed / broken are against `baseline`, eval-7410381c):

| Variant | Passed | Fixed | Broken | Policy check | Task check | Tool calls | Model calls | Median run |
|---|---|---|---|---|---|---|---|---|
| baseline | 19/24 | | | 21/24 | 22/24 | 39 | 62 | 10.3 s |
| resilient (eval-7caf9bfa) | 19/24 | 0 | 0 | 21/24 | 22/24 | 39 | 62 | 10.3 s |
| guided (eval-ff0b3df7) | 15/24 | 2 | 6 | **24/24** | **15/24** | 25 | 49 | 8.3 s |
| full (eval-a37cc205) | 15/24 | 2 | 6 | 24/24 | 15/24 | 25 | 49 | 8.1 s |

**Held-out set, 8 cases** (baseline eval-286fe069, 5/8): resilient (eval-ffb8d521) 5/8, 0 fixed, 0 broken; guided (eval-bfaf8088) 5/8, 1 fixed (H5), 1 broken (H1), policy 6/8 -> 8/8, task 7/8 -> 5/8; full (eval-26376285) identical to guided.

**Failure lab on the real model** (baseline eval-7f1699f1: every fault hurt the run):

| Fault | baseline | resilient (eval-0f9152b9) |
|---|---|---|
| tool timeout | run failed | **no effect** |
| malformed tool output | silent | **no effect** |
| model call fails | run failed | **no effect** |
| wrong tool | policy failed | policy failed (unchanged, as predicted) |

Cost of the three recoveries: 3 retries, tool calls 11 -> 13, model calls 14 -> 17, median run 11.3 -> 13.0 s. On clean runs (golden and held-out, resilient) the cost was exactly zero retries and identical call counts. Under `guided` and `full` the lab is uninformative: the control run itself fails, because the agent refuses the base refund task (see below), so every fault shows an effect (guided eval-4ac00a2b, full eval-1f6b2d31).

**Against the predictions in section 6:**
- Held: timeout and model failure recover; malformed output is caught; wrong tool unchanged; `resilient` changes nothing on cases with no infrastructure faults and costs nothing there.
- Partly held: guidance fixed the lookup-first failures (N8, F2, H5; policy failures 3 -> 0 on golden, 2 -> 0 on held-out) but did **not** fix invented values (A2 still refunds an invented $10, H4 an invented $50) or the cannot-cancel case (W1).
- **Did not hold: the regression prediction was too mild.** "At least one regression is plausible" turned out to be 6 of 24 on the golden set and 1 of 8 on the held-out set. Guidance made the agent worse overall (task completion 22/24 -> 15/24), and the held-out set confirms it, so it is not just the golden cases.

**Why guidance regressed (read from the stored traces, not yet tested as a fix):**
1. *A rule leaked from one tool to another.* The agent now says "we can only process refunds for undelivered orders" and refuses valid refunds on delivered orders (N1, N2, H1). The v2 text says an address can only change for an order not yet delivered; the model applied that to refunds. The agent made this policy up, which is the invention failure again, now caused by the prompt.
2. *Over-asking.* "Ask, and take no action until they answer" made it ask for details the customer had already given (N7 "Where is order 49?", W3, W2), calling no tool at all.
3. *The "ask instead of invent" rule did not stick for amounts* on this 7B model.

**One incident.** In the first `full` run, case C1 took 47 minutes: the model backend stalled and the retry logic absorbed two real 300-second read timeouts, after which the case passed. Whether this was an Ollama stall or the laptop sleeping is unknown. It makes that run's total time (2,994 s) meaningless; use the median. It is also the only time a retry has been exercised by something other than a planted fault.

**Limits.** One model, one machine, n = 24 and 8, one run per variant (plus the noise-floor repeats). The held-out set was not seen before v2, but is no longer clean for any v3, because v2's held-out results have now been read.

### Stage 5b: guidance v3, the one labelled second attempt (2026-10-19)

**What changed, and what did not.** v2 is frozen and pinned by a test, like v1 (its stored results describe it). v3 is written from the diagnosis above and nothing else, and it is the only second attempt: it is run once, on `guided-v3` and `full-v3`, and reported next to v2 whatever happens. Changes: each tool's rule is stated on its own ("never decide yourself whether a refund is allowed: call `check_refund_policy` and follow its answer"; "only an order that has not been delivered yet can have its shipping address changed"); the ask rule becomes "use what the customer already told you, ask only when something is genuinely missing"; the phrases "take no action until they answer" and "do not try a different action instead" are gone. The anti-answer-key test covers v3 too. The phrase "partial refund" appears in v3's tool text (as it did in v2's); it names a policy concept and is also the wording of one golden task, which is stated here rather than hidden.

**Limits of this second attempt.** I had read v2's golden and held-out results before writing v3, so the held-out set is no longer a clean test for it: a v3 that does well on the held-out set is weaker evidence than v2's result was. Invented amounts are not expected to be fixed by wording (v2's attempt failed); a code-level check is a Day 7 option, not part of this.

**Predictions, written before any v3 run:**
- The refusal regression disappears: N1, N2 and H1 pass again.
- The lookup-first gains are kept: policy compliance stays 24/24 on golden and 8/8 on the held-out set; N8, F2, H5 stay fixed.
- The over-asking cases (N7, W2, W3) mostly recover.
- Invented amounts (A2, H4) and the cannot-cancel case (W1) still fail.
- Golden pass count: above the baseline's 19 if v3 works. If it is 19 or below, v3 failed and that is the result.
- The lab on `full-v3`: the control passes, and the three recoverable faults behave as under `resilient` (3 fixed, wrong tool unchanged).

### Stage 5b results: v3 did not work (2026-10-19, same model and settings; code = working tree after commit `0035a2f`)

| Variant | Golden (24) | Fixed / broken vs baseline | Policy | Task | Held-out (8) | Held-out policy / task |
|---|---|---|---|---|---|---|
| baseline | 19 (eval-7410381c) | | 21/24 | 22/24 | 5 (eval-286fe069) | 6/8, 7/8 |
| guided (v2) | 15 (eval-ff0b3df7) | 2 / 6 | 24/24 | 15/24 | 5 (eval-bfaf8088) | 8/8, 5/8 |
| guided-v3 | 15 (eval-212048d0) | 1 / 5 | 24/24 | 15/24 | 5 (eval-dac487a9) | 7/8, 6/8 |
| full-v3 | 15 (eval-a8e43948) | | | | 5 (eval-7d90c662) | |

By the criterion written before the run (golden pass count above 19), **v3 failed.** It is the same count as v2 with different cases: against v2 it fixed 3 (N1, W2, W3) and broke 3 (W4, F2, C1).

**Scorecard against the predictions:**
- N1 recovered, as predicted. N2 and H1 did **not**: the agent still says "we can only issue refunds for undelivered orders" (N2) or declines (H1), so the invented rule survived the wording that was meant to remove it.
- Policy compliance stayed 24/24 on golden, but on the held-out set it fell to 7/8 (H2 skipped the lookup again; v2 had 8/8). Not as predicted.
- Over-asking: W2 and W3 recovered; N7 ("Where is order 49 right now?") still asks for an order number it was given.
- A2 and H4 (invented amounts) and W1 (cannot cancel) still fail, as predicted: this model does not follow "ask instead of invent" from the prompt.
- New failure: W4 ("What's your refund policy?") now asks for an order number instead of stating the policy (the baseline answered it).
- Failure lab on `full-v3` (eval-55a817a2): the control passes, 3 faults fixed, 0 broken, wrong tool unchanged, as predicted. Cost: 3 retries, tool calls 11 -> 13, model calls 14 -> 17, median run 11.3 -> 14.2 s.

**Triage finding (checker, not agent).** Two of the golden failures are the checker rejecting a correct answer, the same kind of gap as F1 and C2 on Day 3. C1 and C4 ask for a refund over the $100 limit and the agent correctly declines ("the policy does not allow a refund of $180 ... the maximum refund allowed is $100"), but the answer patterns for C1 and C4 only recognise "can't / cannot / unable / unfortunately / won't / limit". C2's patterns were widened for this on Day 3 and C1/C4 were not. Counted as correct, v2 would be 16/24 and v3 17/24 (baseline stays 19/24, whose answers already matched). N2, N7 and W4 are real failures. Nothing has been changed: any fix is a new dataset version (widening only, the old results staying under the old hash), and is an owner decision.

### Stage 5c: golden-v3 and rescoring (2026-10-19)

**The triage covered everything, not just v3.** Every stored real-model answer that failed an answer pattern (18 distinct answers across all variants and both datasets) was read. Correct answers the checks rejected: C4 (under v2) and C1 (under v3), both correct refusals of an over-limit refund ("the policy does not allow a full refund ... the maximum refund amount is $100"). Everything else was a genuine agent failure: invented amounts (A2, H4), asking for details already given (N7, W2, W1, F2, W4), and invented rules (N6 "cannot change the address once dispatched" for an order that is shipped, N2, H1).

**golden-v3** widens only the answer patterns of C1 and C4 (adding maximum / only allows / not allowed / does not allow / doesn't allow / exceeds, the C2 alternation plus the observed wording). The diff against v2 is the version, the changelog and those two lines, and a test pins that. Widening only, so an answer v2 accepted v3 accepts; each added phrase is tested on its own, and a refusal-sounding answer cannot hide an issued refund. golden-v3 is now the default dataset; golden-v2 stays loadable and its hash is unchanged.

**`rescore`** (`python -m blackbox.evals rescore <eval_id> --dataset golden-v3`) judges the stored runs of an evaluation against another dataset version. No model is run; the runs are the same, only the expectations differ. The new evaluation records `rescored_from`, the original is untouched, and it refuses lab and validation evaluations, a dataset missing a case, and a case whose task text changed. All seven real golden evaluations were rescored, so every variant is judged by the same cases.

**Final golden-v3 table** (`qwen2.5:7b`, seed 0, 24 cases; fixed / broken against baseline eval-09d327ad):

| Variant | Evaluation | Passed | Fixed | Broken | Policy | Task | Tool calls | Median run |
|---|---|---|---|---|---|---|---|---|
| baseline | eval-09d327ad | 19/24 | | | 21/24 | 22/24 | 39 | 10.3 s |
| resilient | eval-b07a0e6d | 19/24 | 0 | 0 | 21/24 | 22/24 | 39 | 10.3 s |
| guided (v2) | eval-71224f4b | 16/24 | 2 | 5 | 24/24 | 16/24 | 25 | 8.3 s |
| full (v2) | eval-08ae09b9 | 16/24 | 2 | 5 | 24/24 | 16/24 | 25 | 8.1 s |
| guided-v3 | eval-c45fdf03 | 17/24 | 1 | 3 | 24/24 | 17/24 | 31 | 9.3 s |
| full-v3 | eval-1f87936d | 17/24 | 1 | 3 | 24/24 | 17/24 | 31 | 8.7 s |

(The first `full` run, eval-67a0cc90, rescored to eval-5472de4e, flipped 0 cases against its repeat.) The held-out set needs no rescoring: holdout-v1 is unchanged.

**What the whole of Day 5 shows, in plain words.**
1. *Resilience works and costs nothing when nothing is wrong.* On the real model it turned all three recoverable faults (timeout, model failure, malformed output) from harmful to harmless, with 0 regressions on 24 + 8 clean cases and identical call counts there. It cost 3 retries (11 -> 13 tool calls, 11.3 -> 13.0 s median) across the lab.
2. *Prompt guidance did not work on this 7B model, twice.* It removed every policy violation (21/24 -> 24/24 on golden, and on held-out for v2) by making the agent do less, and in doing so lost task completion (22/24 -> 16/24 for v2, 17/24 for v3). Fewer tool calls (39 -> 25 / 31) is the same fact seen from the cost side. It did not stop invented amounts or fix the cannot-cancel case.
3. *The harness is what made these findings visible.* A pass rate alone would have said "guided 16/24, worse"; the fixed/broken table says which cases and the traces say why. The regression, the over-asking, the invented rule, and the checker gap were all found by reading stored runs, not by guessing.
4. *Recommended agent from this evidence: `resilient`.* A code-level guard (lookup-first enforcement, or checking that every tool argument appears in the customer's message) is the next experiment (Day 7); the prompt route has been tried twice and stopped, by decision.

### Stage 6: the comparison UI (done, 2026-10-19)

- **Page** `#/compare/<before>/<after>` (`pages/ComparePage.tsx`): a headline of counts ("2 cases fixed, 5 cases broken", never "improved"), pass counts before and after, then case by case (changed ones first, broken before fixed, a link to the run behind each side), by check with a signed change, cost, by kind of task, and a "how to read this" card. The failure lab is compared by what each fault did to the run, not by whether it was located. Two runs of the same agent show a note that the difference is noise.
- **Entry points:** a picker on every finished evaluation report that offers only evaluations the API would accept (same kind, model, dataset content and seed; the rule is mirrored in `lib/compare.ts`, and the API still decides and the page shows its reason in words); an Agent column and chip in the evaluation list, on the report and on a run (shown on a run only when it is not the baseline); "rescored" is marked.
- **Retries on spans:** a "retried x N" badge in the waterfall, a note and a Retries fact in the inspector, retry events listed with their attempt number, and "Where to look first" shows the retried span.
- **Checked on the real data** in headless Edge: baseline against guided v2 and v3, the real-model lab against resilient, the report-page picker, a real retried run, and a 520 px wide layout. Two defects found by looking and fixed: row labels in the cost table inherited the column-heading style, and three tables were not inside a scroll container, so they pushed the page sideways at narrow widths (each table now scrolls inside its card).
- **Dev tooling:** the Vite proxy target can be set with `BLACKBOX_API`, because ports 8000, 8001 and 8765 on this machine are used by other projects' services. Those were found by reading what owned each port, not assumed; nothing that was not started by this project was touched.
- Tests: 46 new frontend (`lib/compare.test.ts`, `pages/ComparePage.test.tsx`), 128 in all; typecheck and production build clean. Mutation-checked (17 mutations; one survivor, "an unfinished evaluation on the first side", was a real gap and is now tested).
