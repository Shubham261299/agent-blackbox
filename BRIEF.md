# Agent Blackbox — Project Brief

Tagline: **Agent Flight Recorder** — local-first observability and evaluation workbench for AI agents.

## Pitch
Run an agent, record every important operation, inspect the trace, evaluate the execution, inject a failure, and compare the original run with the repaired run — from one dashboard.

The differentiator is connecting three things:
1. **Observability** — what happened, in what order, how long, where it failed.
2. **Evaluation** — did the agent finish the task, use the right tools, obey constraints, avoid wasted steps.
3. **Debugging** — which span caused the failure, and did the fix measurably improve the next run.

## Audience
Hiring managers and HR first (must work without being run: static demo, video, plain-language README), technical reviewers second (architecture, stack, measured results).

## Constraints
- Zero cost: Ollama locally, Jaeger in Docker, DeepEval locally. No hosted models, no Confident AI / hosted eval platform, DeepEval telemetry off.
- Never silently fall back to a hosted model.
- Machine: 16 GB RAM, Docker allowed. Never load agent model and judge model at the same time.
- No custom tracing protocol; no full observability platform. Jaeger is the real OTLP backend and validation target.

## Architecture boundaries
- Agent executes tasks (model behind an interface: scripted/replay for tests, Ollama for showcase).
- OpenTelemetry records execution (nested spans, attributes, events, status, redaction processor).
- Jaeger stores/displays exported traces.
- SQLite holds app-level run metadata, a copy of spans for the UI, eval results and comparisons.
- DeepEval + deterministic checks evaluate outputs and trajectories. Preferred design: **evaluate from the recorded OTel trace** via an adapter (to be confirmed by spike).
- UI (Vite + React + TS) joins everything on a shared `run_id`.

