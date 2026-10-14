# Agent Blackbox — Weekly Plan

Rough target, ordered by what the audience sees first. A day is done only when its **Done when** is met. If something overruns, cut from stretch, not from Day 6.

## Day 0 — Spike and brief (gate) — DONE
- [x] Environment check (Python 3.13 system / 3.12 venv, Node 24, Docker 29, Ollama 0.40, CPU-only inference, 16 GB RAM)
- [x] Jaeger up via Docker; nested OTel trace with `run_id` reaches it (Jaeger v2, query API at `/api/v3`)
- [x] Ollama model with tool calling picked — carried to Day 1 and resolved there: `qwen2.5:7b` works as judge (~49 s per judged metric on CPU) and as a tool-calling agent. Alternatives not yet tried: `llama3.1:8b`; fallback `llama3.2:3b`. Exact tokens/sec not measured.
- [x] Trace -> DeepEval case; metrics run on Ollama, telemetry off, zero non-loopback connections
- [x] `run_id` joins trace, eval result, SQLite row (0 orphan spans; stored `trace_id` resolves in Jaeger)
- **Done when** all three spike checks pass or fallback chosen. No Day 1 before this. -> **Met.**
- Findings are recorded in BRIEF.md ("Spike results"). Spike scripts were throwaway and live outside the repo.

## Day 1 — Instrumented agent — DONE (not committed)
- [x] Model interface: scripted + Ollama implementations
- [x] Hand-rolled agent loop, 4 mock business tools (lookup_order, check_refund_policy, issue_refund, update_shipping_address)
- [x] Spans: run / model call / tool call; `gen_ai.*` attributes; error recording
- [x] Redaction — implemented as a wrapping `RedactingExporter` (OTel processors only see read-only finished spans), applied to both Jaeger and SQLite exports
- [x] Dual export: OTLP -> Jaeger + SQLite spans table
- [x] FastAPI: start run, fetch run, list runs, fetch spans (Pydantic models)
- [x] Tests: 35 pytest tests (34 unit + 1 Jaeger integration); redaction and error-status tests were mutation-checked
- **Done when** one run shows a correct nested trace in Jaeger and the same spans in SQLite. -> **Met** (verified live: 6/6 spans in both, parent links and error statuses match).
- Day 0 carry-over resolved: `qwen2.5:7b` completed the full lookup -> policy check -> refund -> answer sequence via native Ollama tool calling (28.7 s total on CPU; first model call 12.3 s incl. model load, later calls 2.8–3.9 s; real token counts recorded). One run only — not yet a reliability measurement; `llama3.1:8b` not tried.

## Day 2 — Dashboard core — DONE (not committed)
- [x] Vite + React + TS (exact-pinned deps), typed API client behind a `DataSource` interface (live API now; prebaked demo data on Day 6)
- [x] Run list: status pills (icon + label), summary strip, status filter, start-run panel (scripted scenario or local Ollama). Scores column deliberately omitted until Day 3 produces real scores.
- [x] Trace waterfall (indented span tree + shared time axis), table twin of the waterfall, legend, hover/focus tooltip, arrow-key navigation
- [x] Span inspector: facts, tool args/output, prompt transcript, events/exceptions, all attributes; redacted values shown as chips with a count; opens on the failed span by default
- [x] Light/dark/system theme, phone-width layout, API-down state with start command, running state, empty and not-found states
- [x] Backend additions: `GET /scenarios`, `start_offset_ms` on spans (exact integer math; epoch ns exceed JS safe integers)
- [x] Tests: 44 frontend (vitest + Testing Library) and 39 backend; frontend suite run 6x with no flakes
- **Done when** you can click through a real run and see timing and errors. -> **Met**, checked in rendered screenshots (Edge headless) at desktop and narrow width, light and dark, on a real `qwen2.5:7b` run, a failed-tool run and a failed run.
- Not done: no real-browser interaction test (clicks/keys are covered by Testing Library, not a real browser); Day 6 owns the static demo build.

## Day 3 — Evaluation — DONE (not committed; detail in [docs/day-3-evaluation-plan.md](docs/day-3-evaluation-plan.md))
- [x] 3.1 Seed orders 46-49; case schema; 24 golden cases (normal 8, ambiguous 4, wrong-tool 4, tool-failure 4, constraint 4); dataset self-consistency tests
- [x] 3.2 Trajectory adapter: stored (redacted) spans become one plain object that every check reads
- [x] 3.3 Seven checks: task completion and policy compliance gate the run; tool correctness, argument correctness, step efficiency, trace completeness and latency are reported. A catalog of 10 planted faults proves each check catches its fault and nothing else (zero false alarms); each rule is mutation-checked
- [x] 3.4 Shared `RunService`; `eval_runs`/`eval_cases`/`eval_results` tables; eval runner, CLI (`python -m blackbox.evals run --mode ollama|reference|faults`) and API
- [x] 3.5 Real benchmark: `qwen2.5:7b`, seed 0, golden-v2: **19 of 24 runs passed both gating checks** (eval-5b8f6d3c, 4 minutes on CPU). Every failure was triaged (see BRIEF.md "Day 3 findings")
- [x] 3.6 UI: evaluations list, report (headline, per-check bars, per-category bars, case x check matrix, failing first), Evaluation card on each run, Findings on the span, validation shown as detection rate and false alarms
- [x] 3.7 Docs updated; local commits pending your go-ahead
- [ ] 3.8 *(Day 7)* DeepEval adapter, tool-correctness cross-check, judged subset of 6 labelled as estimates
- [ ] 3.9 *(later, only if needed)* keyed digest of sensitive args so address values can be verified from a redacted trace
- **Done when** `pytest` passes with the exact fault-catalog matrix, a stored real-model evaluation exists, and the UI shows it per case and metric with a path to the failing span. -> **Met.**
- Numbers: 192 backend tests (incl. 1 Jaeger integration) and 69 frontend tests; frontend suite repeated 3x with no flakes.
- Limits: n=24, one run per case, one model. Address values are not verified (option B). No judge-model metrics yet.

## Day 4 — Failure lab
- [ ] Faults: tool timeout, malformed tool output, wrong tool choice, failed model response
- [ ] Failure-localization check (trace analysis points at injected span)
- [ ] UI: failed span highlighted, effect on run shown
- **Done when** each fault is reproducible and localized.

## Day 5 — Fix and compare
- [ ] Fix toggle (retry+timeout, output schema validation, better tool description)
- [ ] Baseline vs fixed over N runs; regression-rate metric
- [ ] Comparison view
- **Done when** a measured before/after table exists.

## Day 6 — Showcase
- [ ] Static demo mode with prebaked real runs, deployed on free hosting
- [ ] Demo video/GIF (agent runs -> tool fails -> click red span -> score drops -> fix -> improves)
- [ ] Screenshots, README (plain-language top, technical below), Docker Compose

## Day 7 — Buffer / stretch
- [ ] DeepEval semantic metrics with local judge (if spike viable)
- [ ] Judge agreement vs hand-labeled subset
- [ ] Slipped items

## Rules
- Every README number comes from a recorded run.
- One model loaded at a time (16 GB RAM); cap WSL memory.
- Bulk runs use the scripted model; real Ollama for showcase runs and live-path validation.
