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

## Day 2 — Dashboard core
- [ ] Vite + React + TS, typed API client
- [ ] Run list (status, duration, scores)
- [ ] Trace waterfall + span tree
- [ ] Span inspector (args, output summary, error, redaction visible)
- **Done when** you can click through a real run and see timing and errors.

## Day 3 — Evaluation
- [ ] Golden set of 20–30 tasks: normal, ambiguous, wrong-tool, tool-failure, constraint-violation
- [ ] Deterministic checks: task completion, tool/argument correctness, step efficiency, policy compliance, trace completeness
- [ ] Pytest suite on scripted model
- [ ] Evaluation report view in UI
- **Done when** `pytest` yields a repeatable score table shown per run in the UI.

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