## Key design decisions
- Dual export: OTLP -> Jaeger, plus a SQLite span copy (Jaeger's query API is not a stable contract; default storage is in-memory).
- Redaction in an OTel SpanProcessor, before export.
- Model-call spans use OTel GenAI semantic conventions (`gen_ai.*`).
- "Repaired run" = a code/config fix toggle (retry+timeout, tool-output schema validation, better tool description), compared with fixed / broken counts over the golden and held-out sets. Not automated self-repair. (Built on Day 5 as named agent variants; "N runs" became identical-settings reruns, because at temperature 0 other seeds change nothing.)
- LLM judge is optional; deterministic checks are the backbone. Judge validated against a hand-labeled subset.

## Metrics
Task completion, tool correctness, argument correctness, step efficiency, failure localization, trace completeness, latency (total + per span), regression rate. Every published number comes from a recorded run.

## Out of scope (v1)
Custom tracing DB/protocol, auth/multi-user, hosted deployment of the backend, automated self-repair, OTel metrics/logs pipelines, auto-instrumentation libraries.

## Spike (gate before building) — PASSED
1. Nested OTel trace reaches Jaeger with a `run_id` attribute.
2. A trace converts to a DeepEval case; one metric runs against Ollama with no network calls.
3. `run_id` joins trace, eval result and a SQLite row.
Fallback if (2) fails: deterministic-only evals; local judge becomes a separate milestone (not needed).

## Spike results (what was actually verified)
- **Jaeger**: `jaegertracing/jaeger` is v2. Old `/api/traces` and `/api/services` return 404; use `/api/v3/...` (OTLP-shaped JSON, nanosecond timestamps). **Pin the image tag in Docker Compose** (spike used `latest`). In-memory storage: traces vanish on restart.
- **Trace in Jaeger**: parent links, durations, `run_id` on every span, exception event and ERROR status all round-trip correctly.
- **Evaluate-from-trace works (design B)**: spans fetched from Jaeger were adapted into an `LLMTestCase` plus DeepEval's `_trace_dict`. `_trace_dict` is a *private* attribute and agentic metrics (e.g. `TaskCompletionMetric`, `requires_trace=True`) read it, so **pin the DeepEval version** and add an adapter test that fails loudly on format change.
- **Metrics tried**: `ToolCorrectnessMetric` (deterministic, 1.0, instant) and `TaskCompletionMetric` with `qwen2.5:7b` judge (0.95, ~49 s on CPU). Not yet tried: step-efficiency, plan/trajectory metrics, failing runs.
- **Hosted-model trap**: metrics default to a hosted OpenAI client when no `model` is passed (spike only failed closed because no key was set). **Rule: always pass an explicit local model, via one factory function.**
- **Telemetry**: `DEEPEVAL_TELEMETRY_OPT_OUT=YES`; socket guard recorded zero non-loopback connections. Keep the guard in the test setup. Telemetry-on was not tested.
- **Extra dependency**: DeepEval's `OllamaModel` needs the `ollama` Python package.
- **Cost**: judged metrics are slow on CPU (~49 s each), so bulk evals use deterministic checks and the scripted model; judged metrics run on a small subset.
- **SQLite join**: one `run_id` joins runs, spans (0 orphans) and eval results; stored `trace_id` resolves in Jaeger.

## Day 1 findings
- **Windows clock**: `time.time_ns()` ticks ~1 ms here, so microsecond spans collide (identical timestamps, 0 ms durations, ambiguous order). `telemetry/tracing.py` anchors wall time once and advances it with `perf_counter_ns()`, with explicit span start/end times.
- **Observer effect**: exporting to SQLite synchronously inflated the parent span (6.2 ms vs ~0.6 ms of child work). SQLite export now runs on a batch (background) thread.
- **Jaeger must not gate a run**: the app marks a run finished after the SQLite copy is flushed (`flush_store`); OTLP export is best-effort. Test covers Jaeger-down. `agent.run` duration is measured before any export.
- **DeepEval pytest plugin sends analytics unless opted out** (PostHog). Disabled with `-p no:deepeval` in pytest config, and `DEEPEVAL_TELEMETRY_OPT_OUT=YES` is hard-set in `blackbox/__init__.py` before deepeval can be imported; `test_privacy.py` guards both. One pytest session ran before this fix (its plugin skips the event when no DeepEval work happened, which was the case, so likely nothing was sent — not proven).
- **Redaction limits**: key-based (known field names in JSON, including JSON nested inside JSON strings) plus patterns (emails, card-like numbers, local user-home paths). Free-text PII such as an address in prose is not caught. Local home paths are scrubbed because stack traces would otherwise leak the Windows username into spans.
- **Ops lesson**: never stop processes by port number; record the PID you started. A port-based kill matched 3 PIDs, and Docker Desktop restarted shortly afterwards (causal link unproven). The Jaeger container does not survive a Docker restart (no restart policy yet).

## Day 2 findings
- **Observer effect again, in the failure path**: recording an exception formats a stack trace inside the span; a failing tool call read 31 ms against ~0.16 ms of real work. Expected tool failures now record a cheap event (type + message, no stack trace) and `start_span` takes the end time before recording an exception. Both have mutation-checked tests. Matters for Day 4: injected failures must not be distorted by the tracer.
- **JS cannot hold epoch nanoseconds exactly** (~1.8e18 vs 9e15 safe integer): the API sends `start_offset_ms` computed server-side from integers.
- **Chart colours validated, not guessed**: model calls violet, tool calls aqua, agent run neutral, failures use the status red with a ✕ (never colour alone). Checked with the dataviz validator against the app's own surfaces in both themes; all checks pass. Aqua is just under 3:1 on the light surface (2.72), so every bar has a visible text label in its row plus a table view.
- **Fonts**: system font stacks only (no web fonts), so the app works offline and nothing is fetched from a third party.
- **UI state bug caught by looking at a screenshot**: a keyed spans query briefly rendered "No spans recorded" for one frame while loading. Fixed by mounting the trace section only once the run has finished; regression test added.
- **Verification method**: headless Edge screenshots (no extra install). Iframes under a `file://` parent with a virtual clock load unreliably and gave false "loading" frames; narrow layouts are checked by rendering the real page with a device scale factor instead.
- Ops: dev servers were started and stopped by recorded PID (killing the process tree); ports 8000/5173 are free when not in use.

## Day 3 findings
- **Two kinds of evaluation.** (A) Metric validation: scripted runs with a planted fault, in pytest, prove the checks work (10 faults, each caught by exactly the expected checks, 0 false alarms). (B) Agent benchmark: the real model on 24 cases, stored, with n shown. A scripted run says nothing about a model, so only B produces a headline number.
- **First real benchmark (`qwen2.5:7b`, seed 0, golden-v2): 19 of 24 runs passed both gating checks.** Failures: N6, N8, F2 act on an order without looking it up first (the system prompt forbids this; policy check); A2 ("Refund some of order 42") invented an amount ($10) and refunded it; W1 never said it cannot cancel. Reported-check failures that did not fail the run: A4 invented order id 12345, F4 replaced "abc" with 123, F3 invented a $25 amount. The recurring weakness is **inventing missing values instead of asking**, plus skipping the lookup. That is the headroom Day 5 will target.
- **Triage rule held.** First run (golden-v1): 17/24. Two failures were dataset errors (F1 "I'm unable to find order 999", C2 "the policy only allows a maximum refund of $100" were correct answers my patterns did not recognise). They were fixed under a new version (golden-v2: only those two cases changed, a test pins that); v1 results stay under the v1 hash. No case was ever edited to flatter the model.
- **Reproducibility check.** Same model, seed and temperature across the two runs: identical behaviour in 24/24 cases (the only difference in tool calls was JSON key order), 23/24 final answers word-for-word identical. This is evidence of near-determinism, not a guarantee.
- **Checker bugs found by tests, not by luck:** a bare "refunded" matched "...you'd like refunded?"; the sentence splitter broke on the decimal in "$59.90"; the claim pattern missed "I've *also* issued". The fault catalog also exposed a missed fault (claims_unperformed_action). All fixed with regression tests.
- **Design consequence of redaction:** `new_address` is redacted, so only the order id of an address change is verifiable (option B). A keyed digest (option A) can be added if it proves necessary.
- **Observed, not acted on:** in one run the agent printed the customer's order record, including the (scrubbed) email, back in its answer. Worth a policy check later.
- **Infrastructure bugs found by actually running it:** the default database path was relative to the working directory (benchmark results landed in `backend/data/`), and `python -m blackbox.evals` only worked from `backend/`. The path is now anchored to the project root and the project is installed editable, so both work from any folder. A leftover `backend/data/blackbox.db` from the first run is git-ignored and can be deleted.

## Day 4 findings
- **Four faults, four different signatures.** A timeout and a model failure are loud: error status, the run ends, and the error span is the signal. A malformed tool output is silent: the span is OK, both gating checks pass, and only a contract on tool outputs notices. A wrong tool choice raises nothing either (the address change fails as an ordinary tool error); the policy check is what exposes it.
- **Real model behaviour under faults (qwen2.5:7b, seed 0).** It retried the lookup after the garbage reply and finished the refund correctly, so the corrupted call left only one extra tool call and a failed contract check. After the swapped first call it looked the order up and carried on, so the outcome was right but the process violated policy. The two infrastructure failures killed the run: the baseline agent has no handling for them, which is deliberate and is what Day 5 will fix.
- **The lab found a bug in my localizer.** The first version ranked the run span (named by the "run failed" check) above the real culprit for the two loud faults, so only 2 of 4 were located. Signals naming the run span are now dropped whenever a span beneath it is suspect. A reminder that a heuristic validated on its own examples is only as good as those examples.
- **A test caught a leak of ground truth.** The recorded exception type was `blackbox.faults.injector.ToolTimeoutError`, which tells a reader a fault was planted. The error classes now live in a neutral module. Stack frames still name the injector (that is where the exception is raised), so the guarantee is narrower and stated: the localizer never reads stack traces (a test enforces it), and trace text outside stack frames never says "inject" or "fault".
- **Misleading timing, caught by looking.** The control run of the real-model lab paid for loading the model into memory (23.6 s against 6 to 19 s for the faulted runs), which made faults look like speed-ups. The lab now warms the model up first (untraced); the control is 16.6 s.
- **What counts as a "span" for a wrong-tool fault.** The origin is the tool span that ran the wrong call, not the model span that chose it: the first place a trace reader could see something wrong. That is a definition, and it is stated on the report.
- Cleanup: two superseded evaluations (the first real-model lab with the unfair control time, and the 10-fault validation that predates the contract check) and the runs they created were removed from the local database.

## Day 5 findings
- **The fix toggle is two independent groups, so the result can be attributed.** Resilience (retry timeouts and model errors up to twice, reject tool output that breaks its contract and retry) and guidance (a new prompt and tool descriptions). Six presets: `baseline` (byte-identical to the Day 1-4 agent), `resilient`, `guided`, `full`, `guided-v3`, `full-v3`. A retry happens inside the one span the model's request created and is recorded as an event, so the trace keeps one span per call and the existing checks needed no change.
- **Resilience works and is free when nothing is wrong.** On the real model (`qwen2.5:7b`) it turned tool timeout, model failure and malformed output from harmful to harmless (3 faults fixed, 0 broken) at a cost of 3 retries, 11 -> 13 tool calls and about 15% more median time across the lab. On the 24 golden and 8 held-out cases, which contain no infrastructure faults, it changed nothing (0 fixed, 0 broken, identical call counts). The wrong-tool fault is untouched by it, as predicted. In one real run the retry logic absorbed two genuine 300-second read timeouts from a stalled model and the case still passed (cause unknown: an Ollama stall or the laptop sleeping).
- **Prompt guidance made the agent worse, twice, and the harness is what showed it.** Golden pass counts (golden-v3): baseline 19, guided v2 16, guided v3 17 of 24. Both removed every policy violation (21/24 -> 24/24) by doing less, and lost task completion (22/24 -> 16 and 17). Read from the stored traces: v2 invented a "refunds only for undelivered orders" rule and asked for details the customer had already given; v3's rewording fixed some of that but not the invented rule. Neither stopped invented amounts, and neither fixed the cannot-cancel case. A 7B model does not reliably follow "ask instead of invent" from a prompt, so the next experiment is a code-level guard (enforce lookup-first, check that every tool argument appears in the customer's message), not a third prompt.
- **Discipline that made the result trustworthy.** Predictions were written into the plan before each run; v1 and v2 of the guidance are frozen and pinned by tests; v3 was declared the only second attempt, with the criterion (golden above 19) fixed in advance, and it failed. A held-out set of 8 cases was written before any tuning (baseline 5/8; v2 and v3 also 5/8, with different cases moving). It is not a clean test for v3, because v2's held-out results had been read first, and the report says so.
- **Noise floor: 0 of 24 flipped, twice.** At temperature 0 the model repeated every verdict (baseline vs the Day 3 baseline, and `full` vs `full`), so repeats at other seeds would add nothing and were replaced by identical-settings reruns. One model, one machine: evidence of determinism, not a guarantee.
- **A checker gap, found by triage and fixed without flattering anyone.** Every failing answer across all variants was read (18 distinct answers). Two were correct refusals the checks rejected (C1 and C4: "the policy does not allow ... the maximum refund is $100"), the same gap C2 had on Day 3. Everything else was a real agent failure. golden-v3 widens only those two answer patterns (golden-v2 stays loadable, hash unchanged) and `rescore` re-judged the stored runs of every golden evaluation against it without running a model, so all variants are judged by the same cases. It moved v2 from 15 to 16 and v3 from 15 to 17 and left the baseline at 19.
- **The comparison refuses to lie.** `compare` only accepts two finished evaluations of the same kind, model, dataset content and seed, says why in words when it refuses, counts fixed / broken / still passing / still failing over cases both sides ran, and reports cost (tool calls, model calls, retries, median and total time, tokens only when every call reported them). Two runs of the same agent are allowed on purpose: that is the noise floor. The UI page shows counts, never "improved", with broken cases first.
- **The localizer learned a recovered fault.** A new tier ranks a span that needed retries, found from the event's name and never its text; without it a recovered run has no suspects and the lab scored every recovered fault as missed. On the real model all four lab faults are located at rank 1 under the resilient agent.
- **Tests that checked themselves.** Mutation checks (deliberately breaking the code and confirming a test fails) found real test gaps this stage: a "found by event name, not text" test that could not tell the difference, an added answer phrase never tested on its own, v3's tool texts not pinned against v2's, and a comparison rule checked on only one side. Each was fixed and the mutation re-run.
- **Environment lesson.** Ports 8000, 8001 and 8765 on this machine belong to other projects' services; a health check against the wrong one just returns 404. Servers are started on a free port, the UI proxy is set with `BLACKBOX_API`, and only processes this project started are stopped.
- **Recommended agent from the evidence: `resilient`.** Limits: one model, n of 24 + 8, one run per variant, the lab faults are simulated and fire once, and the prompt results belong to this prompt and this model. All numbers and evaluation ids are in docs/day-5-fix-and-compare-plan.md, section 12.

## Where things stand
Days 0-5 are built and measured. See PLAN.md, section "Resume here", for status, standing rules, run commands and the Day 6 starting point; the Day 6 plan is docs/day-6-showcase-plan.md.

## Environment
Venv `.venv` (Python 3.12.14 via uv). Installed: opentelemetry-sdk/exporter-otlp 1.45.1, deepeval 4.2.8, fastapi 0.143.0, pytest 9.1.1, ollama 0.6.3. Ollama models present: qwen2.5:7b, llama3.1:8b, llama3.2:3b, qwen2.5:14b (too heavy with Docker on 16 GB). Jaeger container name `jaeger`, ports 16686/4317/4318.
